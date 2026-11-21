import json
from pathlib import Path
from b_lang.cli import main


def test_bsrc_is_preferred_source_and_check_json(tmp_path: Path, capsys):
    example = tmp_path / 'hello.bsrc'
    example.write_text('print if true then 42 else 13\n', encoding='utf-8')
    assert main(['check', str(example), '--strict', '--json']) == 0
    record = json.loads(capsys.readouterr().out)
    assert record['status'] == 'accepted'
    assert record['spec'] == '0.8'
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
