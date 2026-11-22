"""Automated foreign signatures are explicit *assumptions*, not proofs."""
import io
import json
import sys
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


def test_check_and_discover_do_not_initialize_dotted_python_packages(tmp_path, monkeypatch, capsys):
    root = tmp_path / "b_lookup_fixture"
    nested = root / "nested"
    nested.mkdir(parents=True)
    marker = tmp_path / "package-executed"
    side_effect = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    for path in (root / "__init__.py", nested / "__init__.py", nested / "leaf.py"):
        path.write_text(side_effect, encoding="utf-8")
    (nested / "leaf.pyi").write_text("def step(x: int) -> int: ...\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / "lookup.bee"
    path.write_text(
        "use py:b_lookup_fixture.nested.leaf as lib\n"
        "fn native(x: Int) -> Int = x + 1\nprint lib.step(1)\n", encoding="utf-8")
    assert main(["check", str(path), "--strict"]) == 0
    capsys.readouterr()
    assert main(["discover", str(path), "--function", "native", "--json"]) == 0
    assert not marker.exists()
    assert not any(name.startswith("b_lookup_fixture") for name in sys.modules)


def test_lookup_preserves_builtins_and_nested_namespace_locations(tmp_path, monkeypatch):
    for segment in ("left", "right"):
        branch = tmp_path / segment / "b_lookup_namespace" / "nested"
        branch.mkdir(parents=True)
        (branch / f"{segment}.py").write_text("def f(x: int) -> int: return x\n")
        monkeypatch.syspath_prepend(str(branch.parents[1]))
    assert inspect_python("sys").source_kind == "binary-or-namespace"
    assert inspect_python("b_lookup_namespace.nested").source_kind == "binary-or-namespace"
    for segment in ("left", "right"):
        assert "f" in inspect_python(f"b_lookup_namespace.nested.{segment}").signatures
    assert "b_lookup_namespace" not in sys.modules


def test_lookup_stops_at_a_nonpackage(tmp_path, monkeypatch):
    (tmp_path / "b_lookup_leaf.py").write_text("pass\n")
    (tmp_path / "coincidental_name.py").write_text("def f(x: int) -> int: return x\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert inspect_python("b_lookup_leaf.coincidental_name").source_kind == "unavailable"
    with pytest.raises(BError, match="E_IMPORT"):
        compile_b("use py:b_lookup_leaf.coincidental_name as lib")
    with pytest.raises(BError, match="E_ADOPT"):
        compile_b("adopt py:b_lookup_leaf.coincidental_name.f as f")


def test_an_untrusted_annotation_is_not_evaluated(tmp_path, monkeypatch):
    path = tmp_path / 'b_bad_annotations.py'
    path.write_text('def trick(x: __import__("os").system("touch pwned")) -> int: return 1\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    inspected = inspect_python('b_bad_annotations')
    assert 'trick' not in inspected.signatures
    assert not (tmp_path / 'pwned').exists()


def test_discovery_supports_overloads_and_dicts_but_skips_unknown_types(tmp_path, monkeypatch):
    (tmp_path / 'b_unsupported.py').write_text('def f(x): return x\n', encoding='utf-8')
    (tmp_path / 'b_unsupported.pyi').write_text(
        'from typing import overload\n'
        '@overload\ndef f(x: int) -> int: ...\n'
        '@overload\ndef f(x: str) -> str: ...\n'
        'def f(x: object) -> object: ...\n'
        'def g(x: dict[str, int]) -> int: ...\n'
        'def unsupported(x: tuple[int, str]) -> int: ...\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    found = inspect_python('b_unsupported')
    assert set(found.signatures) == {'f', 'g'}
    assert 'unsupported' in found.skipped
    result = compile_b('use py:b_unsupported as m\nprint m.f(2)', strict=True)
    assert result.diagnostics == []
    with pytest.raises(BError, match='E_STRICT'):
        compile_b('use py:b_unsupported as m\nprint m.unsupported(2)', strict=True)


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
    for ext in ('.bee', '.b4', '.bsrc', '.b'):
        path = tmp_path / ('ok'+ext)
        path.write_text('print 5\n', encoding='utf-8')
        assert main(['check', str(path), '--strict']) == 0
        capsys.readouterr()
    path = tmp_path / 'berry.be'
    path.write_text('print 5\n', encoding='utf-8')
    assert main(['check', str(path), '--json']) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['error']['code'] == 'E_EXTENSION'
