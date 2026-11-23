import io
import json
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.runtime import BBoundaryError
from b_lang.types import BError

BOOKING = ("record Booking {\n    child: Bool\n    day: Text\n    seats: Int\n    note: Option[Text]\n}\n")


def output(source, strict=True):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source, strict=strict).code, {"__name__": "__b_test__"})
    return buffer.getvalue().splitlines()


def test_transform_lists_and_dictionaries():
    assert output('let prices = {"tea": 30, "cake": 45, "bun": 25}\n'
                  'print [n for n, p in prices where p < 40]\n'
                  'print {n: p * 2 for n, p in prices}\n'
                  'print [x * x for x in [1, 2, 3] where x != 2]\n'
                  'print [k for k in prices]\n') == [
        "['tea', 'bun']", "{'tea': 60, 'cake': 90, 'bun': 50}", "[1, 9]", "['tea', 'cake', 'bun']"]


def test_transforms_are_pure_and_typed():
    names = {}
    exec(compile_b("fn doubled(xs: List[Int]) -> List[Int] pure = [x * 2 for x in xs]\n", strict=True).code, names)
    assert names["doubled"]([1, 2]) == [2, 4]


@pytest.mark.parametrize(("source", "fragment"), [
    ("let x = [y for y in 3]", "needs a List[T] or Dict"),
    ("let x = [a for a, b in [1]]", "one name per item"),
    ("let xs = [1]\nlet x = [xs for xs in xs]", "already in scope"),
    ("let x = [y for y in [1] where y]", "where: expected Bool"),
    ("let x = {y: y for y in [1]}", "dictionary key: expected Text"),
    ("let x = [k for k, k in {\"a\": 1}]", "two different names"),
])
def test_transform_errors(source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert fragment in exc.value.message


def test_records_are_structural_and_come_straight_from_json():
    source = (BOOKING + "use py:json as json\nforeign json.loads(Text) -> List[Booking]\n"
              "fn price(b: Booking) -> Int pure = if b.child then 0 else 100 * b.seats\n"
              "let bookings = json.loads(\"[{\\\"child\\\": true, \\\"day\\\": \\\"sat\\\", \\\"seats\\\": 1},"
              " {\\\"child\\\": false, \\\"day\\\": \\\"mon\\\", \\\"seats\\\": 2, \\\"extra\\\": 9}]\")\n"
              "let walk_in: Booking = {child = false, day = \"sun\", seats = 3}\n"
              "print [price(b) for b in bookings]\n"
              "print price(walk_in)\n"
              "print [b.note ?? \"-\" for b in bookings]\n")
    assert output(source) == ["[0, 200]", "300", "['-', '-']"]


def test_json_that_does_not_fit_the_record_is_stopped_at_the_border():
    source = (BOOKING + "use py:json as json\nforeign json.loads(Text) -> Booking\n"
              "let b = json.loads(\"{\\\"child\\\": true, \\\"day\\\": \\\"sat\\\"}\")\n")
    with pytest.raises(BBoundaryError, match="Missing field seats"):
        output(source, strict=False)


@pytest.mark.parametrize(("source", "fragment"), [
    (BOOKING + 'let b: Booking = {child = true, day = "sat"}', "expected Record"),
    (BOOKING + 'let b: Booking = {child = true, day = "sat", seats = "one"}', "expected Record"),
    (BOOKING + 'fn f(b: Booking) -> Int pure = b.colour', "No field colour in Booking"),
    ("record A {x: Int}\nrecord A {y: Int}", "already defined"),
    ("record List {x: Int}", "already defined"),
    ("let r = {x = 1, x = 2}", "each field once"),
])
def test_record_errors(source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert fragment in exc.value.message


def test_records_nest_and_can_refer_to_later_records():
    source = ("record Order {lines: List[Line], customer: Text}\nrecord Line {item: Text, qty: Int}\n"
              "fn count(o: Order) -> Int pure = summarize l in [line.qty for line in o.lines] {\n    n: sum l\n}[\"n\"] ?? 0\n"
              "let o: Order = {customer = \"Ada\", lines = [{item = \"tea\", qty = 2}, {item = \"bun\", qty = 3}]}\n"
              "print count(o)\n")
    assert output(source) == ["5"]


def test_core_words():
    assert output('let p = {"tea": 30, "cake": 45, "bun": 25}\n'
                  'print sorted(keys(p))\nprint len(p)\nprint sorted(values(p))\n'
                  'print join([n + "=" + text(v) for n, v in p], ", ")\n'
                  'print text(true) + " " + text(2.5)\nprint len("hej")\n') == [
        "['bun', 'cake', 'tea']", "3", "[25, 30, 45]", "tea=30, cake=45, bun=25", "true 2.5", "3"]
    assert output("fn len(x: Int) -> Int pure = x + 1\nprint len(2)\n") == ["3"]  # a program's own word wins


@pytest.mark.parametrize(("source", "fragment"), [
    ("print len(3)", "len needs"),
    ("print sorted([{\"a\": 1}])", "sorted needs"),
    ("record A {b: B}\nrecord B {a: A}", "contains itself"),
    ("print keys([1])", "keys needs"),
    ("print text([1])", "text needs"),
    ("print join([1], \",\")", "join needs"),
    ("print len()", "takes 1 argument"),
])
def test_core_word_errors(source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert fragment in exc.value.message
