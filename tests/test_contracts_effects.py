"""v0.6 language guarantees: static proofs are narrow; effects are conservative."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.runtime import BBoundaryError, BContractError
from b_lang.types import BError


def execute(source: str, strict: bool = True):
    compiled = compile_b(source, strict=strict)
    ns = {}
    with redirect_stdout(io.StringIO()) as out:
        exec(compiled.code, ns, ns)
    return out.getvalue().strip(), ns, compiled


def rejects(source: str, code: str):
    with pytest.raises(BError) as error:
        compile_b(source)
    assert error.value.code == code


def test_pure_verified_integer_contract_in_ir_and_execution():
    src = '''permit [console]
fn increment(x: Int) -> Int pure requires x >= 0 ensures result > 0 = x + 1
print increment(41)'''
    output, ns, compiled = execute(src)
    assert output == "42"
    stmt = compiled.ir.to_dict()["statements"][1]
    assert stmt["postcondition_status"] == "proved-interval"
    assert stmt["effects"] == [] and stmt["declared_pure"] is True
    assert compiled.ir.detected_effects == ("console",)
    assert compiled.ir.permitted_effects == ("console",)
    assert ns['increment'](5) == 6


def test_function_argument_guard_is_checked_when_called_from_python():
    _, ns, _ = execute('fn f(x: Int) -> Int pure = x + 1')
    with pytest.raises(BBoundaryError):
        ns['f']('wrong')
    with pytest.raises(BBoundaryError):
        ns['f'](True)


def test_precondition_is_checked_at_runtime_even_if_checker_proved_a_call():
    _, ns, _ = execute('fn pos(x: Int) -> Int pure requires x > 0 ensures result > 0 = x')
    with pytest.raises(BContractError, match='Precondition'):
        ns['pos'](-1)
    assert ns['pos'](1) == 1


def test_provably_false_precondition_call_rejected_before_running():
    rejects('fn pos(x: Int) -> Int requires x > 0 = x\nprint pos(0)', 'E_PRECONDITION')
    rejects('fn pos(x: Int) -> Int requires x > 0 = x\nlet n = 0\nprint pos(n)', 'E_PRECONDITION')


def test_unknown_precondition_requires_runtime_check_and_blocks_strict():
    src = 'fn positive(x: Int) -> Int requires x > 0 = x\nfn use(x: Int) -> Int = positive(x)'
    c = compile_b(src)
    assert 'W_RUNTIME_PRECONDITION' in [d.code for d in c.diagnostics]
    with pytest.raises(BError) as e:
        compile_b(src, strict=True)
    assert e.value.code == 'E_STRICT'
    ns = {}
    exec(c.code, ns, ns)
    with pytest.raises(BContractError):
        ns['use'](0)


def test_runtime_postcondition_is_not_labeled_proved():
    src = 'fn pred(x: Int) -> Int pure requires x >= 0 ensures result >= 0 = x - 1'
    c = compile_b(src)
    assert c.ir.statements[0].verification == 'runtime-check'
    assert 'W_RUNTIME_POSTCONDITION' in [d.code for d in c.diagnostics]
    with pytest.raises(BError) as e: compile_b(src, strict=True)
    assert e.value.code == 'E_STRICT'
    ns = {}
    exec(c.code, ns, ns)
    assert ns['pred'](2) == 1
    with pytest.raises(BContractError, match='Postcondition'):
        ns['pred'](0)


def test_disproven_postcondition_rejected():
    rejects('fn bad(x: Int) -> Int requires x >= 0 ensures result < 0 = x + 1', 'E_POSTCONDITION')


def test_contradictory_preconditions_rejected():
    rejects('fn no(x: Int) -> Int requires x >= 9 and x < 4 = x', 'E_PRECONDITION_EMPTY')
    rejects('fn no(x: Int) -> Int requires false = x', 'E_PRECONDITION_EMPTY')


def test_reverse_comparison_and_ranges_prove():
    src = 'fn clamp_pos(x: Int) -> Int pure requires 0 <= x and x <= 10 ensures result < 12 = x + 1'
    assert compile_b(src, strict=True).ir.statements[0].verification == 'proved-interval'


def test_interval_does_not_prove_unsupported_arithmetic():
    src = 'fn square(x: Int) -> Int ensures result >= 0 = x * x'
    compiled = compile_b(src)
    assert compiled.ir.statements[0].verification == 'runtime-check'
    assert len(compiled.diagnostics) == 1


def test_float_widening_does_not_inherit_integer_proof():
    src = '''fn f(x: Int) -> Float pure requires x == 9007199254740992
ensures result == 9007199254740993 = x + 1'''
    # Current syntax is intentionally one statement per line.
    src = src.replace('\nensures', ' ensures')
    compiled = compile_b(src)
    assert compiled.ir.statements[0].verification == 'runtime-check'
    with pytest.raises(BError):
        compile_b(src, strict=True)
    ns = {}
    exec(compiled.code, ns, ns)
    with pytest.raises(BContractError):
        ns['f'](9007199254740992)


def test_contract_predicates_reject_executable_calls():
    rejects('fn f(x: Int) -> Int ensures f(result) == 1 = x', 'E_CONTRACT')
    rejects('use py:math as m\nfn f(x: Float) -> Float ensures m.sqrt(result) > 0 = x', 'E_CONTRACT')


def test_contract_scopes_cannot_reference_global_state():
    rejects('let secret = 9\nfn f(x: Int) -> Int requires x < secret = x', 'E_CONTRACT')
    rejects('fn f(x: Int) -> Int ensures other > result = x', 'E_NAME')
    rejects('fn f(result: Int) -> Int ensures result >= 0 = result', 'E_CONTRACT')


def test_pure_rejects_untrusted_python_even_with_typed_stub():
    rejects('use py:statistics as stats\nfn mean(x: List[Float]) -> Float pure = stats.mean(x)', 'E_EFFECT')


def test_pure_rejects_net_and_unchecked_python():
    rejects('use net:System.Math as m\nfn root(x: Float) -> Float pure = m.Sqrt(x)', 'E_EFFECT')
    rejects('use py:math as m\nfn pi() -> Float pure = m.pi', 'E_EFFECT')


def test_pure_function_cannot_call_effectful_b_function():
    rejects('use py:math as m\nfn a(x: Float) -> Float = m.sqrt(x)\nfn b(x: Float) -> Float pure = a(x)', 'E_EFFECT')


def test_known_pure_functions_composable():
    src = 'fn a(x: Int) -> Int pure = x + 1\nfn b(x: Int) -> Int pure = a(x) * 2\nprint b(3)'
    output, _, compiled = execute(src)
    assert output == '8'
    assert compiled.ir.statements[1].effects == ()


def test_pure_function_disallows_captured_mutable_or_unknown_global():
    rejects('let items: List[Int] = [1,2]\nfn f(x: Int) -> List[Int] pure = items', 'E_EFFECT')
    rejects('use py:math as m\nlet n = m.tau\nfn f(x: Float) -> Float pure = n + x', 'E_EFFECT')


def test_pure_function_allows_known_scalar_constant():
    _, ns, _ = execute('let two: Int = 2\nfn twice(x: Int) -> Int pure = two * x')
    assert ns['twice'](4) == 8


def test_program_effect_capabilities_reject_disallowed_code():
    rejects('permit []\nprint 1', 'E_EFFECT')
    rejects('permit [console]\nuse py:math as m\nprint m.pi', 'E_EFFECT')
    rejects('permit []\nuse py:math as m', 'E_EFFECT')


def test_permit_accepts_only_explicit_supported_categories():
    rejects('permit [console, console]\nprint 1', 'E_EFFECT')
    rejects('permit [network]\nprint 1', 'E_EFFECT')
    rejects('print 1\npermit [console]', 'E_EFFECT')
    rejects('permit []\npermit []\nlet x = 1', 'E_EFFECT')


def test_foreign_capability_allows_call_but_does_not_prove_behavior():
    src = '''permit [foreign, console]
use py:statistics as stats
let avg: Float = stats.mean([1.0,2.0,3.0])
print avg'''
    output, _, compiled = execute(src)
    assert output == '2.0'
    assert compiled.ir.detected_effects == ('console', 'foreign')
    assert compiled.ir.to_dict()['behavior_proven'] is False


def test_program_permission_can_allow_empty_program():
    assert compile_b('permit []\nlet x = 2 + 3', strict=True).ir.detected_effects == ()


def test_effects_in_function_are_conservatively_reported():
    src = 'use py:math as m\nfn root(x: Float) -> Float = m.sqrt(x)'
    summary = compile_b(src, strict=True).ir.to_dict()
    assert summary['statements'][1]['effects'] == ['foreign']
    assert summary['detected_effects'] == ['foreign']


def test_json_cli_distinguishes_proved_and_runtime_checks(tmp_path, capsys):
    path = tmp_path / 'contracts.bee'
    path.write_text('''permit [console]
fn square_pos(x: Int) -> Int pure requires x >= 0 ensures result >= 0 = x * x
print square_pos(5)''')
    # x*x is conservatively not proved when x is unbounded.
    assert main(['check', str(path), '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'accepted'
    assert report['permitted_effects'] == ['console']
    assert report['detected_effects'] == ['console']
    assert report['function_contracts'][0]['postcondition_status'] == 'runtime-check'
    assert report['behavior_proven'] is False
    assert main(['check', str(path), '--strict', '--json']) == 1
    error = json.loads(capsys.readouterr().out)
    assert error['error']['code'] == 'E_STRICT'


def test_no_contract_is_invented_for_foreign_implementation():
    src = 'use py:math as m\nfn f(x: Float) -> Float = m.sqrt(x)'
    assert compile_b(src).ir.statements[1].verification is None


def test_contract_rejects_guaranteed_false_literal():
    rejects('fn f(x: Int) -> Int ensures false = x', 'E_POSTCONDITION')


def test_negative_return_guard_and_contract_effect_in_generated_python():
    program = compile_b('fn p(x: Int) -> Int pure requires x > 0 ensures result > 0 = x', strict=True)
    assert '_b_contract_error' in program.source
    assert '_b_guard' in program.source
