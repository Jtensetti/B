import pytest

from b_lang import register_view
from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.register_view import function_view
from b_lang.types import BError


def test_view_round_trip_in_context():
    body = 'if (x) < -(1) then adjust(1) else if x <= 10 then adjust(2) else 5'
    header = 'fn route(x: Int) -> Int pure requires x >= -5 ensures result > 0 = '
    before = 'fn adjust(n: Int) -> Int pure = n + 1\nfn other(x: Int) -> Int = ' + body + '\n'
    after = '  \nprint route(3)'
    source = before + header + body + after
    table = function_view(source, 'route', 'cases')
    assert table == header + 'cases x {\n  < -1 => adjust(1)\n  <= 10 => adjust(2)\n  else => 5\n}'
    ordinary = function_view(before + table + after, 'route', 'ordinary')
    assert ordinary == header + 'if x < -1 then adjust(1) else if x <= 10 then adjust(2) else 5'
    assert compile_b(before + ordinary + after).ir == compile_b(source).ir


def test_ordinary_preserves_precedence_and_expands_nested_tables():
    source = '''fn sides(x: Int) -> Int = 10 + 2 * cases x {
  < 0 => cases x { < -1 => 8; else => 6 }
  else => 4
} - cases x { == 0 => 1; else => 0 }
'''
    ordinary = function_view(source, 'sides', 'ordinary')
    assert ordinary == ('fn sides(x: Int) -> Int = 10 + 2 * '
                        '(if x < 0 then if x < -1 then 8 else 6 else 4) - (if x == 0 then 1 else 0)')
    assert compile_b(ordinary).ir == compile_b(source).ir


def test_partial_view_keeps_a_second_pivot_and_computed_guard_in_the_fallback():
    header = 'fn route(x: Int, y: Int) -> Int = '
    tail = 'if y < 1 then 3 else if x + y < 2 then 4 else 5'
    ordinary = header + 'if x == 0 then 1 else if x == 1 then 2 else ' + tail
    table = function_view(ordinary, 'route', 'cases')
    assert table == header + 'cases x {\n  == 0 => 1\n  == 1 => 2\n  else => ' + tail + '\n}'
    assert function_view(table, 'route', 'ordinary') == ordinary


def test_text_escapes_and_row_separators_stay_inside_the_literal():
    source = r'fn name(x: Text) -> Text = if x == "a;\"#" then "else => }" else "é"'
    table = function_view(source, 'name', 'cases')
    assert r'== "a;\"#" => "else => }"' in table
    assert function_view(table, 'name', 'ordinary') == source


@pytest.mark.parametrize('body', [
    'x + 1',
    'if x + 1 < 0 then 0 else 1',
    'if x < y then 0 else 1',
    'if adjust(x) < 0 then 0 else 1',
])
def test_cases_declines_expressions_outside_the_register(body):
    source = 'fn adjust(n: Int) -> Int = n + 1\nfn route(x: Int, y: Int) -> Int = ' + body
    with pytest.raises(BError, match='Use the ordinary register') as error:
        function_view(source, 'route', 'cases')
    assert error.value.code == 'E_REGISTER_VIEW'
    assert function_view(source, 'route', 'ordinary').endswith(body)


def test_unequal_unoptimized_bir_rejects_rendering(monkeypatch):
    source = 'fn nine() -> Int = 4 + 5'
    monkeypatch.setattr(register_view, '_cases', lambda source, expr: '9')
    with pytest.raises(BError, match='changed.*typed BIR'):
        function_view(source, 'nine', 'cases')


def test_cli_output_is_just_the_declaration_without_running_or_editing_the_file(tmp_path, capsys, monkeypatch):
    module = tmp_path / "view_probe.py"
    module.write_text('raise RuntimeError("module body executed")\ndef mean(xs: list[int]) -> float: ...')
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / 'branch.bee'
    source = ('use py:view_probe as stats\n'
              'fn route(x: Int) -> Float = if x == 1 then stats.mean([1,2]) else 0.0\n'
              'print "must never be executed"')
    path.write_text(source, encoding='utf-8')
    cmd = ['view', str(path), '--register', 'cases', '--function']
    assert main(cmd + ['route']) == 0
    out, err = capsys.readouterr()
    assert out == ('fn route(x: Int) -> Float = cases x {\n'
                   '  == 1 => stats.mean([1,2])\n  else => 0.0\n}\n')
    assert err == ''
    assert main(cmd + ['unknown']) == 1
    out, err = capsys.readouterr()
    assert out == '' and 'No source function named' in err
    assert path.read_text(encoding='utf-8') == source
