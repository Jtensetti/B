import pytest

from b_lang.compiler import compile_b
from b_lang.handoff import inspect_handoff
from b_lang.register_view import function_view
from b_lang.types import BError


def load(source, *, strict=True):
    names = {}
    exec(compile_b(source, strict=strict).code, names)
    return names


def test_pending_and_materialized_use_the_same_declared_scope_and_keep_distinct_behavior():
    original = ('fn discount(n: Int) -> Int pure = 7\n'
                'fn fee(n: Int) -> Int pure requires n >= 0 ensures result >= 0 = 10\n'
                'fn total(n: Int) -> Int pure requires n >= 0 = fee(n) + 1\n')
    instruction = 'next fee when n == 0 => discount(n)'
    source = original + instruction
    current = compile_b(source)
    assert current.ir == compile_b(original).ir
    assert current.source == compile_b(original).source
    instructions, after = inspect_handoff(source)
    assert instructions == [instruction]
    assert after == original.replace('= 10', '= if n == 0 then discount(n) else 10')
    assert inspect_handoff(after) == ([], after)
    assert current.pending_analysis == compile_b(after).analysis
    for program, expected_zero in ((source, 11), (after, 8)):
        names = load(program, strict=False)
        assert [names["total"](n) for n in (0, 1, 9)] == [expected_zero, 11, 11]
        with pytest.raises(AssertionError):
            names["total"](-1)


def test_multiple_functions_apply_together_in_original_lexical_order():
    source = ('  next total when n == 0 => price(1)\n\n'
              'fn price(x: Int) -> Int pure = 2\n'
              'fn total(n: Int) -> Int pure = price(n) + 10\n'
              'next price when x == 1 => 8\n')
    directives, after = inspect_handoff(source)
    assert directives == ['next total when n == 0 => price(1)', 'next price when x == 1 => 8']
    assert load(source)['total'](0) == 12
    assert [load(after)['total'](n) for n in (0, 1, 2)] == [8, 18, 12]


@pytest.mark.parametrize(('target', 'directive', 'error'), [
    ('fn f(x: Int) -> Int pure = x', 'next missing when true => 1', 'E_HANDOFF'),
    ('use py:statistics as f', 'next f when true => 1', 'E_HANDOFF'),
    ('fn f(x: Int) -> Int pure = x', 'next f when true => 1\nnext f when false => 4', 'E_HANDOFF'),
    ('fn f(x: Int) -> Int pure = x', 'next f when x => 1', 'E_TYPE'),
    ('fn f(x: Int) -> Int pure = x', 'next f when x == 0 => "untyped"', 'E_TYPE'),
    ('fn f(x: Int) -> Int pure = x', 'next f when y == 0 => 4', 'E_NAME'),
    ('fn f(x: Int) -> Int pure = x\nlet later = 17', 'next f when x == 0 => later', 'E_NAME'),
    ('fn f(x: Int) -> Int pure = x\nlet later = 17', 'next f when x == later => 0', 'E_NAME'),
    ('let earlier = 17\nfn f(x: Int) -> Int = x', 'next f when x == earlier => 0', 'E_HANDOFF'),
    ('fn test(x: Int) -> Bool pure = true\nfn f(x: Int) -> Int = x', 'next f when test(x) => 0', 'E_HANDOFF'),
    ('fn f(x: List[Any]) -> Int = 0', 'next f when x == x => 1', 'E_HANDOFF'),
    ('use py:math as m\nfn f(x: Int) -> Float pure = 0.0', 'next f when x > 0 => m.sqrt(x)', 'E_EFFECT'),
    ('fn f(x: Int) -> Int pure ensures result >= 0 = 1', 'next f when true => -1', 'E_HANDOFF'),
])
def test_invalid_instructions_fail_on_ordinary_compilation_and_handoff_inspection(target, directive, error):
    for check in (compile_b, inspect_handoff):
        with pytest.raises(BError) as raised:
            check(target + '\n' + directive)
        assert raised.value.code == error


def test_new_unknown_contract_is_visible_and_strict_rejects():
    source = ('fn helper(n: Int) -> Int pure = n * n\n'
              'fn f(x: Int) -> Int ensures result >= 0 = 7\nnext f when x > 0 => helper(x)')
    result = compile_b(source)
    assert any(d.code == 'W_RUNTIME_POSTCONDITION' and 'Pending handoff' in d.message for d in result.diagnostics)
    assert result.pending_analysis is not None and result.pending_analysis != result.analysis
    with pytest.raises(BError) as exc:
        inspect_handoff(source, strict=True)
    assert exc.value.code == 'E_STRICT'


def test_a_syntactically_valid_future_cannot_hide_a_current_error():
    source = 'fn f(x: Int) -> Int = "bad"\nnext f when true => 42'
    with pytest.raises(BError) as error:
        inspect_handoff(source)
    assert error.value.code == "E_TYPE"


def test_guarded_rewrite_must_not_change_the_old_branch_by_joining_types():
    source = 'fn f(x: Int) -> Any = 9007199254740993\nnext f when x == 0 => 0.0'
    with pytest.raises(BError, match='fallback') as exc:
        inspect_handoff(source)
    assert exc.value.code == "E_HANDOFF"
    # A Float return already performs this conversion in both versions.
    float_source = source.replace('-> Any', '-> Float')
    _, rendered = inspect_handoff(float_source)
    assert load(float_source)['f'](3) == load(rendered)['f'](3) == 9007199254740992.0


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r'])
def test_named_next_and_when_multiline_cases_and_literal_hashes(ending):
    baseline = 'fn next(when: Int) -> Text pure = cases when { == 1 => "é#"; else => "old" }'
    instruction = ending.join(['next next when when < 0 => cases when {', '  == -1 => "#"', '  else => "ä"', '}'])
    source = f'{baseline}{ending}  {instruction}{ending}print next(0){ending}'
    instructions, revised = inspect_handoff(source)
    assert instructions == [instruction]
    assert revised.count(ending) == source.count(ending) - 1
    assert inspect_handoff(revised) == ([], revised)
    f = load(revised)['next']
    assert [f(x) for x in [-2, -1, 0, 1]] == ['ä', '#', 'old', 'é#']


def test_keywords_remain_ordinary_names_and_views_preserve_pending_behavior():
    source = ('let when = "next fee when true => 9"\n'
              'fn next(x: Int) -> Int = if x == 1 then 2 else 3\n'
              'next next when x == 9 => 4\n')
    rewritten = source.replace('fn next(x: Int) -> Int = if x == 1 then 2 else 3',
                               function_view(source, 'next', 'cases'))
    assert compile_b(source).ir == compile_b(rewritten).ir
    _, baseline = inspect_handoff(source)
    _, viewed = inspect_handoff(rewritten)
    assert compile_b(baseline).ir == compile_b(viewed).ir


def test_no_directives_preserves_exact_source():
    for source in ('', '\n\n', 'print "# next fake when true => 8"'):
        assert inspect_handoff(source) == ([], source)
