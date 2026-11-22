import pytest

from b_lang.compiler import Compiler, Symbol
from b_lang.history import history_plan, order_comparison
from b_lang.model import parse
from b_lang.types import ANY, BOOL, FLOAT, INT, TEXT, BError, Type, option


def plan(expression, mode="earlier", element_type=INT):
    statement, = parse("print " + expression)
    bindings = {"old": Symbol(element_type), "now": Symbol(element_type), "limit": Symbol(INT)}
    predicate = Compiler().infer(statement.parts[0], bindings).node
    return history_plan(predicate, "old", "now", mode)


@pytest.mark.parametrize(("op", "reverse", "selected"), [
    ("<", ">", "prefix-min"), ("<=", ">=", "prefix-min"),
    (">", "<", "prefix-max"), (">=", "<=", "prefix-max"),
])
def test_order_direction_and_captured_parameters(op, reverse, selected):
    historical = '(old["end"] ?? -1000) + limit'
    present = '(now["start"] ?? 0) - 2'
    record = Type("Dict", (TEXT, INT))
    assert plan(f"{historical} {op} {present}", element_type=record) == {
        "plan": selected, "past_side": 0, "comparison": op,
    }
    assert plan(f"{present} {reverse} {historical}", element_type=record) == {
        "plan": selected, "past_side": 1, "comparison": op,
    }


@pytest.mark.parametrize(("expression", "mode", "expected"), [
    ("now > limit and old > limit", "adjacent", {"plan": "previous-test", "past_side": 1}),
    ("old < limit and now > limit", "adjacent", {"plan": "previous-test", "past_side": 0}),
    ("old < now and now > limit", "adjacent", {"plan": "previous-item"}),
    ("now > limit and true", "adjacent", {"plan": "previous-item"}),
    ("old == now", "earlier", {"plan": "prefix-search"}),
    ("old * now > now", "earlier", {"plan": "prefix-search"}),
    ("old + limit < limit", "earlier", {"plan": "prefix-search"}),
])
def test_each_specialization_needs_a_separable_relation(expression, mode, expected):
    assert plan(expression, mode) == expected


def test_optional_scalar_and_presence_have_total_equality():
    assert plan("old == now", element_type=option(TEXT)) == {"plan": "prefix-search"}
    assert plan('old["key"] != none and now["key"] == none', "adjacent",
                Type("Dict", (TEXT, Type("Dict", (TEXT, BOOL))))) == {
        "plan": "previous-test", "past_side": 0,
    }


@pytest.mark.parametrize(("expression", "element_type"), [
    ("old % now == 0", INT),
    ("if true then true else old / now == 1.0", INT),
    ("old == now", ANY),
    ("old == now", Type("Dict", (TEXT, INT))),
    ("old == now", Type("List", (INT,))),
    ("old > now", FLOAT),
    ('old["x"] != none', Type("Dict", (TEXT, ANY))),
    ('old + "day" == now', TEXT),
])
def test_opaque_partial_and_unsupported_values_are_rejected(expression, element_type):
    with pytest.raises(BError) as exc:
        plan(expression, element_type=element_type)
    assert exc.value.code == "E_HISTORY_PREDICATE"


@pytest.mark.parametrize(("op", "normalized", "reversed_normalized"), [
    ("<", ">=", "<="), ("<=", ">", "<"), (">", "<=", ">="), (">=", "<", ">"),
])
def test_negated_integral_order_retains_its_linear_plan(op, normalized, reversed_normalized):
    for side, (left, right, effective) in enumerate((
        ("old", "now", normalized), ("now", "old", reversed_normalized),
    )):
        expression = f"not ({left} {op} {right})"
        assert plan(expression) == {
            "plan": "prefix-min" if effective in ("<", "<=") else "prefix-max",
            "past_side": side, "comparison": effective,
        }
        statement, = parse("print " + expression)
        checked = Compiler().infer(statement.parts[0], {"old": Symbol(INT), "now": Symbol(INT)}).node
        comparison = order_comparison(checked)
        assert comparison.data == normalized
        assert [operand.data for operand in comparison.operands] == [left, right]


def test_complement_optimization_is_limited_to_ordered_ints():
    assert plan("not (old < now)", element_type=TEXT) == {"plan": "prefix-search"}
    assert plan("not (old == now)") == {"plan": "prefix-search"}
