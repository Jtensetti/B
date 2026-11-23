import pytest

from b_lang.compiler import compile_b
from b_lang.model import parse
from b_lang.runtime import BBoundaryError, BContractError
from b_lang.types import BError


def execute(source, *, strict=True):
    names = {}
    exec(compile_b(source, strict=strict).code, names)
    return names


def test_an_added_case_runs_for_prior_callers_and_preserves_other_inputs():
    base = ('fn free(child: Bool, day: Text) -> Bool pure = child and day == "sat"\n'
            'fn fare(child: Bool, day: Text) -> Int pure = if free(child, day) then 0 else 25\n'
            'let sunday = fare(true, "sun")\n')
    before = execute(base)
    after = execute(base + 'also free(true, "sun")')
    assert (before["sunday"], after["sunday"]) == (25, 0)
    for child in (False, True):
        for day in ("fri", "sat", "sun", "other"):
            expected = 0 if child and day in ("sat", "sun") else 25
            assert after["fare"](child, day) == expected
    with pytest.raises(BBoundaryError):
        after["free"](1, "sun")


def test_exact_literals_and_snapshot_order():
    base = 'fn also(keeping: Int, f: Float, s: Text) -> Bool pure = false\n'
    one = 'also also(-2, -0.5, "ändra#")\n'
    two = 'also also(4, 0.125, "")\n'
    assert parse(one)[0].parts == ("also", (-2, -0.5, "ändra#"), (), None)
    assert compile_b(base + one + two).ir == compile_b(two + base + one).ir
    rule = execute(base + one + two)["also"]
    assert rule(-2, -0.5, "ändra#") and rule(4, 0.125, "")
    assert not rule(-2, -0.5, "") and not rule(4, -0.5, "")
    assert not rule(-2, -0.499999, "ändra#")


def test_zero_argument_predicate_and_keeping_ast():
    assert execute('also gate()\nfn gate() -> Bool pure = false')['gate']() is True
    assert parse('also gate() keeping quota, owner')[0].parts == ("gate", (), ("quota", "owner"), None)


@pytest.mark.parametrize(("base", "change", "code"), [
    ("let gate = true", "gate(true)", "E_ALSO"),
    ("use py:math as gate", "gate(true)", "E_ALSO"),
    ("fn gate(x: Bool) -> Bool = x", "gate(true)", "E_ALSO"),
    ("fn gate(x: Bool) -> Int pure = 1", "gate(true)", "E_ALSO"),
    ("fn gate(x: Bool) -> Bool pure = false", "gate()", "E_ARITY"),
    ("fn gate(x: Int) -> Bool pure = false", "gate(true)", "E_TYPE"),
    ("fn gate(x: Bool) -> Bool pure = false", "gate(1)", "E_TYPE"),
    ("fn gate(x: Float) -> Bool pure = false", "gate(1)", "E_TYPE"),
    ("fn gate(x: Float) -> Bool pure = false", "gate(" + "9" * 319 + ".0)", "E_TYPE"),
    ("fn gate(x: Any) -> Bool pure = false", "gate(1)", "E_TYPE"),
    ("fn gate(x: Option[Int]) -> Bool pure = false", "gate(none)", "E_TYPE"),
    ("fn gate(x: Text) -> Bool pure = false", 'gate("a" + "b")', "E_SYNTAX"),
    ("fn gate(x: Text) -> Bool pure = false", r'gate("\q")', "E_SYNTAX"),
    ("let label = 1\nfn gate(x: Int) -> Bool pure = false", "gate(label)", "E_SYNTAX"),
    ("fn gate(x: Int) -> Bool pure = false\nalso gate(1)", "gate(1)", "E_ALSO"),
    ("fn gate(x: Int) -> Bool pure requires x >= 0 = false", "gate(-1)", "E_ALSO"),
    ("fn gate(x: Int) -> Bool pure ensures not result = false", "gate(1)", "E_ALSO"),
])
def test_reject_invalid_declarations_during_normal_compilation(base, change, code):
    with pytest.raises(BError) as exc:
        compile_b(base + "\nalso " + change)
    assert exc.value.code == code


def test_original_typed_body_and_effects_are_checked_even_when_always_overridden():
    with pytest.raises(BError) as exc:
        compile_b('use py:math as m\nfn gate() -> Bool pure = m.sqrt(1) > 0\nalso gate()')
    assert exc.value.code == "E_EFFECT"
    with pytest.raises(BError) as exc:
        compile_b('fn gate() -> Bool pure = "bad"\nalso gate()')
    assert exc.value.code == "E_TYPE"


def test_valid_contract_remains_active_at_the_boundary():
    source = ('fn gate(result: Int) -> Bool pure requires result > 0 = false\n'
              'also gate(1)\n'
              'fn holiday(x: Int) -> Bool pure ensures not result or x == 0 = false\n'
              'also holiday(0)')
    names = execute(source, strict=False)
    assert names["gate"](1) and not names["gate"](2)
    with pytest.raises(BContractError):
        names["gate"](0)
    assert names["holiday"](0) and not names["holiday"](1)


def test_pending_edit_changes_source_fallback_beneath_persistent_facts():
    source = ('fn gate(x: Int) -> Bool pure = false\n'
              'also gate(1)\n'
              'next gate when x >= 1 => x == 2')
    revised = compile_b(source).handoff.source
    assert [execute(source)["gate"](x) for x in (0, 1, 2)] == [False, True, False]
    assert [execute(revised)["gate"](x) for x in (0, 1, 2)] == [False, True, True]


def test_hundreds_of_literal_facts_compile_without_linear_nesting():
    base = 'fn listed(x: Int) -> Bool pure = false\n'
    rule = execute(base + "\n".join(f"also listed({i})" for i in range(300)))["listed"]
    assert rule(0) and rule(137) and rule(299) and not rule(300)


@pytest.mark.parametrize("count", [1, 16, 32, 256])
def test_large_sets_use_a_constant_index_in_both_execution_paths(count, monkeypatch):
    from b_lang import lowering

    base = 'fn valid(class: Int, tag: Text) -> Bool pure = class < 0\n'
    source = base + "\n".join(f'also valid({n}, "t{n % 3}")' for n in range(count))
    built = compile_b(source)
    monkeypatch.setattr(lowering, "_INDEX_MIN_ROWS", count + 1)
    unindexed = compile_b(source)
    assert built.optimized_ir == unindexed.optimized_ir
    for program in (built.code, built.source):
        names = {}
        exec(program, names)
        rule = names["valid"]
        indices = [value for value in rule.__code__.co_consts if isinstance(value, frozenset)]
        assert indices == ([frozenset((n, f"t{n % 3}") for n in range(count))] if count >= 32 else [])
        for n in range(count):
            assert rule(n, f"t{n % 3}") and not rule(n, "")
        assert rule(-2, "fallback") and not rule(count + 10, "unknown")
        with pytest.raises(BBoundaryError):
            rule(False, "t0")


def test_single_parameter_index_and_mixed_condition_fallback():
    source = 'fn listed(x: Int) -> Bool pure = false\n' + "\n".join(f"also listed({n})" for n in range(64))
    rule = execute(source)["listed"]
    assert frozenset(range(64)) in rule.__code__.co_consts
    assert rule(63) and not rule(-1)
    terms = [f"x == {n}" for n in range(64)] + ["x < 0"]
    ordinary = 'fn listed(x: Int) -> Bool pure = if ' + ' or '.join(terms) + ' then true else false'
    rule = execute(ordinary)["listed"]
    assert not any(isinstance(v, frozenset) for v in rule.__code__.co_consts)
    assert rule(63) and rule(-1) and not rule(75)
