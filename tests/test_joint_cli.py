import json
from pathlib import Path

from b_lang.cli import main
from b_lang.request_json import MAX_REQUEST_BYTES

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/intent"
GOOD, MIXED, RULE = (EXAMPLES / name for name in ("layout.bee", "compact.bee", "uniform.json"))


def run(capsys, source, *args, code=0):
    assert main(["check", str(source), "--json", *map(str, args)]) == code
    return json.loads(capsys.readouterr().out)


def test_joint_rule_is_opt_in_and_orthogonal_to_static_proof(capsys):
    assert "joint_checks" not in run(capsys, MIXED)
    passed = run(capsys, GOOD, "--strict", "--require-proofs", "--joint", RULE)
    assert passed["joint_checks"][0]["checked_pairs"] == 3
    assert passed["behavior_proven"] is False
    bad = run(capsys, MIXED, "--require-proofs", "--joint", RULE, code=1)
    assert bad["error"]["code"] == "E_JOINT_VIOLATED"
    row = bad["joint_checks"][0]
    assert row["failed_comparison"] == {"left_value": 2, "operator": "==", "right_value": 1}
    assert row["witness"]["left"]["inputs"] == {"rank": 0}
    assert main(["check", str(MIXED), "--joint", str(RULE)]) == 1
    error = capsys.readouterr().err
    assert "gap(rank=0) -> 2" in error and "gap(rank=1) -> 2" in error
    assert "required 2 == 1" in error


def test_one_submission_reports_separate_failing_and_passing_requirements(capsys, tmp_path):
    invalid, large = tmp_path / "typo.json", tmp_path / "large.json"
    invalid.write_text('{"left":{}, "left":{}}')
    large.write_bytes(b" " * (MAX_REQUEST_BYTES + 1))
    result = run(capsys, GOOD, "--joint", invalid, "--joint", large, "--joint", RULE, code=1)
    assert [r["status"] for r in result["joint_checks"]] == ["error", "error", "passed"]
    assert [r["code"] for r in result["joint_checks"][:2]] == ["E_JOINT_INPUT", "E_JOINT_LIMIT"]


def test_an_empty_selected_grid_cannot_pass(capsys, tmp_path):
    no_pairs = tmp_path / "excluded.json"
    law = json.loads(RULE.read_text())
    law["where"] = "false"
    no_pairs.write_text(json.dumps(law))
    data = run(capsys, GOOD, "--joint", no_pairs, code=1)
    assert data["error"]["code"] == "E_JOINT_INCONCLUSIVE"
    assert data["joint_checks"][0]["checked_pairs"] == 0
