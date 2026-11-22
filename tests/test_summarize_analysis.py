import pytest

from b_lang.compiler import compile_b
from b_lang.guidance import guidance
from b_lang.runtime import BContractError


def test_filter_proof_does_not_escape_its_field():
    compiled = compile_b("""
fn positive(n: Int) -> Int pure requires n > 0 = n
fn profile(xs: List[Int]) -> Dict[Text,Int] pure = summarize x in xs {
    valid: sum positive(x) where x > 0
    unchecked: sum positive(x)
    invalid: sum positive(x) where x <= 0
}
""")
    calls = [o for o in compiled.analysis.obligations if o.target == "positive"]
    assert [o.status for o in calls] == ["proved", "unknown", "refuted"]
    ns = {}
    exec(compiled.code, ns)
    assert ns["profile"]([3]) == {"valid": 3, "unchecked": 3, "invalid": 0}
    with pytest.raises(BContractError):
        ns["profile"]([-3])


def test_unreachable_projection_creates_no_proof_obligation():
    compiled = compile_b("""
fn nonzero(n: Int) -> Int pure requires n != 0 = n
fn filtered(xs: List[Int]) -> Dict[Text,Int] pure = summarize x in xs {
    unreachable: sum nonzero(x) where x > 0 and x <= 0
    skipped: sum nonzero(x) where false
    selected: sum (12 % x) where x != 0
}
""", strict=True)
    assert [(o.kind, o.status) for o in compiled.analysis.obligations] == [("nonzero", "proved")]


def test_explanation_tracks_only_the_current_field_filter():
    compiled = compile_b("""
fn observe(n: Int) -> Int pure = n
fn profile(xs: List[Int]) -> Dict[Text,Int] pure = summarize x in xs {
    filtered: sum (12 % observe(x)) where observe(x) != 0
    all: sum (12 % observe(x))
}
""")
    hints = guidance(compiled.ir, compiled.analysis)
    assert len(hints) == 2
    assert "separate calls" in hints[0]["detail"]
    assert "no nonzero guarantee" in hints[1]["detail"]


def test_obligation_identifies_summary_arguments():
    compiled = compile_b("""
fn consume(stats: Dict[Text,Int], limit: Int) -> Int pure requires limit > 0 = limit
fn profile(xs: List[Int], limit: Int) -> Int pure = consume(summarize x in xs { low: min x default -9; early: count where x < 0 }, limit)
""")
    call, = compiled.analysis.obligations
    assert call.expression == "consume(summarize x in xs { low: min x default -9; early: count where (x < 0) }, limit)"
