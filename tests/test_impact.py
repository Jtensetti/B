"""Revision comparisons distinguish identifiable moves and changes of proof."""
from b_lang.compiler import compile_b
from b_lang.impact import compare


PROVIDERS = """
fn p(n: Int) -> Int requires n >= 0 ensures result > 0 = n + 1
fn q(n: Int) -> Int requires n >= 0 ensures result >= 0 = n
"""


def changes(before, after):
    return compare(compile_b(before).analysis, compile_b(after).analysis)["changes"]


def test_commuting_two_pure_terms_moves_checks_without_losing_a_proof():
    prefix = PROVIDERS + "fn use(n: Int) -> Float requires n >= 0 = "
    rows = changes(prefix + "1 / p(n) + 1 / q(n)", prefix + "1 / q(n) + 1 / p(n)")
    assert len(rows) == 4
    assert all(row["change"] == "moved" and row["matched_by"] == "expression" for row in rows)
    assert {row["after"]["kind"] for row in rows} == {"requires", "nonzero"}
    assert all(row["before"]["site"] != row["after"]["site"] for row in rows)


def test_identifiable_checks_survive_an_outer_no_op_even_with_a_contract_edit():
    prefix = PROVIDERS + "fn use(n: Int) -> Float requires n >= 0 = "
    expr = "1 / p(n) + 1 / q(n)"
    after = prefix.replace("result > 0", "result >= 0") + f"0.0 + ({expr})"
    rows = [row for row in changes(prefix + expr, after) if row["after"]["caller"] == "use"]
    assert len(rows) == 4 and all(row["moved"] for row in rows)
    lost = [row for row in rows if row["change"] == "lost-proof"]
    assert [row["after"]["requirement"] for row in lost] == ["p(n) != 0"]
    assert sum(row["change"] == "moved" for row in rows) == 3


def test_argument_expressions_disambiguate_calls_to_the_same_function():
    prefix = """
fn take(x: Int) -> Int requires x > 0 = x
fn use(n: Int) -> Int requires n >= 0 = """
    rows = changes(prefix + "take(n) + take(n + 1)", prefix + "take(n + 1) + take(n)")
    assert len(rows) == 2
    assert all(row["change"] == "moved" for row in rows)
    assert all(row["before"]["expression"] == row["after"]["expression"] for row in rows)


def test_ambiguous_duplicate_moves_remain_unmatched():
    prefix = "fn use(n: Int) -> Float = "
    expr = "(1 / n + 1 / n)"
    # Two wrappings keep all old and new paths disjoint.
    rows = changes(prefix + expr, prefix + f"0.0 + (0.0 + {expr})")
    assert sorted(row["change"] for row in rows) == ["added", "added", "removed", "removed"]
    assert all(row["matched_by"] is None for row in rows)
