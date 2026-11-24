"""B 0.7 adoption: new B functions generated from a restricted Python subset."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from b_lang.adoption import adopt_python, audit_adoptable
from b_lang.compiler import compile_b
from b_lang.cli import main
from b_lang.types import BError


def _run(source: str):
    compiled = compile_b(source, strict=True)
    ns = {}
    exec(compiled.code, ns, ns)
    return compiled, ns


def _reject(source: str, code="E_ADOPT"):
    with pytest.raises(BError) as error:
        compile_b(source, strict=True)
    assert error.value.code == code


def test_adopt_native_function_runs_without_importing_python_library(monkeypatch):
    import sys
    sys.modules.pop("b_examples.pure_kernels", None)
    source = ("permit [console]\n"
              "adopt py:b_examples.pure_kernels.square as sq\n"
              "fn triple(x: Float) -> Float pure = sq(x) + sq(x) + sq(x)\n"
              "print triple(2.0)")
    compiled, ns = _run(source)
    assert ns["triple"](3.0) == 27.0
    assert "b_examples.pure_kernels" not in sys.modules
    assert compiled.ir.detected_effects == ("console",)
    assert compiled.ir.foreign_symbols == ()
    assert compiled.ir.statements[1].declared_pure
    assert compiled.ir.statements[1].backend == "py-source"
    assert "@sha256:" in compiled.ir.statements[1].target
    assert "_b_py('b_examples.pure_kernels')" not in compiled.source
    assert "def sq" in compiled.source


def test_adopt_int_conditional_and_reuse_native_contract():
    source = ("permit []\n"
              "adopt py:b_examples.pure_kernels.forward as step\n"
              "fn plus2(x: Int) -> Int pure requires x >= 0 ensures result > 0 = step(x) + 1")
    compiled = compile_b(source)
    assert not compiled.ir.detected_effects
    ns = {}
    exec(compiled.code, ns, ns)
    assert ns["plus2"](4) == 6
    from b_lang.runtime import BContractError, BBoundaryError
    with pytest.raises(BContractError):
        ns["plus2"](-1)
    with pytest.raises(BBoundaryError):
        ns["plus2"](2.5)


def test_adopt_ternary_and_boolean():
    src = "adopt py:b_examples.pure_kernels.clamp as c\nadopt py:b_examples.pure_kernels.positive as p"
    _, env = _run(src)
    assert env["c"](12., 0., 10.) == 10.
    assert env["c"](-4., 0., 10.) == 0.
    assert env["c"](4., 0., 10.) == 4.
    assert env["p"](6) is True
    assert env["p"](0) is False


@pytest.mark.parametrize("name", ["unsafe_global", "unsafe_call", "unsafe_default", "unsafe_statement"])
def test_rejects_unsupported_python(name):
    _reject(f"adopt py:b_examples.pure_kernels.{name} as safe")


def test_rejects_modules_without_source_and_nonexistent_names():
    _reject("adopt py:math.sqrt as sqrt")
    _reject("adopt py:b_examples.pure_kernels.missing as absent")


def test_runtime_exceptions_are_not_totality_proofs():
    _, env = _run("adopt py:b_examples.pure_kernels.ratio as ratio")
    with pytest.raises(ZeroDivisionError):
        env["ratio"](1.0, 0.0)


def test_audit_is_machine_readable_and_honest(capsys):
    result = audit_adoptable("b_examples.pure_kernels")
    assert result["public_top_level_functions"] == 9
    assert result["adoptable"] == 5
    assert "square" in result["accepted"]
    assert result["rejected"]["unsafe_call"]["code"] == "E_ADOPT"
    assert main(["adopt-audit", "py:b_examples.pure_kernels", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["adoptable"] == 5


def test_unknown_python_code_is_never_loaded_by_the_adopter(tmp_path, monkeypatch):
    # Importing this module would raise. Reading only its AST is permitted.
    pkg = tmp_path / "evil_leaf.py"
    pkg.write_text('raise RuntimeError("module executed")\ndef safe(x: int) -> int:\n    return x + 1\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    _, ns = _run("permit []\nadopt py:evil_leaf.safe as inc")
    assert ns["inc"](8) == 9
    import sys
    assert "evil_leaf" not in sys.modules


def test_sha_changes_when_source_changes(tmp_path, monkeypatch):
    pkg = tmp_path / "pureleaf.py"
    monkeypatch.syspath_prepend(str(tmp_path))
    pkg.write_text("def f(x: int) -> int:\n    return x + 1\n")
    old = adopt_python("pureleaf.f", "f")
    pkg.write_text("def f(x: int) -> int:\n    return x + 2\n")
    new = adopt_python("pureleaf.f", "f")
    assert old.sha256 != new.sha256
    assert new.statement.parts[3].parts[1].parts[0] == 2


def test_adopt_prevents_python_shadowed_or_wrong_runtime_types(tmp_path, monkeypatch):
    pkg = tmp_path / "broken.py"
    pkg.write_text("def wrong(x: int) -> int:\n    return x / 2\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    _reject("adopt py:broken.wrong as wrong", "E_TYPE")


def test_adopt_rejects_decorators_and_python_dynamic_constructs(tmp_path, monkeypatch):
    pkg = tmp_path / "restrictions.py"
    pkg.write_text("""
