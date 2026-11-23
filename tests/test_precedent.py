import json
import shutil
from pathlib import Path

import pytest

from b_lang.ask import answer, ask, parse_answer
from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.model import parse
from b_lang.types import BError

ROOT = Path(__file__).resolve().parents[1]
BOOKING = (ROOT / "examples/ask/booking.bee").read_text()
SUNDAY = (ROOT / "examples/ask/sunday.bee").read_text()

RULE = 'fn free_entry(child: Bool, day: Text) -> Bool pure = child and day == "sat"\n'
TICKET = 'fn ticket(child: Bool, day: Text) -> Int pure = if free_entry(child, day) then 0 else 100\n'
TOTAL = 'fn total(child: Bool, day: Text) -> Int pure = ticket(child, day) + fee(child, day)\n'


def program(fee: str, extra: str = "") -> str:
    return RULE + TICKET + f"fn fee(child: Bool, day: Text) -> Int pure = {fee}\n" + TOTAL + extra


def run(source):
    names = {}
    exec(compile_b(source, strict=True).code, names)
    return names


def test_like_parses_between_case_and_keeping():
    row = parse('also free_entry(true, "sun") like (true, "sat") keeping seats')[0]
    assert row.parts == ("free_entry", (True, "sun"), ("seats",), (True, "sat"))
    assert parse("also gate() like ()")[0].parts[3] == ()
    assert parse("fn like(like: Int) -> Int = like")[0].kind == "fn"


def test_like_rejects_a_remaining_difference_and_names_its_start():
    with pytest.raises(BError) as exc:
        compile_b(BOOKING + 'also free_entry(true, "sun") like (true, "sat")')
    assert exc.value.code == "E_LIKE"
    assert 'total(true, "sun") = 10, but total(true, "sat") = 0' in exc.value.message
    assert "starts in fee" in exc.value.message


def test_like_accepts_when_every_shared_input_function_agrees():
    source = program("if free_entry(child, day) then 0 else 10",
                     'also free_entry(true, "sun") like (true, "sat")\n')
    names = run(source)
    assert names["total"](True, "sun") == names["total"](True, "sat") == 0
    assert names["total"](False, "sun") == 110


@pytest.mark.parametrize(("declaration", "fragment"), [
    ('also free_entry(true, "sun") like (false, "sat")', "already covered"),
    ('also free_entry(true, "sun") like (true, "sun")', "like itself"),
    ('also free_entry(true, "sun") like (true)', "expects 2"),
    ('also free_entry(true, "sun") like (1, "sat")', "exact scalar"),
])
def test_like_requires_a_distinct_typed_existing_case(declaration, fragment):
    with pytest.raises(BError) as exc:
        compile_b(program("10", declaration))
    assert fragment in exc.value.message


def test_unrelated_and_unreferenced_functions_do_not_block_like():
    extra = ('fn seats(child: Bool, day: Text, available: Int) -> Int pure = available - 1\n'
             'fn recipient(gift: Bool) -> Text pure = if gift then "buyer" else "guest"\n'
             'also free_entry(true, "sun") like (true, "sat") keeping seats, recipient\n')
    assert compile_b(program("10", extra), strict=True)


def test_extra_parameters_take_the_same_value_on_both_sides():
    extra = ('fn queue(child: Bool, day: Text, size: Int) -> Int pure = if day == "sat" then size else size + 1\n'
             'also free_entry(true, "sun") like (true, "sat")\n')
    with pytest.raises(BError) as exc:
        compile_b(program("10", extra))
    assert "queue(true, \"sun\", 0) = 1, but queue(true, \"sat\", 0) = 0" in exc.value.message


def test_ask_finds_the_booking_and_offers_two_checked_answers():
    report = ask(BOOKING, SUNDAY)
    assert report["status"] == "question"
    entry, = report["declarations"]
    assert entry["precedent"] == [True, "sat"]
    assert entry["question"] == 'total(true, "sun"): 10 or 0?'
    assert entry["causes"] == ["fee"]
    assert {c["function"]: (c["before"], c["after"]) for c in entry["changes"]} == {
        "ticket": (100, 0), "total": (110, 10)}
    assert [o["value"] for o in entry["options"]] == [10, 0]
    assert all(o["applicable"] for o in entry["options"])


def test_each_answer_is_executable_and_settles_the_question():
    texts = answer(ask(BOOKING, SUNDAY), 10)
    assert texts["file"] == BOOKING
    assert texts["delta"].strip().endswith("keeping seats, recipient, fee")
    assert run(texts["file"] + texts["delta"])["total"](True, "sun") == 10
    assert ask(texts["file"], texts["delta"])["declarations"][0]["status"] == "answered"

    texts = answer(ask(BOOKING, SUNDAY), 0)
    assert "if free_entry(child, day) then 0 else 10" in texts["file"]
    assert 'like (true, "sat")' in texts["delta"]
    names = run(texts["file"] + texts["delta"])
    assert names["total"](True, "sun") == 0 and names["total"](False, "sat") == 110
    assert ask(texts["file"], texts["delta"])["declarations"][0]["status"] == "checked"


