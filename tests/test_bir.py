"""BIR is a typed program contract, not a pretty-printer for Python AST."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from b_lang.compiler import compile_b
from b_lang.cli import main
from b_lang.ir import ExprIR
from b_lang.optimizer import optimize
from b_lang.types import BError


def _run(source: str):
    program = compile_b(source, strict=True)
    stream = io.StringIO()
    with redirect_stdout(stream):
        exec(program.code, {})
    return stream.getvalue().strip(), program


def test_bir_is_json_serializable_and_contains_typed_program_without_python_ast():
    source = '''use py:b_examples.demo_lib as t
fn square(x: Float) -> Float = x * x
let p: Float = t.clamp(11.0, 1.0, 10.0)
print square(p)'''
    result, compiled = _run(source)
    assert result == "100.0"
    serial = json.loads(json.dumps(compiled.ir.to_dict()))
    assert serial["schema"] == "bir" and serial["version"] == 2
    assert serial["statements"][1]["op"] == "fn"
    assert serial["statements"][1]["parameters"] == [{"name": "x", "type": "Float"}]
    assert len(serial["foreign_symbols"]) == 1
    foreign = serial["foreign_symbols"][0]
    assert foreign["path"] == "py:b_examples.demo_lib.clamp"
    assert foreign["provenance"] == "pyi"
    assert foreign["verified_behavior"] is False
    assert "ast" not in json.dumps(serial)
    assert "(_b_py" not in json.dumps(serial)
    assert any("signature assumed" in t for t in serial["assumed_foreign_contracts"])


def test_ir_serializes_none_as_explicit_null():
    ir = compile_b('let x: Option[Int] = none\nprint x').ir.to_dict()
    node = ir['statements'][0]['expression']['operands'][0]
    assert node['op'] == 'literal' and 'value' in node and node['value'] is None


def test_bir_handles_python_and_dotnet_through_same_call_node():
    program = compile_b('''use py:statistics as stats
use net:System.Math as Math
let avg: Float = stats.mean([4.0, 6.0])
print Math.Sqrt(avg)''', strict=True)
    exported = program.ir.to_dict()
    assert [(x['backend'], x['path']) for x in exported['foreign_symbols']] == [
        ('net', 'net:System.Math.Sqrt'), ('py', 'py:statistics.mean')]
    def find_calls(node):
        if isinstance(node, dict):
            if node.get('op') == 'call':
                yield node
            for sub in node.values():
                yield from find_calls(sub)
        elif isinstance(node, list):
            for sub in node:
                yield from find_calls(sub)
    calls = list(find_calls(exported['statements']))
    assert sorted(x['foreign'] for x in calls) == ['net:System.Math.Sqrt', 'py:statistics.mean']
    assert all(x['verified_behavior'] is False for x in exported['foreign_symbols'])


def test_safe_ir_optimizer_folds_pure_arithmetic_without_rewriting_foreign_calls():
    output, program = _run('''use py:statistics as stats
let n: Int = (2 + 3) * (4 + 1)
let m: Float = stats.mean([3.0, 5.0])
print n
print m''')
    assert output.splitlines() == ['25', '4.0']
    assert program.folds >= 3
    assert 'n = _b_guard(25,' in program.source
    assert 'stats.mean' in program.source
    raw_stmt = program.ir.to_dict()['statements'][1]
    opt_stmt = program.optimized_ir.to_dict()['statements'][1]
    assert raw_stmt['expression']['operands'][0]['op'] == 'mul'
    assert opt_stmt['expression']['operands'][0]['op'] == 'literal'


def test_optimizer_does_not_execute_foreign_calls_during_compile(tmp_path, monkeypatch):
    (tmp_path / 'b_sideeffect.py').write_text('''from pathlib import Path
def make(x: float) -> float:
    Path('executed.txt').write_text('yes')
    return x
''', encoding='utf-8')
    (tmp_path / 'b_sideeffect.pyi').write_text('def make(x: float) -> float: ...\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    program = compile_b('use py:b_sideeffect as lib\nprint lib.make(2.0 + 3.0)', strict=True)
    assert not (tmp_path / 'executed.txt').exists()
    assert program.folds >= 1
    assert 'lib.make' in program.source
    with redirect_stdout(io.StringIO()):
        exec(program.code, {})
    assert (tmp_path / 'executed.txt').read_text() == 'yes'


def test_bir_cli_is_machine_readable_and_strict_diagnostics_apply(tmp_path, capsys):
    path = tmp_path / 'program.bee'
    path.write_text('print (1 + 3) * 4\n')
    assert main(['ir', str(path), '--optimized']) == 0
    d = json.loads(capsys.readouterr().out)
    assert d['statements'][0]['expression']['op'] == 'literal'
    assert d['statements'][0]['expression']['value'] == 16
    warning = tmp_path / 'unsafe.bee'
    warning.write_text('use py:json as lib\nprint lib.loads("2")')
    assert main(['ir', str(warning), '--strict']) == 1
    assert 'E_STRICT' in capsys.readouterr().err


def test_unsupported_ir_operation_fails_closed():
    from b_lang.ir import ProgramIR, StmtIR
    from b_lang.lowering import PythonLowerer
    with pytest.raises(BError, match='E_INTERNAL'):
        PythonLowerer().lower(ProgramIR((StmtIR('print', expr=ExprIR('telepathy', typ=compile_b('let x = 1').ir.statements[0].typ)),),()))
