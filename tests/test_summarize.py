"""Source-level semantics of typed reductions over B lists."""
import importlib
import json

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.lowering import PythonLowerer
from b_lang.runtime import BBoundaryError
from b_lang.types import BError


PROFILE = """fn profile(xs: List[Int], limit: Int) -> Dict[Text,Int] pure = summarize x in xs {
    size: count
    net: sum x
    high: count where x >= limit
    excess: sum (x - limit) where x > limit
    lo: min x default -7
    hi: max x default 9
}"""


@pytest.mark.parametrize("optimized", [False, True])
def test_profile_matches_scalar_oracle(optimized):
    compiled = compile_b(PROFILE, strict=True)
    code = (compiled.code if optimized else
            compile(PythonLowerer().lower(compiled.ir), "<raw BIR>", "exec"))
    namespace = {}
    exec(code, namespace)
    for values in ([], [13], [-20], [0, 13, 5, 5], [2**125, -(2**160), 2**92]):
        for limit in (0, 5):
            assert namespace["profile"](values, limit) == {
                "size": len(values), "net": sum(values),
                "high": sum(x >= limit for x in values),
                "excess": sum(max(0, x - limit) for x in values),
                "lo": min(values, default=-7), "hi": max(values, default=9),
            }
    with pytest.raises(BBoundaryError):
        namespace["profile"]([1, True], 0)


def test_bindings_are_lexical_and_soft_keywords_still_work():
    source = """fn summarize(where: Int) -> Int pure = where + 1
fn test(xs: List[Int], target: Int) -> Dict[Text,Int] pure = summarize class in xs {
    hits: count where (summarize default in [1, 2] { net: sum (class * default) }) == {"net": target}
    sum: sum summarize(class)
}
let data = test([4, 5, 4], 12)"""
    namespace = {}
    exec(compile_b(source, strict=True).code, namespace)
    assert namespace["data"] == {"hits": 2, "sum": 16}


def test_optional_source_and_nonnumeric_items():
    source = """fn words(xs: Option[List[Text]], needle: Text) -> Dict[Text,Int] pure = summarize x in (xs ?? [needle]) { n: count; hits: count where x == needle }"""
    namespace = {}
    exec(compile_b(source, strict=True).code, namespace)
    assert namespace["words"](None, "cat") == {"n": 1, "hits": 1}
    assert namespace["words"](["dog", "cat", "dog"], "dog") == {"n": 3, "hits": 2}
    assert namespace["words"]([], "cat") == {"n": 0, "hits": 0}


def test_observable_order_and_lazy_expressions(tmp_path, monkeypatch):
    module = "b_summary_event_recorder"
    (tmp_path / f"{module}.py").write_text("""
events = []
def source():
    events.append("source")
    return [1, 0, -1]
def mark(field, value):
    events.append((field, value))
    return value
def choose(value):
    events.append(("guard", value))
    return value != 0
""", encoding="utf-8")
    (tmp_path / f"{module}.pyi").write_text("""
def source() -> list[int]: ...
def mark(field: str, value: int) -> int: ...
def choose(value: int) -> bool: ...
""", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    source = f"""use py:{module} as recorder
fn work(active: Bool) -> Dict[Text,Int] = if active then summarize x in recorder.source() {{
    a: min recorder.mark("min", x) default -100
    b: sum recorder.mark("sum", x) where recorder.choose(x)
    c: max recorder.mark("max", x) default 100
}} else {{"skipped": 1}}"""
    compiled = compile_b(source, strict=True)
    recorder = importlib.import_module(module)
    namespace = {}
    exec(compiled.code, namespace)
    assert namespace["work"](False) == {"skipped": 1}
    assert recorder.events == []
    assert namespace["work"](True) == {"a": -1, "b": 0, "c": 1}
    assert recorder.events == [
        "source", ("min", 1), ("guard", 1), ("sum", 1), ("max", 1),
        ("min", 0), ("guard", 0), ("max", 0),
        ("min", -1), ("guard", -1), ("sum", -1), ("max", -1),
    ]
    with pytest.raises(BError, match="E_EFFECT"):
        compile_b(source.replace(" = if active", " pure = if active"))


@pytest.mark.parametrize("expression,code", [
    ("summarize x in 42 { n: count }", "E_TYPE"),
    ('summarize x in ["a"] { n: sum x }', "E_TYPE"),
    ("summarize x in [true] { n: max x default 0 }", "E_TYPE"),
    ("summarize x in [1] { n: count where x }", "E_TYPE"),
    ("summarize x in [x] { n: count }", "E_NAME"),
    ("summarize _b_temp in [1] { n: count }", "E_NAME"),
])
def test_rejects_wrong_types_and_out_of_scope_names(expression, code):
    with pytest.raises(BError) as error:
        compile_b(f"let result = {expression}")
    assert error.value.code == code


@pytest.mark.parametrize("fields", [
    "n: count; n: sum x", "n: min x", "n: max x default 1.5",
])
def test_duplicate_and_incomplete_fields_rejected(fields):
    with pytest.raises(BError):
        compile_b(f"let result = summarize x in [1] {{ {fields} }}")


def test_cli_check_build_ir_and_run(tmp_path, capsys):
    path = tmp_path / "profile.bee"
    path.write_text(PROFILE + '\nprint profile([4, 8], 5)\n', encoding="utf-8")
    assert main(["check", str(path), "--strict", "--require-proofs"]) == 0
    capsys.readouterr()
    assert main(["ir", str(path), "--optimized"]) == 0
    ir = json.loads(capsys.readouterr().out)
    operation = ir["statements"][0]["expression"]["operands"][0]
    assert operation["op"] == "summarize" and operation["type"] == "Dict[Text, Int]"
    assert main(["build", str(path), "--strict"]) == 0
    built_source = capsys.readouterr().out
    exec(compile(built_source, str(path.with_suffix(".py")), "exec"), {})
    built_output = capsys.readouterr().out
    assert main(["run", str(path), "--strict"]) == 0
    assert capsys.readouterr().out == built_output
    assert "'excess': 3" in built_output


@pytest.mark.parametrize("field,valid,rejected", [
    ("sum x", [3, -1], [1, True]),
    ("count where x", [True, False, True], [True, 1]),
])
def test_untyped_items_receive_per_element_boundary_guards(field, valid, rejected):
    source = f"fn work(xs: List[Any]) -> Dict[Text,Int] = summarize x in xs {{ selected: {field} }}"
    with pytest.raises(BError, match="E_STRICT"):
        compile_b(source, strict=True)
    namespace = {}
    exec(compile_b(source).code, namespace)
    assert namespace["work"](valid) == {"selected": 2}
    with pytest.raises(BBoundaryError):
        namespace["work"](rejected)
