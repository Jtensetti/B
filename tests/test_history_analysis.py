import json

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.guidance import guidance


@pytest.mark.parametrize("mode", ["adjacent", "earlier"])
def test_position_count_has_nonnegative_and_literal_length_bounds(mode, tmp_path, capsys):
    path = tmp_path / "bounds.bee"
    path.write_text(f"""
fn matches(xs: List[Int]) -> Int pure ensures result >= 0 =
    count {mode} past, now in xs where past > now
fn three(k: Int) -> Int pure ensures result <= 2 =
    count {mode} past, now in [k, 0, k] where now > past
fn all(k: Int) -> Int pure ensures result == 2 =
    count {mode} past, now in [k, 0, k] where true
""")
    assert main(["check", str(path), "--strict", "--require-proofs", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [o["status"] for o in report["contract_analysis"]["obligations"]] == ["proved"] * 3


def test_unjustified_positive_count_is_refuted_or_unknown(tmp_path, capsys):
    path = tmp_path / "false.bee"
    path.write_text("""
fn never(k: Int) -> Int pure ensures result > 0 = count adjacent a, b in [k] where a == b
fn maybe(xs: List[Int]) -> Int pure ensures result > 0 = count earlier a, b in xs where a == b
""")
    assert main(["check", str(path), "--require-proofs", "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert [(o["caller"], o["status"]) for o in report["contract_analysis"]["obligations"]] == [
        ("never", "refuted"), ("maybe", "unknown"),
    ]


def test_zero_length_history_does_not_hide_obligations_in_the_source():
    compiled = compile_b("""
fn positive(k: Int) -> Int pure requires k > 0 = k
fn zero(k: Int) -> Int pure ensures result == 0 =
    count earlier a, b in [positive(k)] where a == b
""")
    assert [(o.kind, o.status) for o in compiled.analysis.obligations] == [
        ("requires", "unknown"), ("ensures", "proved"),
    ]
    hint, = guidance(compiled.ir, compiled.analysis)
    assert hint["site"] == "body.0.0" and hint["argument"] == "k"


def test_history_predicate_has_its_own_scope_and_renders_in_obligation():
    compiled = compile_b("""
fn positive(k: Int) -> Int pure requires k > 0 = k
fn checkit(xs: List[Int], floor: Int) -> Int pure =
    positive(count adjacent p, q in xs where p > floor and q > floor)
""")
    item, = compiled.analysis.obligations
    assert item.status == "unknown"
    hint, = guidance(compiled.ir, compiled.analysis)
    assert hint["argument"] == "(count adjacent p, q in xs where ((p > floor) and (q > floor)))"
