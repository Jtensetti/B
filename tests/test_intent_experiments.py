"""Replay the measured distinction between per-edit, per-input and joint judgments."""
from pathlib import Path
from runpy import run_path

EXPERIMENTS = Path(__file__).resolve().parents[1] / "experiments"


def test_the_cost_depends_on_whether_answers_are_reused():
    rows = run_path(str(EXPERIMENTS / "edit-questions" / "measure.py"))["measure"]()
    assert all(row["correct_of_16"] == 16 for row in rows.values())
    fresh = [rows[mode + "/fresh_per_edit"]["questions"] for mode in ("identify_then_decide", "decide_edit")]
    reused = [rows[mode + "/reuse_answers"]["questions"] for mode in ("identify_then_decide", "decide_edit")]
    assert fresh == [32, 14] and reused == [8, 8]


def test_identical_one_row_permissions_can_hide_a_layout_violation():
    row = run_path(str(EXPERIMENTS / "layout-coherence" / "measure.py"))["measure"]()
    assert row["pointwise_comparison"] == "equivalent-on-grid"
    assert row["pointwise_edit_decision"] == "approve"
    assert row["mixed_allowed_with_one_style"] is False
    assert row["mixed_allowed_with_independent_rows"] is True
    assert row["one_style_vs_independent"]["arity"] == 2
    assert row["even_vs_independent"]["arity"] == 3
