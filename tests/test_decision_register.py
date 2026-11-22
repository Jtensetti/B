"""Both decision registers use the same typed program and execution path."""
import statistics

import pytest

from b_lang.compiler import compile_b
from b_lang.runtime import BContractError
from b_lang.types import BError


def equivalent(ordinary, table, strict=True):
    left = compile_b(ordinary, strict=strict)
    right = compile_b(table, strict=strict)
    assert right.ir == left.ir
    assert right.optimized_ir == left.optimized_ir
    assert right.analysis == left.analysis
    assert right.diagnostics == left.diagnostics
    assert right.assumptions == left.assumptions
    assert right.source == left.source
    return right


def load(compiled):
    names = {}
    exec(compiled.code, names, names)
    return names


def test_overlap_selects_first_match_and_preserves_contracts():
    declaration = "fn band(x: Int) -> Int pure requires x >= -5 ensures result >= 0 = "
    ordinary = "if x < 0 then 4 else if x <= 5 then 2 else if x <= 2 then 1 else 3"
    table = """cases x {
        < 0 => 4;
        <= 5 => 2

        <= 2 => 1
        else => 3;
    }"""
    compiled = equivalent(declaration + ordinary, declaration + table)
    assert compiled.ir.statements[0].verification == "proved-interval"
    band = load(compiled)["band"]
    assert [band(x) for x in (-5, -1, 0, 2, 5, 6, 10**100)] == [4, 4, 2, 2, 2, 3, 3]
    with pytest.raises(BContractError, match="Precondition"):
        band(-6)


@pytest.mark.parametrize("typ, rows, probes", [
    ("Float", [("<", "-1.25"), (">=", "2.5")], [(-2, 1), (-1.25, 0), (2.5, 2)]),
    ("Int", [("!=", "-3"), ("==", "-3")], [(-3, 2), (0, 1)]),
    ("Text", [("==", '"green"'), (">", '"red"')], [("green", 1), ("violet", 2), ("red", 0)]),
    ("Bool", [("==", "true")], [(True, 1), (False, 0)]),
    ("Option[Int]", [("==", "none")], [(None, 1), (0, 0)]),
])
def test_scalar_thresholds_reuse_ordinary_comparisons(typ, rows, probes):
    decl = f"fn band(x: {typ}) -> Int = "
    table = "cases x { " + "".join(f"{op} {bound} => {i}; " for i, (op, bound) in enumerate(rows, 1)) + "else => 0 }"
    ordinary = "".join(f"if x {op} {bound} then {i} else " for i, (op, bound) in enumerate(rows, 1)) + "0"
    band = load(equivalent(decl + ordinary, decl + table))["band"]
    for x, expected in probes:
        assert band(x) == expected


def test_tables_can_nest_inside_ordinary_expressions():
    decl = "fn f(x: Int, y: Int) -> Int = "
    table = "1 + cases x { == 0 => cases y { == 0 => 7; else => 3 }; else => 5 } * 2"
    ordinary = "1 + (if x == 0 then (if y == 0 then 7 else 3) else 5) * 2"
    f = load(equivalent(decl + ordinary, decl + table))["f"]
    assert [f(0, 0), f(0, 1), f(1, 0)] == [15, 7, 11]


def test_selected_branch_runs_once_and_other_branch_stays_lazy(monkeypatch):
    decl = "use py:statistics as stats\nfn f(k: Int, x: Int) -> Float = "
    table = "cases k { == 0 => stats.mean([2.0]); else => 8 / x }"
    ordinary = "if k == 0 then stats.mean([2.0]) else 8 / x"
    compiled = equivalent(decl + ordinary, decl + table)
    assert compiled.ir.statements[-1].effects == ("foreign",)
    calls = []

    def observed_mean(values):
        calls.append(values)
        return 2.0

    monkeypatch.setattr(statistics, "mean", observed_mean)
    f = load(compiled)["f"]
    assert f(0, 0) == 2.0
    assert f(1, 4) == 2.0
    with pytest.raises(ZeroDivisionError):
        f(1, 0)
    assert calls == [[2.0]]


