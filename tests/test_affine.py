"""Check declared affine laws against independent integer arithmetic and B execution."""
from itertools import product

import pytest

from b_lang.affine import implementation
from b_lang.compiler import compile_b
from b_lang.composition import analyze
from b_lang.runtime import BContractError


def obligation(analysis, name):
    return next(item for item in analysis.obligations if item.kind == "ensures" and item.caller == name)


def execute(compiled):
    env = {}
    exec(compiled.code, env)
    return env


def functions(compiled):
    return {stmt.name: stmt for stmt in compiled.ir.statements if stmt.op == "fn"}


def test_conservation_needs_the_suppliers_public_equations():
    source = """
fn free_after(x: Int) -> Int pure requires x > 0 ensures result == x - 1 = x - 1
fn booked_after(y: Int) -> Int pure requires y >= 0 ensures result == y + 1 = y + 1
fn total(x: Int, y: Int) -> Int pure requires x > 0 and y >= 0 ensures result == x + y = booked_after(y) + free_after(x)
"""
    c = compile_b(source)
    previously = analyze(c.ir, affine_guarantees=False)
    total = obligation(c.analysis, "total")
    assert total.status == "proved" and total.proof_method == "affine-equality"
    assert obligation(previously, "total").status == "unknown"
    assert set(total.dependencies) >= {"free_after", "booked_after"}
    assert functions(c)["total"].verification == "proved-affine"
    env = execute(c)
    for free, booked in product(range(1, 5), range(4)):
        assert env["total"](free, booked) == free + booked

    only_signs = source.replace("result == x - 1", "result >= 0").replace("result == y + 1", "result > 0")
    opaque = compile_b(only_signs)
    assert obligation(opaque.analysis, "total").status == "unknown"
    assert execute(opaque)["total"](1, 0) == 1


def test_wrong_public_increment_cannot_certify_the_consumer():
    src = """
fn booked(y: Int) -> Int pure ensures result == y + 1 = y + 2
fn balance(x: Int, y: Int) -> Int pure ensures result == x + y = x - 1 + booked(y)
"""
    c = compile_b(src)
    assert obligation(c.analysis, "booked").status != "proved"
    assert obligation(c.analysis, "balance").status != "proved"
    with pytest.raises(BContractError, match="booked"):
        execute(c)["balance"](3, 5)


def test_truth_about_the_implementation_can_disagree_with_the_accounting_rule():
    c = compile_b("""
fn booked(y: Int) -> Int pure ensures result == y + 2 = y + 2
fn observed(x: Int, y: Int) -> Int pure ensures result == x + y + 1 = x - 1 + booked(y)
fn intended(x: Int, y: Int) -> Int pure ensures result == x + y = x - 1 + booked(y)
""")
    assert obligation(c.analysis, "observed").status == "proved"
    assert obligation(c.analysis, "intended").status != "proved"
    env = execute(c)
    assert env["observed"](2, 3) == 6
    with pytest.raises(BContractError, match="intended"):
        env["intended"](2, 3)


def test_both_callee_precondition_and_entire_postcondition_are_needed():
    c = compile_b("""
fn limited(x: Int) -> Int requires x > 0 ensures result == x + 1 = x + 1
fn partial(x: Int) -> Int ensures result == x + 1 and result > 0 = x + 1
fn unchecked(x: Int) -> Int ensures result == 2 * (x + 1) = 2 * limited(x)
fn verified(x: Int) -> Int requires x > 0 ensures result == 2 * (x + 1) = 2 * limited(x)
fn sibling(x: Int) -> Int ensures result == 2 * (x + 1) = 2 * partial(x)
""")
    assert obligation(c.analysis, "verified").status == "proved"
    for name in ["unchecked", "partial", "sibling"]:
        assert obligation(c.analysis, name).status != "proved"
    ns = execute(c)
    assert ns["verified"](3) == 8
    with pytest.raises(BContractError, match="limited"):
        ns["unchecked"](0)
    with pytest.raises(BContractError, match="partial"):
        ns["sibling"](-1)


def test_partial_correlated_domain_does_not_supply_a_spurious_refutation():
    c = compile_b("""
fn diagonal(x: Int, y: Int) -> Int requires x == y ensures result == y = x
fn zero(x: Int) -> Int requires x == 0 ensures result == x = 0
""")
    env = execute(c)
    for n in range(-3, 4):
        assert env["diagonal"](n, n) == n
    assert env["zero"](0) == 0
    for name in ["diagonal", "zero"]:
        assert obligation(c.analysis, name).status != "refuted"


