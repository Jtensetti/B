import pytest

from b_lang.compiler import compile_b
from b_lang.register_view import function_view
from b_lang.types import BError


def test_line_break_after_equals_preserves_bir_and_source_view():
    compact = 'fn next_ms(n: Int) -> Int pure = n + 1\nlet t = next_ms(40)\n'
    expanded = compact.replace("= ", "=\r\n    ")
    assert compile_b(compact, strict=True).ir.to_dict() == compile_b(expanded, strict=True).ir.to_dict()
    assert function_view(expanded, "next_ms", "ordinary").rstrip() == expanded.split("let t")[0].rstrip()


def test_missing_expression_after_equals_remains_an_error():
    with pytest.raises(BError) as error:
        compile_b("let n =\nlet m = 3")
    assert error.value.code == "E_SYNTAX"
