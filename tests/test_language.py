import io
from contextlib import redirect_stdout
import pytest
from b_lang.compiler import compile_b
from b_lang.types import BError


def run(source, strict=False):
    result = compile_b(source, strict=strict)
    stream = io.StringIO()
    with redirect_stdout(stream):
        namespace = {"__name__": "__b_program__"}
        exec(result.code, namespace, namespace)
    return stream.getvalue(), result


def test_native_arithmetic_and_function():
    out, result = run("fn square(x: Int) -> Int = x * x\nlet x = square(7)\nprint x\n", strict=True)
    assert out.strip() == "49"
    assert "def square" in result.source


def test_native_expression_precedence():
    out, _ = run("print 2 + 3 * 4\nprint (2 + 3) * 4\n", strict=True)
    assert out.splitlines() == ["14", "20"]


def test_types_and_boolean():
    out, _ = run('let n: Int = 3\nassert n > 2 and not false\nprint "ok"\n')
    assert out.strip() == "ok"


def test_python_standard_library():
    out, _ = run("use py:statistics as stats\nprint stats.mean([1, 2, 3])\n", strict=True)
    assert out.strip() == "2"


def test_math_constant_known():
    out, _ = run("use py:math as math\nprint math.pi\n", strict=True)
    assert out.startswith("3.14159")


@pytest.mark.parametrize("source,code", [
    ('let x: Int = "wrong"', "E_TYPE"),
    ("let x = z", "E_NAME"),
    ("print 1 / 0", "E_DIV_ZERO"),
    ("assert false", "E_ASSERT"),
    ("let x = (4 +", "E_SYNTAX"),
    ("fn f(x: Int) -> Int = x\nprint f(1, 2)", "E_ARITY"),
    ("use net:System.Math as Math\nprint Math.DoesNotExist(1)", "E_FOREIGN"),
    ("fn f(x: Int) -> Int = x\nlet x = 2\nlet x = 3", "E_NAME"),
    ('let x: List[Int] = [1, "wrong"]', "E_TYPE"),
])
def test_preflight_rejects(source, code):
    with pytest.raises(BError) as err: compile_b(source)
    assert err.value.code == code


def test_constant_propagation():
    with pytest.raises(BError) as err:
        compile_b("let x = 2 + 2\nassert x == 5")
    assert err.value.code == "E_ASSERT"


def test_runtime_obligation_not_claimed_proven():
    checked = compile_b("fn f(x: Int) -> Int = x + 1\nassert f(1) == 2")
    assert [d.code for d in checked.diagnostics] == ["W_RUNTIME_ASSERT"]
    with pytest.raises(BError) as err:
        compile_b("fn f(x: Int) -> Int = x + 1\nassert f(1) == 2", strict=True)
    assert err.value.code == "E_STRICT"


def test_unknown_python_library_is_explicitly_unverified():
    source = 'use py:json as json\nprint json.dumps([1,2,3])'
    out, checked = run(source)
    assert out.strip() == '[1, 2, 3]'
    assert [d.code for d in checked.diagnostics] == ["W_UNCHECKED_FOREIGN"]
    with pytest.raises(BError) as err: compile_b(source, strict=True)
    assert err.value.code == "E_STRICT"


def test_import_missing():
    with pytest.raises(BError) as err:
        compile_b("use py:there_is_no_b_package_999 as x\nprint x")
    assert err.value.code == "E_IMPORT"


def test_dotnet_typed_import_checks_without_sdk():
    result = compile_b("use net:System.Math as Math\nlet z: Float = Math.Sqrt(81.0)\nprint z", strict=True)
    assert not result.diagnostics
    assert "Math.Sqrt" in result.source


def test_generated_python_syntax_is_valid():
    import ast
    result = compile_b("use py:statistics as stats\nlet m = stats.mean([1,2,3])\nprint m")
    ast.parse(result.source)


def test_unknown_foreign_attribute_is_not_silently_proven():
    source = 'use py:math as math\nlet external = math.tau\nprint external'
    value, report = run(source)
    assert float(value.strip()) > 6
    assert any(d.code == "W_UNCHECKED_FOREIGN" for d in report.diagnostics)
    with pytest.raises(BError) as err: compile_b(source, strict=True)
    assert err.value.code == "E_STRICT"
