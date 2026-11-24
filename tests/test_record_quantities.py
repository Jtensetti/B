"""Quantities in record fields: a field keeps one dimension under its name in every record."""
import io
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.types import BError

LINE = "record Line { sku: Text, net: Money[SEK] }\n"


def run(source):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source).code, {"__name__": "__b_test__"})
    return buffer.getvalue().splitlines()


def test_a_record_holds_money_and_sums_keep_the_currency():
    assert run(LINE + 'fn line(sku: Text, price: Float, qty: Int) -> Line = {sku = sku, net = qty * (price * 1 SEK)}\n'
               'let ls = [line("tea", 40.0, 2), line("mug", 120.0, 1)]\n'
               'let total = sum([l.net for l in ls])\n'
               'print total as SEK\n'
               'print max([l.net for l in ls]) as SEK\n'
               'print [l.sku for l in ls where l.net > 100 SEK]\n') == ["200.0", "120.0", "['mug']"]


def test_a_field_converts_like_any_quantity():
    assert run("record Parcel { id: Text, weight: Mass }\n"
               'let p: Parcel = {id = "a", weight = 2 lb}\n'
               "print round(p.weight as kg, 4)\n") == ["0.9072"]


@pytest.mark.parametrize(("source", "fragment"), [
    (LINE + 'let l: Line = {sku = "a", net = 5 NOK}\n', "Field net must be Money[SEK], got Money[NOK]"),
    (LINE + 'let l: Line = {sku = "a", net = 5 SEK}\nprint sum([x.net for x in [l]]) + 1 NOK as SEK\n',
     "Cannot add Money[SEK] and Money[NOK]"),
    (LINE + "record Other { net: Money[NOK] }\n", "keeps one dimension in every record"),
    (LINE + "record Other { net: Int }\n", "give the quantity field a name of its own"),
    (LINE + 'let l: Line = {sku = "a", net = 5 SEK}\nprint l.net\n', "print needs a plain number"),
])
def test_mistakes_with_record_quantities_are_compile_errors(source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert fragment in exc.value.message
