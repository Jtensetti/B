"""B's Node calls share a worker and preserve the supported typed boundary."""
import json
import math
from pathlib import Path
import shutil

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.runtime import BBoundaryError
from b_lang.types import BError


NODE = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
PACKAGE = 'use js:"@fixture/tool-box" as lib\n'


def put_package(root, name, body, version="1.0.0"):
    folder = root / "node_modules" / name
    folder.mkdir(parents=True)
    (folder / "package.json").write_text(json.dumps({"name": name, "version": version, "main": "index.cjs"}))
    (folder / "index.cjs").write_text(body)
    return folder


def execute(root, source):
    ns = {"__file__": str(root / "main.bee")}
    try:
        exec(compile_b(source, strict=True).code, ns)
        return ns
    finally:
        if "_b_js_session" in ns:
            ns["_b_js_session"].close()


def test_bir_and_inspect_record_assumptions_without_node(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    source = 'use js:semver as v\nprint v.satisfies("1.2.0", "^1")\n'
    c = compile_b(source, strict=True)
    row, = c.ir.to_dict()["foreign_symbols"]
    assert row["path"] == "js:semver.satisfies"
    assert row["adapter"] == "js" and row["backend"] == "js" and row["verified_behavior"] is False
    assert row["provenance"] == "curated-semver-7" and c.assumptions
    assert main(["inspect", "js:semver", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {s["name"] for s in data["signatures"]} == {"valid", "maxSatisfying", "satisfies", "compare"}
    assert data["installed_version_checked"] is False
    assert main(["inspect", "js:other-pkg", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["provenance"] == "declaration-required"
    with pytest.raises(BBoundaryError, match="Node.js is required"):
        exec(c.code, {})


@pytest.mark.parametrize("source, error", [
    ("use js:versioner as v\nprint v.major(1)", "E_FOREIGN"),
    (PACKAGE + "foreign lib.inner.deep(Int) -> Int", "E_FOREIGN"),
    (PACKAGE + "foreign lib.opaque(List[Any]) -> Text", "E_FOREIGN"),
    (PACKAGE + "foreign lib._name(Int) -> Int", "E_FOREIGN"),
    ('use js:"./relative.cjs" as lib', "E_IMPORT"),
    ('use js:"https://example.org/mod.js" as lib', "E_IMPORT"),
    ('use js:"node:path/posix" as p\nforeign p.other(Int) -> Int', "E_FOREIGN"),
    ('use js:semver as v\nforeign v.compare(Text, Text) -> Int', "E_FOREIGN"),
    ('permit []\nuse js:semver as v', "E_EFFECT"),
    ('use js:semver as v\nfn good(s: Text) -> Bool pure = v.satisfies(s, "^1")', "E_EFFECT"),
])
def test_js_requires_named_concrete_signatures_and_foreign_effect(source, error):
    with pytest.raises(BError) as caught:
        compile_b(source)
    assert caught.value.code == error


@NODE
def test_standard_library_curated_paths_and_module_alias(tmp_path):
    ns = execute(tmp_path, '''use js:"node:path/posix" as p
let other = p
let answer = other.join("/one", "two/../three")
let ext = p.extname("one.bee")
''')
    assert (ns["answer"], ns["ext"]) == ("/one/three", ".bee")


@NODE
def test_declared_cjs_shares_state_between_imports_and_resets_between_programs(tmp_path):
    put_package(tmp_path, "@fixture/tool-box", """
        let n = 0;
        exports.next = () => ++n;
        exports.empty = () => null;
        Object.defineProperty(exports, "current", {get() { ++n; return () => n; }});

    """)
    source = PACKAGE + '''foreign lib.next() -> Int
foreign lib.empty() -> Option[Text]
foreign lib.current() -> Int
use js:"@fixture/tool-box" as again
let first = lib.next()
let second = again.next()
let third = again.current()
let no_text = lib.empty() ?? "fallback"
'''
    for _ in range(2):
        ns = execute(tmp_path, source)
        assert (ns["first"], ns["second"], ns["third"], ns["no_text"]) == (1, 2, 3, "fallback")


@NODE
def test_cli_resolves_packages_next_to_program_and_keeps_package_logs_off_protocol(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    put_package(project, "@fixture/tool-box", 'console.log("hello from JS"); exports.answer = () => 42;')
    src = project / "main.bee"
    src.write_text(PACKAGE + "foreign lib.answer() -> Int\nprint lib.answer()\n")
    monkeypatch.chdir(tmp_path)
    assert main(["run", str(src)]) == 0
    assert capsys.readouterr().out == "42\n"


@NODE
def test_import_never_executes_during_check_and_semver_catalog_is_version_scoped(tmp_path):
    marker = tmp_path / "loaded"
    put_package(tmp_path, "semver",
                f"require('node:fs').writeFileSync({json.dumps(str(marker))}, 'yes')", version="6.0.0")
    c = compile_b('use js:semver as v\nprint v.valid("1.2.3") ?? ""\n', strict=True)
    assert not marker.exists()
    ns = {"__file__": str(tmp_path / "main.bee")}
    try:
        with pytest.raises(BBoundaryError, match="requires version 7"):
            exec(c.code, ns)
    finally:
        ns["_b_js_session"].close()
    assert not marker.exists()


@NODE
def test_typed_transport_preserves_negative_zero_nested_null_and_text_dictionary(tmp_path):
    put_package(tmp_path, "@fixture/tool-box",
                "exports.echo = obj => obj; exports.hasNegativeZero = n => Object.is(n, -0);")
    source = PACKAGE + '''foreign lib.echo(Dict[Text,List[Option[Float]]]) -> Dict[Text,List[Option[Float]]]
foreign lib.hasNegativeZero(Float) -> Bool
let nested = lib.echo({"__proto__": [-0.0, none, 1.25], "雪": [none]})
let check = lib.hasNegativeZero(-0.0)
'''
    ns = execute(tmp_path, source)
    assert ns["check"] is True
    assert ns["nested"] == {"__proto__": [0.0, None, 1.25], "雪": [None]}
    assert math.copysign(1, ns["nested"]["__proto__"][0]) < 0


@NODE
def test_reports_wrong_values_without_replacing_state_or_replaying_calls(tmp_path):
    put_package(tmp_path, "@fixture/tool-box", """
        let n = 0;
        exports.fail = () => { ++n; throw Error("failed call"); };
        exports.count = () => n;
        exports.echo = x => {++n; return x;};
        exports.badInt = () => 9007199254740992;
        exports.promised = async () => true;
        exports.hole = () => Array(3);
        exports.weird = () => new Date();
        exports.undef = () => undefined;
    """)
    source = PACKAGE + '''
foreign lib.fail() -> Int
foreign lib.count() -> Int
foreign lib.echo(List[Int]) -> List[Int]
foreign lib.badInt() -> Int
foreign lib.promised() -> Bool
foreign lib.hole() -> List[Int]
foreign lib.weird() -> Dict[Text,Int]
foreign lib.undef() -> Option[Int]
foreign lib.missing() -> Int
fn fail() -> Int = lib.fail()
fn count() -> Int = lib.count()
fn echo(xs: List[Int]) -> List[Int] = lib.echo(xs)
fn badInt() -> Int = lib.badInt()
fn promised() -> Bool = lib.promised()
fn hole() -> List[Int] = lib.hole()
fn weird() -> Dict[Text,Int] = lib.weird()
fn undef() -> Option[Int] = lib.undef()
fn missing() -> Int = lib.missing()
'''
    ns = {"__file__": str(tmp_path / "main.bee")}
    try:
        exec(compile_b(source, strict=True).code, ns)
        for name in ["fail", "badInt", "promised", "hole", "weird", "undef", "missing"]:
            with pytest.raises(BBoundaryError):
                ns[name]()
        for value in (2**53, -(2**53)):
            with pytest.raises(BBoundaryError, match="safe integer"):
                ns["echo"]([value])
        assert ns["count"]() == 1
        assert ns["echo"]([2**53 - 1, 1 - 2**53]) == [2**53 - 1, 1 - 2**53]
    finally:
        ns["_b_js_session"].close()
