"""The v0.2 experiments: structural branches, typed foreign functions, boundary guards."""
import io
import json
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.runtime import BBoundaryError
from b_lang.types import BError


def run_b(source: str, *, strict: bool = True):
    checked = compile_b(source, strict=strict)
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exec(checked.code, {"__name__": "__b_test__"})
    return stdout.getvalue(), checked


def test_if_expression_is_b_code_and_is_statically_evaluated():
    out, checked = run_b('let value: Int = if 2 > 1 then 15 else 7\nassert value == 15\nprint value')
    assert out.strip() == '15'
    assert not checked.diagnostics


def test_if_nested_and_lazy_evaluation():
    src = '''fn decide(x: Int) -> Text = if x > 10 then "large" else if x > 0 then "small" else "zero"
print decide(4)
'''
    out, _ = run_b(src)
    assert out.strip() == 'small'


def test_if_rejects_inconsistent_branch_types():
    with pytest.raises(BError, match="incompatible types"):
        compile_b('let score = if true then "text" else 5')


def test_if_requires_boolean_condition():
    with pytest.raises(BError, match="if condition"):
        compile_b('print if 2 then 1 else 3')


def test_foreign_declared_library_function_no_builtin_registry_entry():
    src = '''use py:statistics as stats
foreign stats.median(List[Float]) -> Float
let m: Float = stats.median([10, 20, 30])
print m
'''
    stdout, checked = run_b(src)
    assert stdout.strip() == '20.0'
    assert checked.assumptions == ['py:statistics.median(List[Float]) -> Float']
    assert not checked.diagnostics


def test_typed_json_library_contract():
    source = '''use py:json as json
foreign json.dumps(List[Int]) -> Text
print json.dumps([1, 2, 3])'''
    output, compiled = run_b(source)
    assert json.loads(output) == [1, 2, 3]
    assert len(compiled.assumptions) == 1


def test_foreign_signature_arg_type_error():
    source = '''use py:statistics as stats
foreign stats.median(List[Float]) -> Float
print stats.median(["wrong"])'''
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert exc.value.code == 'E_TYPE'


def test_foreign_signature_arg_count_error():
    source = '''use py:statistics as stats
foreign stats.median(List[Float]) -> Float
print stats.median([1], [2])'''
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert exc.value.code == 'E_ARITY'


def test_foreign_requires_existing_import():
    with pytest.raises(BError) as exc:
        compile_b('foreign stats.median(List[Float]) -> Float')
    assert exc.value.code == 'E_FOREIGN'


def test_foreign_redefinition_is_rejected():
    source = '''use py:statistics as stats
foreign stats.mean(List[Int]) -> Float'''
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert exc.value.code == 'E_FOREIGN'


def test_custom_net_binding_cannot_bypass_host_allowlist():
    source = '''use net:System.Math as Math
foreign Math.Unknown(Float) -> Float'''
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert exc.value.code == 'E_FOREIGN'


def test_foreign_return_type_is_guarded_not_trusted():
    source = '''use py:json as json
foreign json.dumps(List[Int]) -> Int
print json.dumps([1, 2, 3])'''
    checked = compile_b(source, strict=True)
    with pytest.raises(BBoundaryError, match='Expected Int'):
        exec(checked.code, {})


def test_recursive_dynamic_guard_nested_list():
    source = '''use py:json as json
let unknown = json.loads("[1, \"oops\"]")
let typed: List[Int] = unknown
print typed'''
    # Runtime dynamic boundary is guarded even when the static annotation is a list.
    # Use a valid B string representation of a JSON string, without a broken double escape.
    source = 'use py:json as json\nlet unknown = json.loads("[1, \\\"oops\\\"]")\nlet typed: List[Int] = unknown\nprint typed'
    compiled = compile_b(source)
    assert {d.code for d in compiled.diagnostics} == {'W_UNCHECKED_FOREIGN', 'W_DYNAMIC_TYPE'}
    with pytest.raises(BBoundaryError, match='Expected Int'):
        exec(compiled.code, {})


def test_static_mixed_list_rejected_earlier_in_v04():
    # Both element types are already known: no need to defer to runtime.
    source = 'let mixed = [1, "wrong"]\nlet ints: List[Int] = mixed\nprint ints'
    with pytest.raises(BError, match='E_TYPE'):
        compile_b(source)


def test_if_cannot_hide_wrong_type_in_dead_branch():
    source = 'print if true then 1 else "wrong"'
    with pytest.raises(BError):
        compile_b(source)


def test_dotnet_regex_static_types_checked_without_dotnet_sdk():
    source = '''use net:System.Text.RegularExpressions.Regex as Rx
let ok: Bool = Rx.IsMatch("abc-123", "^[a-z]+-[0-9]+$")
print ok'''
    checked = compile_b(source, strict=True)
    assert not checked.diagnostics
    assert "Rx.IsMatch" in checked.source


def test_dotnet_regex_bad_types_rejected_before_run():
    source = '''use net:System.Text.RegularExpressions.Regex as Rx
print Rx.IsMatch(15, "hello")'''
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert exc.value.code == 'E_TYPE'
