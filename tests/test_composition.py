"""Check the public obligation report against modular contracts and actual B execution."""
from __future__ import annotations

import sys

import pytest

from b_lang.compiler import compile_b
from b_lang.composition import analyze
from b_lang.runtime import BContractError


def obligation(report, caller, kind, target):
    matches = [
        item for item in report.obligations
        if (item.caller, item.kind, item.target) == (caller, kind, target)
    ]
    assert len(matches) == 1, (caller, kind, target, matches)
    return matches[0]


def runtime(compiled):
    namespace = {}
    exec(compiled.code, namespace, namespace)
    return namespace


def counting_program(contract, body):
    return f"""
fn count(n: Int) -> Int pure requires n >= 0 ensures result {contract} = {body}
fn total(n: Int) -> Int pure requires n >= 0 ensures result >= 10 = count(n) + 10
fn ratio(n: Int) -> Float pure requires n >= 0 = 12 / count(n)
"""


def test_weaker_interface_invalidates_only_the_dependent_guarantee():
    strong = compile_b(counting_program("> 0", "n + 1"))
    # Keep the implementation identical to isolate the public contract edit.
    weak = compile_b(counting_program(">= 0", "n + 1"))
    before, after = analyze(strong.ir), analyze(weak.ir)
    old_divisor = obligation(before, "ratio", "nonzero", "div")
    new_divisor = obligation(after, "ratio", "nonzero", "div")
    assert old_divisor.status == "proved" and new_divisor.status == "unknown"
    assert old_divisor.site == new_divisor.site
    assert "count" in old_divisor.dependencies
    for report in (before, after):
        assert obligation(report, "total", "ensures", "total").status == "proved"
        assert obligation(report, "total", "requires", "count").status == "proved"
        assert obligation(report, "ratio", "requires", "count").status == "proved"
    assert runtime(strong)["ratio"](0) == runtime(weak)["ratio"](0) == 12.0

    # The weaker interface now admits a real implementation that returns zero.
    changed = compile_b(counting_program(">= 0", "n"))
    env = runtime(changed)
    assert env["total"](0) == 10
    with pytest.raises(ZeroDivisionError):
        env["ratio"](0)


def test_proof_crosses_two_native_call_boundaries():
    source = """
fn increment(x: Int) -> Int pure requires x >= 0 ensures result > 0 = x + 1
fn forward(x: Int) -> Int pure requires x >= 0 ensures result > 0 = increment(x)
fn use(x: Int) -> Float pure requires x >= 0 = 10 / forward(x)
"""
    compiled = compile_b(source)
    report = analyze(compiled.ir)
    first = obligation(report, "forward", "ensures", "forward")
    second = obligation(report, "use", "nonzero", "div")
    assert first.status == second.status == "proved"
    assert "increment" in first.dependencies and "forward" in second.dependencies
    env = runtime(compiled)
    for x in range(7):
        assert env["use"](x) == 10 / (x + 1)


@pytest.mark.parametrize("threshold,expected", [(0, "proved"), (2, "unknown"), (3, "refuted")])
def test_report_agrees_with_all_inputs_of_a_finite_call_domain(threshold, expected):
    source = f"""
fn shift(x: Int) -> Int requires 0 <= x and x <= 2 ensures 1 <= result and result <= 3 = x + 1
fn accept(v: Int) -> Int requires v > {threshold} = v
fn use(x: Int) -> Int requires 0 <= x and x <= 2 = accept(shift(x))
"""
    compiled = compile_b(source)
    checked = obligation(analyze(compiled.ir), "use", "requires", "accept")
    env = runtime(compiled)
    successes = []
    for x in range(3):
        if x + 1 > threshold:
            assert env["use"](x) == x + 1
            successes.append(True)
        else:
            with pytest.raises(BContractError, match="Precondition"):
                env["use"](x)
            successes.append(False)
    observed = "proved" if all(successes) else "refuted" if not any(successes) else "unknown"
    assert checked.status == observed == expected


def test_an_unproved_runtime_postcondition_cannot_be_exported():
    compiled = compile_b("""
fn maybe(x: Int) -> Int ensures result > 0 = x
fn quotient(x: Int) -> Float = 1 / maybe(x)
""")
    report = analyze(compiled.ir)
    assert obligation(report, "maybe", "ensures", "maybe").status == "unknown"
    assert obligation(report, "quotient", "nonzero", "div").status == "unknown"
    with pytest.raises(BContractError, match="Postcondition"):
        runtime(compiled)["quotient"](0)