@pytest.mark.parametrize("decl, ordinary, table, code", [
    ("fn f(x: Int) -> Int = ", 'if x < "t" then 1 else 0', '< "t" => 1; else => 0', "E_TYPE"),
    ("fn f(x: Int) -> Int = ", 'if x < 1 then "t" else 0', '< 1 => "t"; else => 0', "E_TYPE"),
    ("use py:statistics as s\nfn f(x: Int) -> Float pure = ",
     "if x < 0 then s.mean([1]) else 0.0", "< 0 => s.mean([1]); else => 0.0", "E_EFFECT"),
    ("fn pos(n: Int) -> Int requires n > 0 = n\nfn f(x: Int, n: Int) -> Int = ",
     "if x < 0 then pos(n) else 1", "< 0 => pos(n); else => 1", "E_STRICT"),
])
def test_invalid_programs_receive_same_error(decl, ordinary, table, code):
    failures = []
    for body in (ordinary, "cases x { " + table + " }"):
        with pytest.raises(BError) as caught:
            compile_b(decl + body, strict=True)
        assert caught.value.code == code
        failures.append(str(caught.value))
    assert failures[0] == failures[1]


def test_cases_stays_usable_as_identifier_including_before_then():
    compiled = compile_b("""fn cases2(cases: Int) -> Int = cases cases { == 1 => 2; else => 3 }
fn cases(cases: Bool) -> Dict[Text, Int] = if cases then {"yes": 1} else {"no": 0}
let chosen = cases(true)
let score = cases2(1)""", strict=True)
    names = load(compiled)
    assert names["chosen"] == {"yes": 1}
    assert names["score"] == 2


@pytest.mark.parametrize("word", ["true", "false", "none", "if", "not"])
def test_pivots_must_be_readable_as_ordinary_variables(word):
    with pytest.raises(BError, match="must be usable as an ordinary variable") as caught:
        compile_b(f"fn f({word}: Int) -> Int = cases {word} {{ == 9 => 1; else => 0 }}")
    assert caught.value.code == "E_SYNTAX"


@pytest.mark.parametrize("body", [
    "cases x { < 0 => 9 }",
    "cases x { < 0 => 9; }",
    "cases x { < 0 => 9\n}",
])
def test_missing_fallback_explains_repair(body):
    with pytest.raises(BError, match="final 'else => result' row") as caught:
        compile_b("fn f(x: Int) -> Int = " + body)
    assert caught.value.code == "E_SYNTAX"


@pytest.mark.parametrize("body", [
    "cases x { }", "cases x { else => 0 }",
    "cases x { < 0 => 9; else => 0; < 2 => 3 }",
    "cases x { < 0 => 9; else => 0; else => 1 }",
    "cases x { < 0 => 9 else => 0 }",
    "cases pick(x) { < 0 => 9; else => 0 }",
    "cases (x + 1) { < 0 => 9; else => 0 }",
    "cases x { < x => 9; else => 0 }",
    "cases x { < 2 + 1 => 9; else => 0 }",
    "2; print 3",
])
def test_unsupported_forms_fail_before_execution(body):
    with pytest.raises(BError) as caught:
        compile_b("fn f(x: Int) -> Int = " + body)
    assert caught.value.code == "E_SYNTAX"


@pytest.mark.parametrize("register", ["ordinary", "cases"])
def test_excessive_nesting_reports_compiler_capacity(register):
    if register == "cases":
        rows = "".join(f"== {i} => {i}; " for i in range(1500))
        body = "cases x { " + rows + "else => 0 }"
    else:
        body = "".join(f"if x == {i} then {i} else " for i in range(1500)) + "0"
    with pytest.raises(BError) as caught:
        compile_b("fn f(x: Int) -> Int = " + body)
    assert caught.value.code == "E_DEPTH"
