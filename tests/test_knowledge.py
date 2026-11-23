from pathlib import Path

import pytest

from b_lang.ask import ask
from b_lang.compiler import compile_b
from b_lang.learn import learn, render
from b_lang.model import parse
from b_lang.types import BError

ROOT = Path(__file__).resolve().parents[1]


def run(source):
    names = {}
    exec(compile_b(source, strict=True).code, names)
    return names


def test_swedish_names_compile_and_unnormalized_names_are_refused():
    names = run('fn pris(barn: Bool, dag: Text) -> Int pure = if barn and dag == "lördag" then 0 else 100\n')
    assert names["pris"](True, "lördag") == 0
    with pytest.raises(Exception, match="normalized"):
        parse("let ﬁx = 1")
    with pytest.raises(Exception):
        parse("let 1x = 1")


def test_membership_uses_a_known_group():
    names = run('know calendar\nfn fee(day: Text) -> Int pure = if day in weekend then 20 else 10\n')
    assert [names["fee"](d) for d in ("fri", "sat", "sun")] == [10, 20, 20]
    names = run('group late of hour: "night", "evening"\n'
                'fn lamp(hour: Text) -> Bool pure = hour in late and not (hour in late and false)\n')
    assert names["lamp"]("night") and not names["lamp"]("noon")


@pytest.mark.parametrize(("source", "code"), [
    ("know astrology\n", "E_KNOW"),
    ('fn f(day: Text) -> Bool pure = day in holidays\n', "E_NAME"),
    ('know calendar\ngroup weekend of day: "sat"\n', "E_DOMAIN"),
    ('know calendar\ngroup long of day: "sat", "funday"\n', "E_DOMAIN"),
    ('know calendar\nfn f(day: Text) -> Bool pure = day == "sön"\n', "E_DOMAIN"),
])
def test_invalid_knowledge(source, code):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert exc.value.code == code


def test_knowledge_files_are_written_in_b():
    for name in ("calendar", "kalender"):
        statements = parse((ROOT / "b_lang/truths" / f"{name}.bee").read_text(encoding="utf-8"))
        assert {s.kind for s in statements} == {"domain", "group"}
    assert compile_b("know calendar\nknow kalender\nknow calendar\n")


def test_a_known_group_is_one_test_for_the_learner():
    domains = {"day": ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    groups = {"weekend": ("day", ("sat", "sun"))}
    rows = [((False, "mon"), 100), ((True, "sat"), 0), ((True, "sun"), 0), ((True, "mon"), 100),
            ((False, "sun"), 100), ((True, "tue"), 100)]
    params = [("child", "Bool"), ("day", "Text")]
    assert render(learn("p", params, "Int", rows, {}, domains, groups).rule, ["child", "day"]) \
        == "if child and day in weekend then 0 else 100"
    without = learn("p", params, "Int", rows, {}, domains)
    assert "weekend" not in render(without.rule, ["child", "day"])


def test_one_line_change_generalizes_to_the_known_concept():
    source = (ROOT / "examples/learn/biljett.bee").read_text(encoding="utf-8")
    entry = ask(source)["declarations"][0]
    assert entry["status"] == "settled" and entry["rule"] == "if barn and dag in helg then 0 else 100"
    names = run(source)
    assert names["pris"](True, "söndag") == 0 and names["pris"](True, "fredag") == 100
    before = source.replace('example pris(true, "söndag") == 0 was 100\n', "")
    assert ask(before)["declarations"][0]["rule"] == 'if barn and dag == "lördag" then 0 else 100'
