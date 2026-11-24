"""Fixes for friction seen in the sibling trials: named records, text words, divisor guards, ?? and restated signatures."""
import io
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.types import BError


def unproved(source):
    return [o for o in compile_b(source).analysis.obligations if o.status != "proved"]


def run(source):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source, strict=True).code, {"__name__": "__b_test__"})
    return buffer.getvalue().splitlines()


def test_a_named_record_literal_is_checked_against_its_record():
    assert run('record Quote { price: Float, note: Option[Text] }\n'
               'fn q(p: Float) -> Quote = Quote {\n    price = p\n}\nprint q(2.5).price\n') == ["2.5"]
    with pytest.raises(BError):
        compile_b('record Quote { price: Float }\nlet q = Quote { cost = 1.0 }\n')


def test_text_words():
    assert run('print upper("se")\nprint lower("SE")\nprint trim("  se ")\n') == ["SE", "se", "se"]


@pytest.mark.parametrize("guard", ["r > 0.0", "0.0 < r", "r != 0.0", "not (r <= 0.0)", "r > 0.0 and x > 0.0"])
def test_a_branch_condition_proves_its_divisor_nonzero(guard):
    assert unproved(f"fn f(x: Float, r: Float) -> Float = if {guard} then x / r else 0.0\n") == []


@pytest.mark.parametrize("guard", ["r >= 0.0", "r < 1.0", "r == 0.0", "r > 0.0 or x > 0.0"])
def test_a_condition_that_allows_zero_proves_nothing(guard):
    assert len(unproved(f"fn f(x: Float, r: Float) -> Float = if {guard} then x / r else 0.0\n")) == 1


def test_a_field_divisor_is_proved_by_its_own_test_only():
    record = "record R { r: Float, s: Float }\n"
    assert unproved(record + "fn f(x: Float, d: R) -> Float = if d.r > 0.0 then x / d.r else 0.0\n") == []
    assert len(unproved(record + "fn f(x: Float, d: R) -> Float = if d.r > 0.0 then x / d.s else 0.0\n")) == 1
    assert len(unproved("fn f(x: Float, r: Float) -> Float = if r > 0.0 then 0.0 else x / r\n")) == 1
