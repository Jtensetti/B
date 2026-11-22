"""The public interface keeps behavioral evidence separate from contract intent."""
import json
from pathlib import Path

import pytest

from b_lang.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run_report(capsys, path, *args, code=0, function="accounted"):
    assert main(["discover", str(path), "--function", function, "--json", *args]) == code
    return json.loads(capsys.readouterr().out)


def test_booking_proposal_does_not_publish_or_edit_the_contract(capsys, tmp_path):
    original = (EXAMPLES / "conservation.bee").read_text()
    source = tmp_path / "booking.bee"
    source.write_text(original)
    data = run_report(capsys, source, "--expect", "result - booked == free")
    assert data["expectation"]["status"] == data["verification"]["status"] == "proved"
    assert data["proposal_origin"] == "current-implementation" and data["intent"] == "unspecified"
    assert data["verification"]["body_dependencies"] == ["booked_after", "free_after"]
    assert data["declared_audit"] == "no-observed-violation"
    assert "trace" not in data and data["survivors_count"] == 1
    detailed = run_report(capsys, source, "--trace")
    assert detailed["trace"]["proved"] is False
    assert {r["phase"] for r in detailed["trace"]["observations"]} == {"discovery", "challenge"}
    assert source.read_text() == original
    assert main(["check", str(source), "--require-proofs"]) == 1
    assert main(["check", str(EXAMPLES / "conservation-modular.bee"), "--strict", "--require-proofs"]) == 0


def test_bad_booking_law_can_be_proved_while_supplied_expectation_is_refuted(capsys, tmp_path):
    source = tmp_path / "drift.bee"
    source.write_text((EXAMPLES / "conservation.bee").read_text().replace("= booked + 1", "= booked + 2"))
    data = run_report(capsys, source, "--expect", "result == free + booked", code=1)
    assert data["proposed_contract"] == "ensures result == free + booked + 1"
    assert data["verification"]["status"] == "proved" and data["expectation"]["status"] == "refuted"
    assert data["declared_audit"] == "counterexample"
    row = data["expectation"]["counterexample"]
    assert row["expected"] == sum(row["inputs"].values()) and row["observed"] == row["expected"] + 1
    assert data["observed_value"] == "body-result-before-target-ensures"


def test_explicit_expectation_can_succeed_outside_proposal_family(capsys, tmp_path):
    src = tmp_path / "scale.bee"
    src.write_text("fn f(x: Int) -> Int = 2 * x\n")
    data = run_report(capsys, src, "--expect", "result == 2 * x", function="f")
    assert data["status"] == "no-match" and data["expectation"]["status"] == "proved"


def test_matching_samples_cannot_discharge_an_unseen_branch(capsys, tmp_path):
    src = tmp_path / "hidden.bee"
    src.write_text("fn f(x: Int) -> Int = if x == 10007 then x + 1 else x\n")
    data = run_report(capsys, src, "--expect", "result == x", function="f", code=1)
    assert data["status"] == "candidate"
    assert data["verification"]["status"] == data["expectation"]["status"] == "unknown"


@pytest.mark.parametrize("expression", ["result > free", "result == free\nprint 41", "result =="])
def test_unsupported_expectation_has_structured_error(capsys, expression):
    data = run_report(capsys, EXAMPLES / "conservation.bee", "--expect", expression, code=1)
    assert data["status"] == "rejected" and data["error"]["code"] == "E_EXPECT"


def test_reports_missing_name_and_unsupported_existing_contract(capsys, tmp_path):
    src = tmp_path / "audit.bee"
    src.write_text("fn f(x: Int) -> Int ensures result < 0.5 = x\n")
    data = run_report(capsys, src, function="f")
    assert data["declared_audit"] == "unsupported" and data["declared_counterexample"] is None
    assert run_report(capsys, src, function="absent", code=1)["error"]["code"] == "E_FUNCTION"


def test_no_affine_refutation_for_empty_relational_domain(capsys, tmp_path):
    src = tmp_path / "never.bee"
    src.write_text("fn f(x: Int, y: Int) -> Int requires x < y and y < x ensures result == x + 1 = x\n")
    data = run_report(capsys, src, "--expect", "result == x + 1", function="f", code=1)
    assert data["observations_count"] == 0 and data["survivors_count"] is None
    assert data["expectation"]["status"] == "unknown"
    assert main(["check", str(src), "--json"]) == 0
    obligations = json.loads(capsys.readouterr().out)["contract_analysis"]["obligations"]
    assert next(row for row in obligations if row["kind"] == "ensures")["status"] == "unknown"
