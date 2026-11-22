"""Independent checks of declared input/result implications across B calls."""
from __future__ import annotations

from collections import Counter
from itertools import product
import operator

import pytest

from b_lang.compiler import compile_b
from b_lang.composition import analyze
from b_lang.runtime import BContractError


LAW = "result >= 0 and (x <= 0 or result > 0)"
BODY = "if x > 0 then x else 0"


def provider(law=LAW, body=BODY):
    return f"fn p(x: Int) -> Int ensures {law} = {body}\n"


def check(report, caller, kind, target=None):
    matches = [
        item for item in report.obligations
        if item.caller == caller and item.kind == kind and (target is None or item.target == target)
    ]
    assert len(matches) == 1, (caller, kind, target, matches)
    return matches[0]


def execute(compiled):
    namespace = {}
    exec(compiled.code, namespace)
    return namespace


@pytest.mark.parametrize("law", [
    LAW,
    "(0 >= x or 0 < result) and 0 <= result",
])
def test_checked_law_travels_across_a_wrapper_only_for_the_matching_argument(law):
    compiled = compile_b(provider(law) + """
fn wrap(v: Int) -> Int ensures (v <= 0 or result > 0) and result >= 0 = p(v)
fn guarded(n: Int) -> Float = if n <= 0 then 0.0 else 9 / wrap(n)
fn unguarded(n: Int) -> Float = 9 / wrap(n)
fn wrong_argument(n: Int, other: Int) -> Float = if n > 0 then 9 / wrap(other) else 0.0
fn wrong_sign(n: Int) -> Float = if n > 0 then 9 / wrap(-n) else 0.0
""")
    enabled = analyze(compiled.ir, conditional_guarantees=True)
    disabled = analyze(compiled.ir, conditional_guarantees=False)
    for name, kind in (("p", "ensures"), ("wrap", "ensures"), ("guarded", "nonzero")):
        item = check(enabled, name, kind)
        assert item.status == "proved" and item.proof_method == "conditional-guarantee"
        assert check(disabled, name, kind).status == "unknown"
    assert "wrap" in check(enabled, "guarded", "nonzero").dependencies
    env = execute(compiled)
    assert [env["guarded"](x) for x in [-1, 0, 1, 2]] == [0.0, 0.0, 9.0, 4.5]
    for name, args in [("unguarded", (0,)), ("wrong_argument", (2, 0)), ("wrong_sign", (1,))]:
        assert check(enabled, name, "nonzero").status != "proved"
        with pytest.raises(ZeroDivisionError):
            env[name](*args)


def test_counterexample_at_boundary_prevents_export_even_at_a_good_call():
    compiled = compile_b(provider(body="if x >= 2 then 1 else 0") + """
fn use(n: Int) -> Float requires n >= 2 = 1 / p(n)
""")
    assert check(compiled.analysis, "p", "ensures").status == "unknown"
    assert check(compiled.analysis, "use", "nonzero").status == "unknown"
    env = execute(compiled)
    with pytest.raises(BContractError, match="Postcondition"):
        env["p"](1)
    assert env["use"](2) == 1.0


def test_no_published_implication_means_no_cross_boundary_deduction():
    for clause in ["", " ensures result >= 0"]:
        source = f"fn p(x: Int) -> Int{clause} = {BODY}\n"
        compiled = compile_b(source + "fn use(n: Int) -> Float requires n > 0 = 1 / p(n)")
        assert check(compiled.analysis, "use", "nonzero").status == "unknown"
        assert execute(compiled)["use"](2) == 0.5


def test_guarded_summary_cannot_repair_an_unmet_call_precondition():
    compiled = compile_b(f"""
fn p(x: Int) -> Int requires x == 0 ensures {LAW} = 0
fn use(n: Int) -> Float requires n > 0 = 1 / p(n)
""")
    assert check(compiled.analysis, "use", "requires", "p").status == "refuted"
    assert check(compiled.analysis, "use", "nonzero").status == "unknown"
    with pytest.raises(BContractError, match="Precondition"):
        execute(compiled)["use"](1)


def test_independent_short_circuit_operand_must_be_defined():
    compiled = compile_b(f"""
fn p(x: Int, t: Any) -> Int ensures ({LAW}) and (t < t or true) = {BODY}
fn use(n: Int, t: Any) -> Float requires n > 0 = 1 / p(n, t)
""")
    for name, kind in [("p", "ensures"), ("use", "nonzero")]:
        assert check(compiled.analysis, name, kind).status == "unknown"
    with pytest.raises(TypeError):
        execute(compiled)["p"](1, {})


