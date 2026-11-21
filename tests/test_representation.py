"""The checker, emitted Python and bytecode must agree at numeric type joins."""
import pytest

from b_lang.compiler import compile_b
from b_lang.types import BError


def test_inferred_float_preserves_strict_assertion_in_bytecode_and_source(capsys):
    program = compile_b(
        "let value = if true then 9007199254740993 else 0.0\n"
        "assert value == 9007199254740992.0\nprint value", strict=True)
    for code in (program.code, program.source):
        exec(code, {})
        assert capsys.readouterr().out == "9007199254740992.0\n"


@pytest.mark.parametrize("expression", [
    "(if true then 9007199254740993 else 0.0)",
    "((if true then 9007199254740993 else none) ?? 0.0)",
    "((if true then none else 0.0) ?? 9007199254740993)",
])
def test_direct_comparison_uses_the_rounded_branch_value(expression):
    with pytest.raises(BError, match="E_ASSERT"):
        compile_b(f"assert {expression} == 9007199254740993")
    compiled = compile_b(f"assert {expression} == 9007199254740992.0", strict=True)
    exec(compiled.code, {})


def test_widening_preserves_lazy_evaluation_and_nested_container_types():
    program = compile_b('''
fn pick(flag: Bool) -> Float = if flag then 0.5 else 9007199254740993
fn missing() -> Option[Float] = none
let nope: Option[Int] = 9
let present = nope ?? 0.5
let fallback = missing() ?? 8
let items = if true then {"nums": [1, 3]} else {"nums": [2.5]}
let mixed = [1, 2.5] + [3]
let record = {"first": 1, "last": 2.5}
let huge = HUGE_CONSTANT
let skipped = if true then 0.5 else huge
let also_skipped = (if true then 0.5 else none) ?? huge
'''.replace('HUGE_CONSTANT', str(10 ** 310)), strict=True)
    env = {}
    exec(program.code, env)
    assert env["pick"](False) == 9007199254740992.0
    assert type(env["present"]) is type(env["fallback"]) is float
    assert all(type(n) is float for n in env["items"]["nums"])
    assert all(type(n) is float for n in env["mixed"])
    assert all(type(n) is float for n in env["record"].values())
    assert env["skipped"] == env["also_skipped"] == 0.5


def test_python_backend_respects_b_names_in_emitted_code(capsys):
    program = compile_b('''
use py:math as class
fn return(lambda: Int) -> Int requires lambda >= 0 ensures result >= 0 = lambda
let __debug__ = 1
let print = 7
print class.sqrt(return(print + __debug__ + 1))
''', strict=True)
    for code in (program.code, program.source):
        exec(code, {})
        assert capsys.readouterr().out == "3.0\n"


def test_foreign_attribute_named_python_keyword_is_preserved(tmp_path, monkeypatch, capsys):
    (tmp_path / "b_foreign_keyword.py").write_text('globals()["class"] = 7\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    program = compile_b("use py:b_foreign_keyword as lib\nprint lib.class")
    for code in (program.code, program.source):
        exec(code, {})
        assert capsys.readouterr().out == "7\n"


@pytest.mark.parametrize("typ", ["Dict[Text, Int]", "Option[Int]", "List[Dict[Text, Int]]",
                                "List[List[Option[Int]]]", "None"])
def test_unordered_type_rejected_even_inside_a_postcondition(typ):
    source = f"fn f(d: {typ}) -> Int pure ensures d < d or true = 1"
    with pytest.raises(BError, match="E_TYPE.*cannot order"):
        compile_b(source)


def test_supported_ordering_and_structural_equality_remain_available():
    source = '''
fn eq(a: Dict[Text, Int], b: Dict[Text, Int]) -> Bool = a == b
fn earlier(a: List[List[Text]], b: List[List[Text]]) -> Bool = a < b
fn le(a: Bool, b: Bool) -> Bool = a <= b
fn gt(a: Int, b: Float) -> Bool = a > b
'''
    env = {}
    exec(compile_b(source, strict=True).code, env)
    assert env["eq"]({"k": 1}, {"k": 1})
    assert env["earlier"]([["a"]], [["b"]])
    assert env["le"](False, True)
    assert env["gt"](5, 4.5)
