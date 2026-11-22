import pytest

from b_lang.compiler import compile_b
from b_lang.handoff import inspect_handoff
from b_lang.shorthand import expand_shorthand, prepare_shorthand
from b_lang.types import BError


ROUTE = 'fn route(days: Int) -> Text pure = "standard"'
SIGNAL = 'fn signal(channel: Int, phase: Int) -> Int pure = channel + phase'


def run_function(source, function):
    namespace = {}
    exec(compile_b(source, strict=True).code, namespace)
    return namespace[function]


def test_two_registers_produce_identical_checked_revisions():
    source = ROUTE + "\n" + SIGNAL
    rows = 'route 5 "express"\nsignal phase -2 12'
    ordinary = source + '\nnext route when days == 5 => "express"\nnext signal when phase == -2 => 12\n'
    expanded, prepared = prepare_shorthand(source, rows, strict=True)
    assert expanded == ordinary
    assert prepared.source == inspect_handoff(ordinary, strict=True)[1]
    assert compile_b(prepared.source).ir == compile_b(inspect_handoff(ordinary)[1]).ir
    assert run_function(expanded, "route")(5) == "standard"
    route, signal = [run_function(prepared.source, name) for name in ("route", "signal")]
    assert (route(4), route(5), signal(1, 2), signal(1, -2)) == ("standard", "express", 3, 12)


def test_literals_reuse_b_escaping_and_preserve_spelling():
    source = 'fn next(when: Text) -> Text pure = when'
    row = r'next "röd #5 \"nu\"" "\u00e5 och \\"'
    expanded, after = prepare_shorthand(source, row)
    assert expanded.endswith(r'next next when when == "röd #5 \"nu\"" => "\u00e5 och \\"' + '\n')
    f = run_function(after.source, "next")
    assert f('röd #5 "nu"') == 'å och \\'
    assert f("annat") == "annat"


@pytest.mark.parametrize(("signature", "row", "input_value", "expected"), [
    ("x: Bool) -> Bool pure = x", "f true false", True, False),
    ("x: Float) -> Float pure = 0.0", "f -2.5 -0.5", -2.5, -0.5),
    ("x: Option[Int]) -> Option[Int] pure = x", "f none 3", None, 3),
    ("x: Option[Int]) -> Option[Int] pure = x", "f x 3 none", 3, None),
])
def test_all_scalar_kinds(signature, row, input_value, expected):
    _, after = prepare_shorthand("fn f(" + signature, row, strict=True)
    assert run_function(after.source, "f")(input_value) == expected


@pytest.mark.parametrize(("source", "rows", "code"), [
    (SIGNAL, "signal 1 7", "E_SHORTHAND"),
    (SIGNAL, "signal stage 1 7", "E_SHORTHAND"),
    ("fn f(i: Int, b: Bool) -> Int = i", "f 1 7", "E_SHORTHAND"),
    ("fn f() -> Int = 5", "f 1 7", "E_SHORTHAND"),
    (SIGNAL, "unknown 1 7", "E_SHORTHAND"),
    ("fn f(true: Bool) -> Int = 0", "f true 7", "E_SHORTHAND"),
    ("fn f(if: Int) -> Int = 0", "f 5 7", "E_SHORTHAND"),
    (SIGNAL, 'signal phase "red" 5', "E_TYPE"),
    (ROUTE, "route 5 5", "E_TYPE"),
    ("fn f(x: Any) -> Int = 0", "f 5 7", "E_HANDOFF"),
    (ROUTE, 'route 5 "red"\nroute 5 "red"', "E_HANDOFF"),
    ("use py:math as m", "m 1 2", "E_SHORTHAND"),
    ("adopt py:b_examples.pure_kernels.square as square", "square 1 3", "E_SHORTHAND"),
])
def test_bad_targets_arity_and_types(source, rows, code):
    with pytest.raises(BError) as exc:
        expand_shorthand(source, rows)
    assert exc.value.code == code


@pytest.mark.parametrize("row", ['f 1 +2', 'f 2 1e2', 'f (1) 2', 'f 00 2', 'f 1 2 + 3', 'f 1 [2]',
    'f true 2 # pending', r'f "bad\q" 2', 'f 3 "a"+"b"', 'f "a"+"b" 2',
    'f 1 "never closed', 'f 1 2;', 'f 1\u20282', 'f\v1 2'])
def test_shorthand_accepts_only_separate_complete_literal_fields(row):
    with pytest.raises(BError, match="Row 2") as exc:
        expand_shorthand("fn f(x: Int) -> Int = x", '\n' + row)
    assert exc.value.code == "E_SHORTHAND"


@pytest.mark.parametrize("line_break", ["\r\n", "\n", "\r"])
def test_empty_rows_preserve_source_and_new_lines_follow_source_style(line_break):
    original = ROUTE + line_break + 'print "#choose"'
    assert expand_shorthand(original, "\t\n \r\n") == original
    updated = expand_shorthand(original, '\r\nroute\t  5\t "express"')
    assert updated == original + line_break + 'next route when days == 5 => "express"' + line_break


def test_blank_can_never_consume_prior_edits_nonempty_rejects_them():
    original = ROUTE + '\n' + SIGNAL + '\nnext route when days == 1 => "morning"'
    assert prepare_shorthand(original, " ") == (original, None)
    with pytest.raises(BError) as exc:
        prepare_shorthand(original, 'signal phase 3 8')
    assert exc.value.code == "E_SHORTHAND_PENDING"
    with pytest.raises(BError) as exc:
        prepare_shorthand('fn f(p: Bool) -> Int = "invalid"', "")
    assert exc.value.code == "E_TYPE"


def test_retry_skips_exact_existing_leading_branch_and_checks_remaining_edits():
    original = ROUTE + "\n" + SIGNAL
    first = prepare_shorthand(original, 'route 5 "express"')[1].source
    assert prepare_shorthand(first, 'route days 5 "express"') == (first, None)
    expanded, updated = prepare_shorthand(first, 'route 5 "express"\nsignal channel 2 8')
    assert expanded == first + 'next signal when channel == 2 => 8\n'
    assert run_function(updated.source, "signal")(2, -9) == 8
    with pytest.raises(BError) as exc:
        prepare_shorthand(first, 'route 5 "express"\nroute 5 "express"')
    assert exc.value.code == "E_HANDOFF"


def test_retry_requires_exact_literal_kind_including_float_zero_sign():
    source = 'fn f(x: Int) -> Float = if x == 1 then 0.0 else 4.0'
    assert prepare_shorthand(source, 'f 1 0.0') == (source, None)
    for row in ('f 1 -0.0', 'f 1 0', 'f 1.0 0.0'):
        _, handoff = prepare_shorthand(source, row)
        assert handoff is not None


def test_expanding_has_no_runtime_output(capsys):
    checked = expand_shorthand(ROUTE + '\nprint "run only"', 'route 5 "ok"')
    assert capsys.readouterr().out == ""
    assert 'next route' in checked


def test_expansion_preserves_pending_contract_obligations_and_strict_mode():
    source = "fn f(x: Int, y: Int) -> Int ensures result >= x = x"
    expanded = expand_shorthand(source, "f y 1 0")
    assert any(d.code == "W_RUNTIME_POSTCONDITION" for d in compile_b(expanded).diagnostics)
    with pytest.raises(BError) as exc:
        expand_shorthand(source, "f y 1 0", strict=True)
    assert exc.value.code == "E_STRICT"
