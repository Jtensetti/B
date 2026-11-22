"""An observed rule is a proposal about code, never an implicit requirement."""
import sys

from b_lang.compiler import compile_b
from b_lang.discovery_contracts import discover


def run(compiled):
    namespace = {}
    exec(compiled.code, namespace)
    return namespace


def test_discovery_reports_a_unique_law_without_modifying_the_module():
    before = """
fn free_after(x: Int) -> Int pure requires x > 0 = x - 1
fn booked_after(y: Int) -> Int pure requires y >= 0 = y + 1
fn total(x: Int, y: Int) -> Int pure requires x > 0 and y >= 0 = free_after(x) + booked_after(y)
"""
    for code, excess in [(before, 0), (before.replace("= y + 1", "= y + 2"), 1)]:
        compiled = compile_b(code)
        old_ir = compiled.ir.to_dict()
        old_analysis = compiled.analysis.to_dict()
        report = discover(compiled.ir, "total")
        assert report["status"] == "candidate" and report["proved"] is False
        assert report["candidate_form"] == {"coefficients": {"x": 1, "y": 1}, "constant": excess}
        assert report["proposed_contract"].startswith("ensures ")
        assert compiled.ir.to_dict() == old_ir and compiled.analysis.to_dict() == old_analysis
        assert not any(o.kind == "ensures" for o in compiled.analysis.obligations)
        env = run(compiled)
        assert env["total"](3, 5) == 8 + excess
        for case in report["observations"]:
            x, y = case["inputs"]["x"], case["inputs"]["y"]
            assert x > 0 and y >= 0 and case["result"] == x + y + excess


def test_equal_inputs_keep_competing_explanations_alive():
    compiled = compile_b("fn f(x: Int, y: Int) -> Int requires x == y = x")
    report = discover(compiled.ir, "f")
    assert report["status"] == "ambiguous" and len(report["survivors"]) >= 2
    assert report["candidate_form"] is None and report["proposed_contract"] is None
    assert all(o["inputs"]["x"] == o["inputs"]["y"] for o in report["observations"])
    assert report["proved"] is False


def test_no_valid_sample_is_no_evidence():
    compiled = compile_b("fn f(x: Int) -> Int requires x > 1000000 = x")
    report = discover(compiled.ir, "f")
    # Samplers may derive boundary values instead of always probing near zero.
    # Either way every observation must be valid, and silence can supply no law.
    assert all(o["inputs"]["x"] > 1000000 for o in report["observations"])
    if not report["observations"]:
        assert report["status"] == "inconclusive"
        assert report["candidate_form"] is None and report["proved"] is False

    empty = compile_b("fn empty(x: Int) -> Int requires x * x < 0 = x")
    impossible = discover(empty.ir, "empty")
    assert not impossible["observations"] and impossible["status"] in {"unsupported", "inconclusive"}
    assert impossible["candidate_form"] is None and impossible["proved"] is False


def test_held_out_input_can_refute_an_apparent_identity():
    compiled = compile_b("fn f(x: Int) -> Int = if x == 17 then x + 1 else x")
    report = discover(compiled.ir, "f")
    assert report["status"] == "no-match" and report["candidate_form"] is None
    assert any(row["phase"] == "challenge" and row["inputs"] == {"x": 17}
               and row["expected"] == 17 and row["observed"] == 18
               for row in report["counterexamples"])


def test_an_input_outside_all_queries_exposes_an_accidental_fit():
    identity = discover(compile_b("fn f(x: Int) -> Int = x").ir, "f")
    samples = {o["inputs"]["x"] for o in identity["observations"]}
    assert samples
    unseen = max(samples) + 100000
    compiled = compile_b(f"fn f(x: Int) -> Int = if x == {unseen} then x + 1 else x")
    report = discover(compiled.ir, "f")
    # A search that deliberately challenges literals in the source may detect it;
    # otherwise the proposal must remain visibly observational.
    if report["status"] == "candidate":
        assert report["candidate_form"] == {"coefficients": {"x": 1}, "constant": 0}
        assert report["proved"] is False
    else:
        assert report["status"] == "no-match"
    assert run(compiled)["f"](unseen) == unseen + 1


def test_observations_distinguish_the_executed_body_from_an_erroneous_contract():
    compiled = compile_b("fn booked(x: Int) -> Int ensures result == x + 1 = x + 2")
    report = discover(compiled.ir, "booked")
    violation = report["declared_counterexample"]
    assert violation and violation["result"] == violation["inputs"]["x"] + 2
    assert violation["result"] != violation["inputs"]["x"] + 1
    assert report["proved"] is False
    assert all(o["result"] == o["inputs"]["x"] + 2 for o in report["observations"])


def test_foreign_recursive_and_float_functions_cannot_be_used_as_oracles(tmp_path, monkeypatch):
    module = "b_affine_foreign_leaf"
    (tmp_path / (module + ".py")).write_text(
        'raise RuntimeError("foreign import executed")\n'
        'def sample(x: int) -> int:\n    return x\n'
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    compiled = compile_b(f"""
use py:{module} as ext
fn extcall(x: Int) -> Int = ext.sample(x)
fn transitive(x: Int) -> Int = extcall(x)
fn recurse(x: Int) -> Int = recurse(x)
fn widen(x: Int) -> Float = x
""")
    for name in ("extcall", "transitive", "recurse", "widen"):
        report = discover(compiled.ir, name)
        assert report["status"] == "unsupported", name
        assert not report["observations"] and report["candidate_form"] is None
        assert report["proved"] is False
    assert module not in sys.modules


def test_failed_nested_precondition_is_reported_as_an_observation_failure():
    compiled = compile_b("""
fn pos(x: Int) -> Int requires x > 0 = x
fn f(x: Int) -> Int = pos(x)
""")
    report = discover(compiled.ir, "f")
    assert report["status"] == "inconclusive"
    assert report["proposed_contract"] is None and report["candidate_form"] is None
    failure = report["probe_failure"]
    assert failure["inputs"]["x"] <= 0 and "precondition" in failure["reason"]


def test_failed_nested_ensures_is_observed_even_when_target_contract_is_ignored():
    compiled = compile_b("""
fn shrink(x: Int) -> Int ensures result > 0 = x - 1
fn f(x: Int) -> Int = shrink(x)
""")
    report = discover(compiled.ir, "f")
    assert report["status"] == "inconclusive" and report["candidate_form"] is None
    assert report["probe_failure"]["inputs"]["x"] <= 1
    assert "postcondition" in report["probe_failure"]["reason"]