def test_form_does_not_cross_float_foreign_recursive_or_nonlinear_boundaries():
    c = compile_b("""
use py:math as math
fn foreign_body(x: Int) -> Int ensures result == x = math.floor(x)
fn recursive(x: Int) -> Int ensures result == x = recursive(x)
fn square(x: Int) -> Int ensures result == x = x * x
fn widen(x: Int) -> Float ensures result == x = x
""")
    fns = functions(c)
    for name, fn in fns.items():
        assert implementation(fn, fns, {}, expand_bodies=True) is None
        assert obligation(c.analysis, name).status != "proved"


def test_finite_oracle_checks_signed_coefficients_offsets_and_semantic_mutations():
    # The declaration permutes independent inputs and distributes its constant.
    # An implementation with a wrong slope can coincide on an entire line of
    # samples. Evaluate the full Cartesian domain, including both off-diagonals.
    gains = 0
    for a, b, shift, mutation in product((-2, 0, 2), (-1, 1), (-1, 1), ("none", "slope", "offset")):
        body_a = a + int(mutation == "slope")
        body_c = shift + int(mutation == "offset")
        compiled = compile_b(f"""
fn f(x: Int, y: Int) -> Int requires -2 <= x and x <= 2 and -2 <= y and y <= 2 ensures ({b}) * y + x * ({a}) + ({shift}) == result = ({body_c}) + ({body_a}) * x + ({b}) * y
""")
        status = obligation(compiled.analysis, "f").status
        f = execute(compiled)["f"]
        valid = []
        for x, y in product(range(-2, 3), repeat=2):
            actual = body_a * x + b * y + body_c
            intended = a * x + b * y + shift
            valid.append(actual == intended)
            if actual == intended:
                assert f(x, y) == intended
            else:
                with pytest.raises(BContractError):
                    f(x, y)
        if status == "proved":
            assert all(valid), (a, b, shift, mutation)
        if status == "refuted":
            assert not any(valid), (a, b, shift, mutation)
        if mutation == "none":
            assert status == "proved"
            gains += obligation(analyze(compiled.ir, affine_guarantees=False), "f").status != "proved"
    assert gains > 0


def test_excessively_deep_body_expansion_declines_without_a_partial_form():
    from b_lang.affine import MAX_CALL_DEPTH

    lines = ["fn first(x: Int) -> Int = x"]
    previous = "first"
    for i in range(MAX_CALL_DEPTH + 2):
        name = f"link{i}"
        lines.append(f"fn {name}(x: Int) -> Int = {previous}(x) + 1")
        previous = name
    compiled = compile_b("\n".join(lines))
    fns = functions(compiled)
    assert implementation(fns[previous], fns, {}, expand_bodies=True) is None
    assert execute(compiled)[previous](0) == MAX_CALL_DEPTH + 2


def test_nested_substitution_respects_argument_order_and_duplicate_coefficients():
    c = compile_b("""
fn g(u: Int, v: Int) -> Int ensures result == -2 * u + 3 * v - 1 = 3 * v - (2 * u + 1)
fn transform(x: Int, y: Int) -> Int ensures result == -3 * x - 2 * y - 3 = g(y + 1, -x)
fn cancel(x: Int, y: Int) -> Int ensures result == x - 1 = g(x + y, x + y) - y
""")
    ns = execute(c)
    for name in ("g", "transform", "cancel"):
        assert obligation(c.analysis, name).status == "proved"
    for x, y in product(range(-2, 3), repeat=2):
        assert ns["transform"](x, y) == -3 * x - 2 * y - 3
        assert ns["cancel"](x, y) == x - 1


def test_two_calls_of_the_same_foreign_function_cannot_be_cancelled(tmp_path, monkeypatch):
    (tmp_path / "b_affine_ticker.py").write_text(
        "value = 0\ndef tick(x: int) -> int:\n"
        "    global value\n    value += 1\n    return value\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    c = compile_b("""
use py:b_affine_ticker as ext
fn difference(x: Int) -> Int ensures result == 0 = ext.tick(x) - ext.tick(x)
""")
    assert obligation(c.analysis, "difference").status != "proved"
    with pytest.raises(BContractError, match="difference"):
        execute(c)["difference"](0)