def test_recursive_contract_cannot_prove_itself():
    compiled = compile_b("""
fn cycle(x: Int) -> Int ensures result > 0 = cycle(x)
fn quotient(x: Int) -> Float = 1 / cycle(x)
""")
    report = analyze(compiled.ir)
    assert obligation(report, "cycle", "ensures", "cycle").status == "unknown"
    assert obligation(report, "quotient", "nonzero", "div").status == "unknown"


def test_foreign_type_cannot_supply_a_value_guarantee(tmp_path, monkeypatch):
    module = "b_composition_leaf"
    (tmp_path / (module + ".py")).write_text(
        'raise RuntimeError("foreign implementation executed")\n'
        'def sample(x: int) -> int:\n    return 1\n'
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    compiled = compile_b(f"""
use py:{module} as ext
fn sample(x: Int) -> Int ensures result > 0 = ext.sample(x)
fn quotient(x: Int) -> Float = 1 / sample(x)
""")
    report = analyze(compiled.ir)
    assert obligation(report, "sample", "ensures", "sample").status == "unknown"
    assert obligation(report, "quotient", "nonzero", "div").status == "unknown"
    assert module not in sys.modules


@pytest.mark.parametrize("operation,result_type", [("/", "Float"), ("%", "Int")])
def test_nonzero_guard_on_named_denominator(operation, result_type):
    compiled = compile_b(
        f"fn safe(x: Int) -> {result_type} = if x == 0 then 0 else 10 {operation} x"
    )
    target = "div" if operation == "/" else "mod"
    assert obligation(analyze(compiled.ir), "safe", "nonzero", target).status == "proved"
    env = runtime(compiled)
    assert env["safe"](0) == 0
    for x in [-3, -1, 1, 2]:
        expected = 10 / x if operation == "/" else 10 % x
        assert env["safe"](x) == expected


def test_float_boundary_cannot_export_integer_precision():
    compiled = compile_b("""
fn widen(x: Int) -> Float requires x == 9007199254740993 ensures result == 9007199254740993 = x
fn caller(x: Int) -> Float requires x == 9007199254740993 = widen(x)
""")
    report = analyze(compiled.ir)
    assert obligation(report, "widen", "ensures", "widen").status == "unknown"
    with pytest.raises(BContractError, match="Postcondition"):
        runtime(compiled)["caller"](9007199254740993)


def test_two_calls_to_same_function_keep_distinct_obligations():
    compiled = compile_b("""
fn take(x: Int) -> Int requires x >= 0 = x
fn pair(x: Int) -> Int requires x >= 0 = take(x + 1) + take(x - 1)
""")
    sites = [
        site for site in analyze(compiled.ir).obligations
        if site.caller == "pair" and site.kind == "requires" and site.target == "take"
    ]
    assert {site.status for site in sites} == {"proved", "unknown"}
    assert len({site.site for site in sites}) == 2
    env = runtime(compiled)
    assert env["pair"](1) == 2
    with pytest.raises(BContractError):
        env["pair"](0)


def test_provably_dead_arm_does_not_report_a_refuted_division():
    compiled = compile_b("""
fn skip(x: Int) -> Float requires x == 0 = if x == 0 then 1.0 else 8 / x
""")
    report = analyze(compiled.ir)
    assert all(site.status != "refuted" for site in report.obligations)
    assert runtime(compiled)["skip"](0) == 1.0


def test_raising_dynamic_comparison_cannot_certify_its_postcondition():
    compiled = compile_b("fn f(x: Any) -> Int ensures x < x or true = 1")
    assert obligation(analyze(compiled.ir), "f", "ensures", "f").status == "unknown"
    with pytest.raises(TypeError):
        runtime(compiled)["f"]({})


def test_provenance_includes_producer_needed_to_establish_intermediate_precondition():
    compiled = compile_b("""
fn source(n: Int) -> Int requires n >= 0 ensures result > 0 = n + 1
fn positive(x: Int) -> Int requires x > 0 ensures result > 0 = x
fn ratio(n: Int) -> Float requires n >= 0 = 1 / positive(source(n))
""")
    division = obligation(analyze(compiled.ir), "ratio", "nonzero", "div")
    assert division.status == "proved"
    assert set(division.dependencies) == {"source", "positive"}