def test_float_parameter_law_and_unknown_foreign_body_are_not_integer_proofs(tmp_path, monkeypatch):
    (tmp_path / "conditional_leaf.py").write_text("def sample(x: int) -> int:\n    return 0\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    compiled = compile_b(f"""
use py:conditional_leaf as ext
fn widened(x: Float) -> Int ensures x <= 0.0 or result > 0 = if x > 0.0 then 1 else 0
fn opaque(x: Int) -> Int ensures {LAW} = ext.sample(x)
fn f(n: Int) -> Float requires n > 0 = 1 / widened(n)
fn g(n: Int) -> Float requires n > 0 = 1 / opaque(n)
""")
    for name, kind in [("widened", "ensures"), ("opaque", "ensures"), ("f", "nonzero"), ("g", "nonzero")]:
        assert check(compiled.analysis, name, kind).status == "unknown"
    env = execute(compiled)
    assert env["f"](1) == 1.0
    with pytest.raises(BContractError, match="Postcondition"):
        env["g"](1)


def test_budget_exhaustion_and_recursion_cannot_supply_a_partial_guarantee():
    # Nine distinct rules exceed the per-function limit of eight.
    rules = " and ".join(f"(x <= {k} or result > 0)" for k in range(9))
    compiled = compile_b(provider(law="result >= 0 and " + rules) + f"""
fn cycle(x: Int) -> Int ensures {LAW} = cycle(x)
fn f(n: Int) -> Float requires n > 0 = 2 / p(n)
fn g(n: Int) -> Float requires n > 0 = 2 / cycle(n)
""")
    for name, kind in [("p", "ensures"), ("cycle", "ensures"), ("f", "nonzero"), ("g", "nonzero")]:
        assert check(compiled.analysis, name, kind).status == "unknown"


def test_all_issued_proofs_agree_with_exhaustive_observations_on_finite_domains():
    # Body, declared guard and caller guard vary independently. Some declarations
    # fail on exactly one boundary. Only count divisor checks on reached calls that
    # actually returned a value: a failed postcondition prevents division entirely.
    statuses = Counter()
    for cutoff, declared, caller in product([-1, 0, 1], repeat=3):
        compiled = compile_b(f"""
fn p(x: Int) -> Int requires -3 <= x and x <= 3 ensures result >= 0 and (x <= {declared} or result > 0) = if x > {cutoff} then x - ({cutoff}) else 0
fn rate(n: Int) -> Float requires -3 <= n and n <= 3 = if n > {caller} then 6 / p(n) else 0.0
""")
        env = execute(compiled)
        post = check(compiled.analysis, "p", "ensures").status
        nonzero = check(compiled.analysis, "rate", "nonzero").status
        all_post = []
        reached_nonzero = []
        for n in range(-3, 4):
            expected = max(n - cutoff, 0)
            satisfies = expected >= 0 and (n <= declared or expected > 0)
            all_post.append(satisfies)
            if not satisfies:
                with pytest.raises(BContractError):
                    env["p"](n)
            else:
                assert env["p"](n) == expected
            if n <= caller:
                assert env["rate"](n) == 0.0
            elif not satisfies:
                with pytest.raises(BContractError):
                    env["rate"](n)
            else:
                reached_nonzero.append(expected != 0)
                if expected:
                    assert env["rate"](n) == 6 / expected
                else:
                    with pytest.raises(ZeroDivisionError):
                        env["rate"](n)
        for status, outcomes in [(post, all_post), (nonzero, reached_nonzero)]:
            assert outcomes
            if status == "proved":
                assert all(outcomes), (cutoff, declared, caller, outcomes)
            if status == "refuted":
                assert not any(outcomes), (cutoff, declared, caller, outcomes)
        statuses["post", post] += 1
        statuses["nonzero", nonzero] += 1
    for kind in ["post", "nonzero"]:
        assert statuses[kind, "proved"] > 0 and statuses[kind, "unknown"] > 0


def test_rule_uses_the_declared_parameter_position_even_with_two_integer_arguments():
    compiled = compile_b("""
fn gate(noise: Int, trigger: Int) -> Int ensures trigger <= 0 or result > 0 = if trigger > 0 then trigger else 0
fn right(n: Int) -> Float requires n > 0 = 1 / gate(0, n)
fn wrong(n: Int) -> Float requires n > 0 = 1 / gate(n, 0)
""")
    assert check(compiled.analysis, "right", "nonzero").status == "proved"
    assert check(compiled.analysis, "wrong", "nonzero").status != "proved"
    env = execute(compiled)
    assert env["right"](2) == 0.5
    with pytest.raises(ZeroDivisionError):
        env["wrong"](2)


def test_eight_rules_fit_the_budget():
    rules = " and ".join(f"(x <= {k} or result > 0)" for k in range(8))
    compiled = compile_b(provider(law=rules) + "fn f(n: Int) -> Float requires n > 0 = 1 / p(n)")
    assert check(compiled.analysis, "p", "ensures").status == "proved"
    assert check(compiled.analysis, "f", "nonzero").status == "proved"


def test_all_integer_comparison_pairs_against_independent_semantics():
    operators = {"<": operator.lt, "<=": operator.le, ">": operator.gt,
                 ">=": operator.ge, "==": operator.eq, "!=": operator.ne}
    opposite = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "==": "!=", "!=": "=="}
    bodies = [("x", lambda x: x), ("-x", lambda x: -x),
              ("if x >= 0 then x else 0", lambda x: max(0, x))]

    # For each law run both its natural caller and a caller whose guard can
    # admit a different domain. Some failed provider checks prevent take().
    for left, right, (body, evaluate), natural in product(operators, operators, bodies, (True, False)):
        caller = opposite[left] if natural else ">="
        compiled = compile_b(f"""
fn p(x: Int) -> Int requires -3 <= x and x <= 3 ensures x {left} 0 or result {right} 0 = {body}
fn take(v: Int) -> Int requires v {right} 0 = v
fn use(n: Int) -> Int requires -3 <= n and n <= 3 = if n {caller} 0 then take(p(n)) else 0
""")
        ns = execute(compiled)
        post_results, reached_calls = [], []
        for n in range(-3, 4):
            value = evaluate(n)
            good = operators[left](n, 0) or operators[right](value, 0)
            post_results.append(good)
            if good:
                assert ns["p"](n) == value
            else:
                with pytest.raises(BContractError):
                    ns["p"](n)

            if not operators[caller](n, 0):
                assert ns["use"](n) == 0
                continue
            accepted = operators[right](value, 0)
            if good:
                reached_calls.append(accepted)
            if good and accepted:
                assert ns["use"](n) == value
            else:
                with pytest.raises(BContractError):
                    ns["use"](n)

        for obligation, results in [(check(compiled.analysis, "p", "ensures"), post_results),
                                    (check(compiled.analysis, "use", "requires", "take"), reached_calls)]:
            if results and obligation.status == "proved":
                assert all(results), (left, right, body, caller)
            if results and obligation.status == "refuted":
                assert not any(results), (left, right, body, caller)


def test_unconditional_wrapper_retains_the_proof_origin_of_its_public_guarantee():
    compiled = compile_b("""
fn p(x: Int) -> Int ensures x <= 0 or result > 0 = x
fn w(v: Int) -> Int requires v > 0 ensures result > 0 = p(v)
fn f(n: Int) -> Float requires n > 0 = 1 / w(n)
""")
    baseline = analyze(compiled.ir, conditional_guarantees=False)
    assert check(baseline, "f", "nonzero").status == "unknown"
    exported = check(compiled.analysis, "f", "nonzero")
    assert exported.status == "proved" and exported.proof_method == "conditional-guarantee"
    assert execute(compiled)["f"](2) == 0.5


def test_one_false_rule_prevents_exporting_a_sibling_rule():
    compiled = compile_b("""
fn p(x: Int) -> Int ensures (x <= 0 or result > 0) and (x >= 0 or result > 0) = x
fn use(n: Int) -> Float requires n > 0 = 1 / p(n)
""")
    assert check(compiled.analysis, "p", "ensures").status == "unknown"
    assert check(compiled.analysis, "use", "nonzero").status == "unknown"
    env = execute(compiled)
    assert env["use"](1) == 1.0
    with pytest.raises(BContractError):
        env["p"](-1)


def test_conservation_law_needs_more_than_signs():
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / "examples" / "conservation.bee"
    transfer = example.read_text()
    for program, excess in ((transfer, 0), (transfer.replace("= booked + 1", "= booked + 2"), 1)):
        built = compile_b(program)
        statuses = {o.target: o.status for o in built.analysis.obligations if o.kind == "ensures"}
        assert statuses == {"free_after": "proved", "booked_after": "proved", "accounted": "unknown"}
        functions = {}
        exec(built.code, functions)
        for free in range(1, 11):
            for booked in range(10):
                expected = free + booked
                actual = functions["free_after"](free) + functions["booked_after"](booked)
                assert actual - expected == excess
                if excess:
                    with pytest.raises(BContractError):
                        functions["accounted"](free, booked)
                else:
                    assert functions["accounted"](free, booked) == expected
