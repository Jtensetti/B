import json
from pathlib import Path
from b_lang.cli import main


def test_bsrc_is_preferred_source_and_check_json(tmp_path: Path, capsys):
    example = tmp_path / 'hello.bsrc'
    example.write_text('print if true then 42 else 13\n', encoding='utf-8')
    assert main(['check', str(example), '--strict', '--json']) == 0
    record = json.loads(capsys.readouterr().out)
    assert record['status'] == 'accepted'
    assert record['spec'] == '0.28'
    assert record['diagnostics'] == []
    assert record['behavior_proven'] is False


def test_old_b_extension_remains_supported(tmp_path: Path, capsys):
    example = tmp_path / 'legacy.b'
    example.write_text('print 42\n', encoding='utf-8')
    assert main(['run', str(example)]) == 0
    assert capsys.readouterr().out.strip() == '42'


def test_reject_unrelated_extensions(tmp_path: Path, capsys):
    example = tmp_path / 'not_b.py'
    example.write_text('print 42\n', encoding='utf-8')
    assert main(['check', str(example), '--json']) == 1
    record = json.loads(capsys.readouterr().out)
    assert record['error']['code'] == 'E_EXTENSION'


def test_json_error_is_machine_readable(tmp_path: Path, capsys):
    example = tmp_path / 'fail.bsrc'
    example.write_text('let n: Int = "bad"\n', encoding='utf-8')
    assert main(['check', str(example), '--json']) == 1
    record = json.loads(capsys.readouterr().out)
    assert record['status'] == 'rejected'
    assert record['error']['code'] == 'E_TYPE'


def test_json_contracts_report_trusted_assumptions(tmp_path: Path, capsys):
    example = tmp_path / 'contract.bsrc'
    example.write_text('use py:statistics as stats\nforeign stats.median(List[Float]) -> Float\nprint stats.median([1,2,3])', encoding='utf-8')
    assert main(['check', str(example), '--strict', '--json']) == 0
    record = json.loads(capsys.readouterr().out)
    assert record['assumed_foreign_contracts'] == ['py:statistics.median(List[Float]) -> Float']


def test_strict_json_rejection_includes_diagnostic_details(tmp_path: Path, capsys):
    path = tmp_path / 'untyped.bsrc'
    path.write_text('use py:json as json\nprint json.dumps([1,2,3])', encoding='utf-8')
    assert main(['check', str(path), '--strict', '--json']) == 1
    obj = json.loads(capsys.readouterr().out)
    assert obj['error']['code'] == 'E_STRICT'
    assert any(d['code'] == 'W_UNCHECKED_FOREIGN' for d in obj['diagnostics'])


def test_compare_revisions_and_gate_proofs(capsys):
    fixtures = Path(__file__).resolve().parents[1] / "examples" / "revisions"
    before, after = (str(fixtures / f"count-{suffix}.bee") for suffix in ("positive", "zero"))
    assert main(["check", before, "--require-proofs", "--strict", "--json"]) == 0
    old = json.loads(capsys.readouterr().out)
    statuses = {f["name"]: f["postcondition_status"] for f in old["function_contracts"]}
    assert statuses["total_with_reserve"] == "proved-composition"
    assert main(["check", after, "--require-proofs", "--json"]) == 1
    new = json.loads(capsys.readouterr().out)
    assert new["error"]["code"] == "E_PROOF_REQUIRED"
    unresolved = [o for o in new["contract_analysis"]["obligations"] if o["status"] != "proved"]
    assert [(o["kind"], o["caller"], o["dependencies"]) for o in unresolved] == [
        ("nonzero", "cost_per_item", ["count"])
    ]
    assert main(["impact", before, after, "--json"]) == 0
    impact = json.loads(capsys.readouterr().out)
    assert [(r["after"]["caller"], r["after"]["status"]) for r in impact["changes"]
            if r["change"] == "lost-proof"] == [("cost_per_item", "unknown")]
    assert impact["unchanged"] > 0


def test_impact_distinguishes_removed_obligation_from_a_proof(tmp_path, capsys):
    before = tmp_path / "old.bee"
    before.write_text("fn ratio(n: Int) -> Float = 1 / n")
    after = tmp_path / "new.bee"
    after.write_text("fn ratio(n: Int) -> Float = 0.0")
    assert main(["impact", str(before), str(after), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [c["change"] for c in report["changes"]] == ["removed"]
    after.write_text("fn =")
    assert main(["impact", str(before), str(after), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["revision"] == "after" and report["error"]["code"] == "E_SYNTAX"


def test_conditional_rules_guidance_and_gravity_example(capsys):
    fixtures = Path(__file__).resolve().parents[1] / "examples" / "mechanics"
    model = str(fixtures / "flight.bee")
    assert main(["check", model, "--require-proofs", "--strict", "--json"]) == 0
    on = json.loads(capsys.readouterr().out)
    assert all(o["status"] == "proved" for o in on["contract_analysis"]["obligations"])
    assert any(f["postcondition_status"] == "proved-conditional" for f in on["function_contracts"])
    assert "guidance" not in on
    assert main(["check", model, "--no-conditional-guarantees", "--require-proofs", "--explain", "--json"]) == 1
    off = json.loads(capsys.readouterr().out)
    assert off["conditional_guarantees"] is False
    assert off["error"]["code"] == "E_PROOF_REQUIRED"
    assert any(o["kind"] == "nonzero" for o in off["guidance"])
    assert main(["impact", model, str(fixtures / "rebound.bee"), "--json"]) == 0
    diff = json.loads(capsys.readouterr().out)
    assert {(r["after"]["caller"], r["after"]["kind"]) for r in diff["changes"]
            if r["change"] == "lost-proof"} == {
                ("velocity", "ensures"), ("descent_speed", "ensures"), ("time_per_unit", "nonzero")
            }


def test_ideal_flight_against_tick_oracle_and_rebound_counterexample():
    import pytest
    from b_lang.cli import compile_file
    from b_lang.runtime import BContractError

    fixtures = Path(__file__).resolve().parents[1] / "examples" / "mechanics"
    ideal, rebounding = {}, {}
    exec(compile_file(fixtures / "flight.bee").code, ideal)
    exec(compile_file(fixtures / "rebound.bee").code, rebounding)
    speed = 3
    for tick in range(12):
        assert ideal["velocity"](tick) == speed
        if tick > 3:
            assert ideal["time_per_unit"](tick) == -1 / speed
        if tick < 5:
            assert rebounding["velocity"](tick) == speed
        speed -= 1
    with pytest.raises(BContractError):
        rebounding["velocity"](5)


def test_a_python_module_next_to_the_program_can_be_imported(tmp_path, capsys, monkeypatch):
    import sys
    from b_lang.cli import main
    (tmp_path / "carrier_next_to_program.py").write_text("def rate(weight_lb: float) -> float:\n    return 2 * weight_lb\n")
    program = tmp_path / "quote.bee"
    program.write_text("use py:carrier_next_to_program as carrier\nprint carrier.rate(2.0)\n")
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert main(["run", str(program)]) == 0
    assert capsys.readouterr().out.strip() == "4.0"