def wrapper(f):
    return f
@wrapper
def decorated(x: int) -> int:
    return x

def indexing(xs: list[int]) -> int:
    return xs[0]

def builtin(x: int) -> int:
    return abs(x)

def nested(x: int) -> int:
    return (x if x > 0 else 0) + 1
""")
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("decorated", "indexing", "builtin"):
        _reject(f"adopt py:restrictions.{name} as f")
    _, ns = _run("adopt py:restrictions.nested as f")
    assert ns["f"](-3) == 1
    assert ns["f"](4) == 5


def test_nested_package_initializers_are_not_executed(tmp_path, monkeypatch):
    package = tmp_path / "untouched_package"
    package.mkdir()
    (package / "__init__.py").write_text('raise RuntimeError("__init__ was executed")\n')
    (package / "leaf.py").write_text('def safe(x: int) -> int:\n    return x * 3\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    _, ns = _run("permit []\nadopt py:untouched_package.leaf.safe as safe")
    assert ns["safe"](5) == 15
    import sys
    assert "untouched_package" not in sys.modules
    assert "untouched_package.leaf" not in sys.modules


def test_unsupported_attribute_access_and_side_effecting_python_not_silently_accepted(tmp_path, monkeypatch):
    file = tmp_path / "untrusted.py"
    file.write_text("""
def mutate(x: int) -> int:
    return dangerous.store(x)

def read(x: int) -> int:
    return object.some_global

def choose(x: int) -> int:
    return x if x > 0 else 0
""")
    monkeypatch.syspath_prepend(str(tmp_path))
    for fn in ("mutate", "read"):
        _reject(f"permit []\nadopt py:untrusted.{fn} as f")
    _, ns = _run("permit []\nadopt py:untrusted.choose as f")
    assert ns["f"](-7) == 0


def test_editable_install_meta_path_finder_without_importing_package(tmp_path, monkeypatch):
    """An editable finder may locate a package that PathFinder cannot see."""
    import sys
    from importlib.machinery import ModuleSpec

    package = tmp_path / "virtual_editable_package"
    package.mkdir()
    (package / "__init__.py").write_text('raise RuntimeError("should not be imported")\n')
    (package / "leaf.py").write_text('def safe(x: int) -> int:\n    return x + 5\n')

    class EditableFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "virtual_editable_package":
                return None
            spec = ModuleSpec(fullname, loader=None, is_package=True)
            spec.submodule_search_locations = [str(package)]
            return spec

    monkeypatch.setattr(sys, "meta_path", [EditableFinder(), *sys.meta_path])
    _, ns = _run("permit []\nadopt py:virtual_editable_package.leaf.safe as f")
    assert ns["f"](7) == 12
    assert "virtual_editable_package" not in sys.modules


def test_fixed_example_tracks_the_adopted_body_without_importing_it(tmp_path, monkeypatch):
    provider = tmp_path / "tariff_probe.py"
    def write_rate(rate):
        provider.write_text(f'raise RuntimeError("imported provider")\n'
                            f'def fee(q: int) -> int:\n    return q * {rate}\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    source = "adopt py:tariff_probe.fee as fee\nexample fee(3) == 21\n"
    write_rate(7)
    compile_b(source, strict=True)
    write_rate(8)
    with pytest.raises(BError, match="program gives 24"):
        compile_b(source, strict=True)
