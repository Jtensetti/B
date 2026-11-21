"""Automated foreign signatures are explicit *assumptions*, not proofs."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.discovery import inspect_python
from b_lang.netmeta import manifest, net_bindings
from b_lang.runtime import BBoundaryError
from b_lang.types import BError


def test_real_python_stub_autoloads_without_foreign_declaration():
    source = '''use py:b_examples.demo_lib as t
let m: Float = t.weighted_mean([1.0, 5.0], [1.0, 3.0])
print m'''
    compiled = compile_b(source, strict=True)
    assert not compiled.diagnostics
    assert compiled.assumptions == [
        'py:b_examples.demo_lib.weighted_mean (pyi): signature assumed, not behavior proved'
    ]
    out = io.StringIO()
    with redirect_stdout(out):
        exec(compiled.code, {'__name__': '__b_test__'})
    assert out.getvalue().strip() == '4.0'


def test_python_default_arity_from_stub():
    one = compile_b('use py:b_examples.demo_lib as t\nprint t.repeat("X")', strict=True)
    out = io.StringIO()
    with redirect_stdout(out): exec(one.code, {})
    assert out.getvalue().strip() == 'X'
    two = compile_b('use py:b_examples.demo_lib as t\nprint t.repeat("X", 3)', strict=True)
    out = io.StringIO()
    with redirect_stdout(out): exec(two.code, {})
    assert out.getvalue().strip() == 'XXX'
    with pytest.raises(BError, match='E_ARITY'):
        compile_b('use py:b_examples.demo_lib as t\nprint t.repeat()')


def test_autodiscovery_rejects_wrong_types_preexecution():
    with pytest.raises(BError) as e:
        compile_b('use py:b_examples.demo_lib as t\nprint t.clamp("bad", 0.0, 1.0)')
    assert e.value.code == 'E_TYPE'


def test_static_stub_check_never_imports_target(tmp_path: Path, monkeypatch):
    (tmp_path / 'b_temp_mod.py').write_text(
        'from pathlib import Path\nPath("will-not-run.txt").write_text("side effect")\n'
        'def safe(x: float) -> float: return x\n', encoding='utf-8')
    (tmp_path / 'b_temp_mod.pyi').write_text('def safe(x: float) -> float: ...\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = compile_b('use py:b_temp_mod as m\nprint m.safe(2.0)', strict=True)
    assert result.assumptions
    assert not Path('will-not-run.txt').exists()


def test_an_untrusted_annotation_is_not_evaluated(tmp_path, monkeypatch):
    path = tmp_path / 'b_bad_annotations.py'
    path.write_text('def trick(x: __import__("os").system("touch pwned")) -> int: return 1\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    inspected = inspect_python('b_bad_annotations')
    assert 'trick' not in inspected.signatures
    assert not (tmp_path / 'pwned').exists()


def test_discovery_skips_nonrepresentable_types_and_overloads(tmp_path, monkeypatch):
    (tmp_path / 'b_unsupported.py').write_text('def f(x): return x\n', encoding='utf-8')
    (tmp_path / 'b_unsupported.pyi').write_text(
        'from typing import overload\n'
        '@overload\ndef f(x: int) -> int: ...\n'
        '@overload\ndef f(x: str) -> str: ...\n'
        'def f(x: object) -> object: ...\n'
        'def g(x: dict[str, int]) -> int: ...\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    found = inspect_python('b_unsupported')
    assert found.signatures == {}
    assert 'f' in found.skipped and 'g' in found.skipped
    result = compile_b('use py:b_unsupported as m\nprint m.f(2)')
    assert any(d.code == 'W_UNCHECKED_FOREIGN' for d in result.diagnostics)
    with pytest.raises(BError, match='E_STRICT'):
        compile_b('use py:b_unsupported as m\nprint m.f(2)', strict=True)


def test_py_source_annotations_can_be_discovered_without_stub(tmp_path, monkeypatch):
    (tmp_path / 'b_typed_source.py').write_text('def plus(x: float, y: float) -> float: return x+y\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    found = inspect_python('b_typed_source')
    assert found.source_kind == 'py'
    assert list(found.signatures) == ['plus']


def test_boundary_checks_return_values_when_stubs_lie(tmp_path, monkeypatch):
    (tmp_path / 'b_liar.py').write_text('def answer() -> str: return "no"\n', encoding='utf-8')
    (tmp_path / 'b_liar.pyi').write_text('def answer() -> int: ...\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    checked = compile_b('use py:b_liar as m\nprint m.answer()', strict=True)
    with pytest.raises(BBoundaryError, match='Expected Int'):
        exec(checked.code, {})


def test_net_manifest_is_inspectable_without_net_runtime(capsys):
    assert manifest()['schema'] == 1
    assert 'net:System.Math.Sqrt' in net_bindings()
    assert 'net:System.Text.RegularExpressions.Regex.IsMatch' in net_bindings()
    assert main(['inspect', 'net:System.Math', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['provenance'] == 'verified-snapshot'
    assert any(x['name'] == 'Sqrt' for x in result['signatures'])


def test_python_inspection_command(capsys):
    assert main(['inspect', 'py:b_examples.demo_lib', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['provenance'] == 'pyi'
    assert result['behavior_proven'] is False
    assert 'weighted_mean' in [x['name'] for x in result['signatures']]


def test_bee_extension_and_compatibility(tmp_path: Path, capsys):
    for ext in ('.bee', '.bsrc', '.b'):
        path = tmp_path / ('ok'+ext)
        path.write_text('print 5\n', encoding='utf-8')
        assert main(['check', str(path), '--strict']) == 0
        capsys.readouterr()
    path = tmp_path / 'berry.be'
    path.write_text('print 5\n', encoding='utf-8')
    assert main(['check', str(path), '--json']) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['error']['code'] == 'E_EXTENSION'
