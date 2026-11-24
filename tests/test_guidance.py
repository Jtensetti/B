import sys

import pytest

from b_lang.compiler import compile_b
from b_lang.guidance import guidance


def explain(source):
    compiled = compile_b(source)
    return guidance(compiled.ir, compiled.analysis)


@pytest.mark.parametrize("operator, result_type, target", [("/", "Float", "div"), ("%", "Int", "mod")])
def test_guarding_the_input_identifies_the_actual_divisor(operator, result_type, target):
    rows = explain(f"""
fn count(raw: Int) -> Int pure ensures result >= 0 = 1
fn cost(total: Int, raw: Int) -> {result_type} pure = if raw == 0 then 0 else total {operator} count(raw)
""")
    row, = rows
    assert (row["caller"], row["site"], row["target"], row["status"]) == ("cost", "body.else", target, "unknown")
    assert row["denominator"] == "count(raw)"
    assert "branch tests raw" in row["detail"]
    assert "once" in row["suggestion"] and "specified zero case" in row["suggestion"]


def test_proved_and_non_divisor_obligations_do_not_generate_advice():
    assert explain("""
fn fixed(x: Int) -> Float = if x == 0 then 0.0 else 1 / x
fn uncertain(x: Int) -> Int ensures result > 0 = x
""") == []


def test_float_with_a_zero_guard_proves_the_division():
    assert explain("fn f(x: Float) -> Float = if 0.0 < x then 10.0 / x else 0.0") == []


def test_unknown_foreign_behavior_is_never_run_or_assumed_pure(tmp_path, monkeypatch):
    name = "b_explain_external"
    (tmp_path / f"{name}.pyi").write_text("def count(v: int) -> int: ...\n")
    (tmp_path / f"{name}.py").write_text("raise RuntimeError('must not execute')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    row, = explain(f"""
use py:{name} as ext
fn consume(v: Int) -> Float = if ext.count(v) == 0 then 0.0 else 8 / ext.count(v)
""")
    assert name not in sys.modules
    assert row["denominator"] == "ext.count(v)"
    assert "separate calls" in row["detail"]


def test_dynamic_top_level_divisor_receives_typed_boundary_advice():
    row, = explain('use py:json as j\nlet quotient = 12 / j.loads("0")')
    assert row["caller"] == "<module>" and row["site"] == "let.quotient"
    assert row["status"] == "unknown" and row["type"] == "Any"
    assert "type at the boundary" in row["suggestion"]


def test_refuted_report_is_conditional_on_reaching_the_operation():
    row, = explain("""
fn zero(v: Int) -> Int ensures result == 0 = 0
fn reduce(v: Int) -> Int = if v < 0 then v % zero(v) else 0
""")
    assert row["status"] == "refuted"
    assert "whenever this operation is reached" in row["detail"]


def test_nested_module_sites_and_nested_guards_map_to_their_own_operands():
    source = """
fn count(x: Int) -> Int = x
let x = count(50)
print x
print if not (x == 0) and x > 2 then 1 / (x % count(x)) else 0
"""
    rows = explain(source)
    assert {row["site"]: row["denominator"] for row in rows} == {
        "print.1.then": "(x % count(x))", "print.1.then.1": "count(x)"
    }
    inner = next(row for row in rows if row["target"] == "mod")
    assert "branch tests x" in inner["detail"]


@pytest.mark.parametrize("contract,test,required", [
    ("pitch > 0", "raw > 0", "produce(raw) > 0"),
    ("0 > pitch", "raw < 0", "produce(raw) < 0"),
    ("pitch >= -8", "raw >= -8", "produce(raw) >= -8"),
])
def test_native_argument_guidance_maps_the_constrained_formal(contract, test, required):
    row, = explain(f"""
fn produce(v: Int) -> Int = v + 1
fn tune(volume: Int, pitch: Int) -> Int requires {contract} = volume + pitch
fn adjust(raw: Int) -> Int = if {test} then tune(40, produce(raw)) else 1
""")
    assert (row["kind"], row["target"], row["parameter"]) == ("requires", "tune", "pitch")
    assert row["argument"] == "produce(raw)"
    assert row["actual_requirement"] == required
    assert row["status"] == "unknown" and "branch tests the producer's input raw" in row["detail"]
    assert "once" in row["suggestion"]


def test_refuted_argument_guidance_and_out_of_scope_preconditions():
    rows = explain("""
fn zero(v: Int) -> Int ensures result == 0 = 0
fn take(dummy: Int, z: Int) -> Int requires z < 0 = z
fn pair(x: Int, y: Int) -> Int requires x < y = x
fn use(v: Int) -> Int = take(v, zero(v)) + pair(v, v)
""")
    row, = rows
    assert row["status"] == "refuted" and row["argument"] == "zero(v)"
    assert "whenever this call is reached" in row["detail"]
    assert "outside the bound" in row["suggestion"]


def test_disabled_conditional_reasoning_only_suggests_available_repairs():
    compiled = compile_b("""
fn measure(x: Int) -> Int = x
fn tune(pitch: Int) -> Int requires pitch > 0 = pitch
fn adjust(raw: Int) -> Int = if raw > 0 then tune(measure(raw)) else raw
""", conditional_guarantees=False)
    row, = guidance(compiled.ir, compiled.analysis, conditional_guarantees=False)
    assert "test its result" in row["suggestion"]
    assert "contract" not in row["suggestion"]
    enabled, = guidance(compiled.ir, compiled.analysis)
    assert "contract relating" in enabled["suggestion"]