def test_an_answer_outside_the_offered_values_is_rejected():
    with pytest.raises(BError) as exc:
        answer(ask(BOOKING, SUNDAY), 5)
    assert "10 or 0" in exc.value.message
    with pytest.raises(BError):
        answer(ask(BOOKING, SUNDAY), parse_answer('"0"'))


@pytest.mark.parametrize(("fee", "status", "value"), [
    ("10", "settled", 10),
    ("if free_entry(child, day) then 0 else 10", "settled", 0),
    ('if child and (day == "sat" or day == "sun") then 0 else 10', "settled", 0),
])
def test_context_can_settle_the_meaning_without_a_question(fee, status, value):
    source = program(fee, 'also free_entry(true, "sun")\n')
    entry, = ask(source)["declarations"]
    assert entry["status"] == status
    assert run(source)["total"](True, "sun") == value
    assert 'like (true, "sat")' in entry["suggestion"]
    assert compile_b(source.replace('also free_entry(true, "sun")', entry["suggestion"]), strict=True)


def test_a_difference_without_a_repeated_rule_cannot_be_written_automatically():
    source = (RULE + TICKET + 'fn surcharge(day: Text) -> Int pure = if day == "sun" then 20 else 0\n'
              'fn total(child: Bool, day: Text) -> Int pure = ticket(child, day) + surcharge(day)\n'
              'also free_entry(true, "sun")\n')
    entry, = ask(source)["declarations"]
    assert entry["question"] == 'total(true, "sun"): 20 or 0?'
    keep, like = entry["options"]
    assert keep["applicable"] and keep["declaration"].endswith("keeping surcharge")
    assert not like["applicable"]
    with pytest.raises(BError) as exc:
        answer(ask(source), 0)
    assert "edit surcharge" in exc.value.message
    assert "keeping surcharge" in answer(ask(source), 20)["file"]


def test_integer_rules_use_the_nearest_existing_case():
    source = ('fn discount(age: Int, day: Text) -> Bool pure = age < 12 and day == "sat"\n'
              'fn price(age: Int, day: Text) -> Int pure = if discount(age, day) then 50 else 100\n'
              'fn gift(age: Int, day: Text) -> Text pure = if day == "sat" then "pin" else "none"\n'
              'also discount(10, "sun")\n')
    entry, = ask(source)["declarations"]
    assert entry["precedent"] == [10, "sat"]
    assert entry["question"] == 'gift(10, "sun"): "none" or "pin"?'


def test_no_change_and_no_precedent_are_reported():
    entry, = ask(program("10", 'also free_entry(true, "sat")\n'))["declarations"]
    assert entry["status"] == "no-change"
    never = ('fn gate(day: Text) -> Bool pure = false\n'
             'fn label(day: Text) -> Text pure = if gate(day) then "open" else "closed"\nalso gate("sun")\n')
    entry, = ask(never)["declarations"]
    assert entry["status"] == "no-precedent"
    assert entry["changes"] == [{"function": "label", "arguments": {"day": "sun"},
                                 "before": "closed", "after": "open"}]


def test_cli_reports_applies_and_exits_by_status(tmp_path, capsys):
    base, delta = tmp_path / "booking.bee", tmp_path / "sunday.bee"
    shutil.copy(ROOT / "examples/ask/booking.bee", base)
    shutil.copy(ROOT / "examples/ask/sunday.bee", delta)
    assert main(["ask", str(base), "--with", str(delta)]) == 2
    out = capsys.readouterr().out
    assert 'question: total(true, "sun"): 10 or 0?' in out
    assert 'and in fee: child and day == "sat" -> free_entry(child, day)' in out
    assert main(["ask", str(base), "--with", str(delta), "--answer", "0"]) == 0
    assert base.read_text() == BOOKING  # without --apply nothing is written
    capsys.readouterr()
    assert main(["ask", str(base), "--with", str(delta), "--answer", "0", "--apply"]) == 0
    capsys.readouterr()
    assert main(["run", str(base), "--with", str(delta)]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "0"
    assert main(["ask", str(base), "--with", str(delta), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["declarations"][0]["status"] == "checked"
    assert main(["ask", str(base), "--with", str(delta), "--answer", "0"]) == 1


def test_fixture_study_results_are_current():
    import importlib.util
    spec = importlib.util.spec_from_file_location("precedent_study", ROOT / "experiments/precedent-questions/check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorded = json.loads((ROOT / "experiments/precedent-questions/results.json").read_text())
    assert module.study() == recorded
    assert [row["status"] for row in recorded].count("question") == 3


def test_two_repeated_conditions_are_both_repaired():
    source = (RULE + TICKET
              + 'fn fee(child: Bool, day: Text) -> Int pure = if child and day == "sat" then 0 else 10\n'
              + 'fn snack(child: Bool, day: Text) -> Int pure = if child and day == "sat" then 0 else 5\n'
              + 'fn total(child: Bool, day: Text) -> Int pure = ticket(child, day) + fee(child, day) + snack(child, day)\n'
              + 'also free_entry(true, "sun")\n')
    entry, = ask(source)["declarations"]
    assert entry["question"] == 'total(true, "sun"): 15 or 0?'
    assert sorted(entry["causes"]) == ["fee", "snack"]
    revised = answer(ask(source), 0)["file"]
    assert revised.count("free_entry(child, day) then 0") == 3
    assert run(revised)["total"](True, "sun") == 0
