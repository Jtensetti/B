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


def test_local_bindings_in_function_bodies():
    source = ("fn describe(prices: Dict[Text, Int], item: Text) -> Text =\n"
              "    let price = prices[item]\n"
              "    let label: Text = \"item \" + item\n"
              "    if price != none then label + \" costs \" + text(price) else label + \" is unknown\"\n"
              "let x = 1\n"
              "print describe({\"tea\": 30}, \"tea\")\nprint describe({\"bun\": 25}, \"cake\")\n")
    assert output(source) == ["item tea costs 30", "item cake is unknown"]


def test_a_local_is_evaluated_once():
    source = ("use py:b_examples.demo_lib as demo\n"
              "fn twice(v: Float) -> Float =\n    let c = demo.clamp(v, 0.0, 3.0)\n    c + c\nprint twice(5.0)\n")
    assert output(source, strict=False) == ["6.0"]


@pytest.mark.parametrize(("source", "fragment"), [
    ("fn f(x: Int) -> Int =\n    let y: Text = x\n    1", "let y: expected Text"),
    ("fn g() -> Int = 1\nfn f(x: Int) -> Int =\n    let g = x\n    g", "would hide a function"),
])
def test_local_binding_errors(source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert fragment in exc.value.message


def test_option_narrowing_after_a_none_test():
    assert output('fn f(o: Option[Int]) -> Int = if o != none then o + 1 else 0\n'
                  'fn g(o: Option[Int]) -> Int = if o == none then 0 else o * 2\n'
                  'fn h(a: Option[Int], b: Option[Int]) -> Int = if a != none and b != none then a + b else -1\n'
                  'fn k(a: Option[Int]) -> Int = if not (a == none) then a else 0\n'
                  'print [f(2), f(none), g(3), h(1, 2), h(1, none), k(4)]\n'
                  'print {key: v + 1 for key, v in {"a": 1, "b": none} where v != none}\n') == [
        "[3, 0, 6, 3, -1, 4]", "{'a': 2}"]
    with pytest.raises(BError):
        compile_b("fn f(o: Option[Int]) -> Int = if o == none then o + 1 else 0\n")
    with pytest.raises(BError):
        compile_b("fn f(a: Option[Int], b: Option[Int]) -> Int = if a != none or b != none then a + b else 0\n")


def test_numeric_and_io_core_words(monkeypatch):
    import io as stdio
    monkeypatch.setattr("sys.stdin", stdio.StringIO("hello\n"))
    assert output("print read_line()\nprint round(2.675, 2)\nprint round(2.5)\nprint sum([1.5, 2.25])\n"
                  "print sum([1, 2])\nprint max([3, 9, 4]) ?? 0\nprint max(2, 3.5)\nprint abs(-4)\n"
                  "print to_json({a = 1, b = [true, false]})\n") == [
        "hello", "2.67", "2", "3.75", "3", "9", "3.5", "4", '{"a": 1, "b": [true, false]}']


def test_then_and_else_may_start_a_line():
    assert output('fn size(x: Int) -> Text =\n    if x > 10\n    then "big"\n    else if x > 4\n    then "medium"\n'
                  '    else "small"\nprint [size(1), size(5), size(20)]\n') == ["['small', 'medium', 'big']"]
    # A decision table keeps its own else row.
    assert output('fn r(d: Int) -> Text pure = cases d {\n    < 0 => "late"\n    else => "ok"\n}\nprint r(-1)\n') == ["late"]


@pytest.mark.parametrize(("source", "fragment"), [
    ("print round(\"a\")", "round needs"),
    ("print sum([\"a\"])", "sum needs"),
    ("print max([{\"a\": 1}])", "max needs"),
    ("print min(1, \"a\")", "two Int, Float or Text"),
    ("print read_line(1)", "takes 0 argument"),
])
def test_numeric_core_word_errors(source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert fragment in exc.value.message


def test_the_guide_for_models_program_passes_strict_checks(monkeypatch):
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    program = root / "examples/for-models/quote.bee"
    monkeypatch.setattr(sys, "path", [str(program.parent), *sys.path])
    assert compile_b(program.read_text(), strict=True)
    assert program.read_text() in (root / "docs/for-models.md").read_text()


def test_a_fallback_may_name_what_a_transform_iterates_over():
    # Regression: ?? once lowered to :=, which Python forbids in a comprehension's iterable.
    assert output('fn f(d: Option[Dict[Text, Int]]) -> List[Text] = [k for k, v in d ?? {"none": 0} where v >= 0]\n'
                  'print f(none)\nprint f({"a": 1})\nprint text(1.5)\n') == ["['none']", "['a']", "1.5"]


def test_the_guide_change_example_asks_the_sunday_question():
    from pathlib import Path
    from b_lang.ask import ask
    root = Path(__file__).resolve().parents[1]
    source = (root / "examples/for-models/change.bee").read_text()
    assert source in (root / "docs/for-models.md").read_text()
    entry, = ask(source)["declarations"]
    assert entry["question"] == 'total(true, "sun"): 10 or 0?'
