import itertools

import pytest

from b_lang.compiler import compile_b
from b_lang.revision_witness import compare_functions, evaluate_rule, evaluate_scalar


def compare(left, right, *names):
    return compare_functions(compile_b(left).ir, compile_b(right).ir, names)


def test_text_equality_needs_a_fresh_value_per_argument():
    base = 'fn route(a: Text, b: Text) -> Text pure = if a == "fixed" then "fixed" else a'
    candidate = base.replace('else a', 'else b')
    answer = compare(base, candidate, "route")
    assert answer["status"] == "counterexample"
    assert answer["arguments"]["a"] != answer["arguments"]["b"]
    assert answer["expected"] == answer["arguments"]["a"]
    assert answer["actual"] == answer["arguments"]["b"]

    same = 'fn same(a: Text, b: Text) -> Bool pure = a == b'
    answer = compare(same, same.replace("a == b", "true"), "same")
    assert answer["arguments"]["a"] != answer["arguments"]["b"]


@pytest.mark.parametrize("kind,literal", [("Text", '"_other_0"'), ("Int", '0')])
def test_complete_equality_classes_inside_native_call_closure(kind, literal):
    program = f'''fn tagged(a: {kind}) -> Bool pure = a == {literal}
fn choose(a: {kind}, b: {kind}, flip: Bool) -> {kind} pure =
    if tagged(a) and flip then b else a'''
    changed = program.replace("tagged(a) and flip then b else a",
                              "not (flip and tagged(a)) then a else b")
    answer = compare(program, changed, "choose")
    assert answer == {"status": "proved", "cases": 18, "method": "exhaustive-scalar-classes"}


def test_real_counterexample_through_two_native_calls():
    base = '''fn eligible(child: Bool, day: Text) -> Bool pure = child and day == "sun"
fn seats(child: Bool, day: Text) -> Int pure = 1
fn remaining(n: Int, child: Bool, day: Text) -> Int pure = n - seats(child, day)'''
    altered = base.replace("Int pure = 1", "Int pure = if eligible(child, day) then 2 else 1")
    result = compare(base, altered, "remaining")
    assert result["status"] == "counterexample"
    assert result["arguments"]["child"] is True and result["arguments"]["day"] == "sun"
    assert result["actual"] + 1 == result["expected"]


def test_integer_arithmetic_samples_cannot_prove_equivalence():
    base = "fn offset(n: Int) -> Int pure = n + 1"
    answer = compare(base, base.replace("n + 1", "1 + n"), "offset")
    assert answer["status"] == "unknown"
    assert answer["cases"] > 0


def test_arithmetic_still_provable_over_finite_domains():
    base = '''fn amount(big: Bool, day: Text) -> Int pure =
    if day == "sat" and big then 50 + 10 else 20'''
    changed = base.replace("50 + 10", "60")
    assert compare(base, changed, "amount")["status"] == "proved"


def test_concrete_rule_argument_types_and_unknowns():
    raw = 'fn adult(n: Int, day: Text) -> Bool pure = n > 17 and day == "mon"'
    program = compile_b(raw).ir
    assert evaluate_rule(program, "adult", (18, "mon")) is True
    assert evaluate_rule(program, "adult", (16, "mon")) is False
    assert evaluate_rule(program, "adult", (True, "mon")) is None
    assert evaluate_rule(program, "adult", (18,)) is None
    contracted = compile_b(raw.replace("pure =", "pure requires n >= 0 =")).ir
    assert evaluate_rule(contracted, "adult", (18, "mon")) is None


@pytest.mark.parametrize(("kind", "expr", "answer"), [
    ("Int", "3 * 8", (True, 24)), ("Bool", "false", (True, False)),
    ("Text", '"1"', (True, "1")), ("Float", "1.0", (False, None)),
    ("None", "none", (False, None)),
])
def test_scalar_observation_for_ordered_console_output(kind, expr, answer):
    ir = compile_b(f"fn show() -> {kind} pure = {expr}").ir
    assert evaluate_scalar(ir, "show", ()) == answer


@pytest.mark.parametrize("src", [
    'fn eq(x: Float) -> Bool pure = x == 0.0',
    'fn eq(x: Int) -> Bool pure requires x > 0 = x == 3',
    'let fixed = 8\nfn eq(x: Int) -> Bool = x == fixed',
    'fn eq(x: Text) -> Bool pure = (x + "a") == "a"',
    'use py:math as m\nfn eq(x: Int) -> Bool = m.sqrt(x) == 1.0',
])
def test_unsupported_closures_never_masquerade_as_proof(src):
    result = compare(src, src, "eq")
    assert result["status"] == "unknown" and result["cases"] == 0


def test_more_possible_input_tuples_than_budget():
    names = [f"a{i}" for i in range(13)]
    inputs = ", ".join(f"{n}: Bool" for n in names)
    source = f"fn f({inputs}) -> Bool pure = a0"
    changed = source.replace("= a0", "= not (not a0)")
    assert compare(source, changed, "f")["status"] == "unknown"


def test_ordered_sorts_are_not_certified_by_equality_samples():
    base = 'fn compare(a: Text) -> Bool pure = a < "z"'
    # Both predicates agree at "z" and generated fresh values, but disagree at "za".
    changed = base.replace('a < "z"', 'a != "z"')
    result = compare(base, changed, "compare")
    assert result["status"] == "unknown"


def test_each_concrete_counterexample_matches_the_compiled_backend():
    variants = ["a == b", 'a == "fixed"', 'b == "_other_0"', "a != b", "flag"]
    signature = "fn choice(a: Text, b: Text, flag: Bool) -> Bool pure = "
    for lhs, rhs in itertools.combinations(variants, 2):
        left, right = (compile_b(signature + body) for body in (lhs, rhs))
        result = compare_functions(left.ir, right.ir, ["choice"])
        assert result["status"] == "counterexample"
        for program, reported in [(left, "expected"), (right, "actual")]:
            exported = {}
            exec(program.code, exported)
            assert exported["choice"](**result["arguments"]) is result[reported]
