from functools import cache
from itertools import combinations

import pytest

from b_lang.clarification import compare
from b_lang.compiler import compile_b
from b_lang.question_planner import MAX_PARTITIONS, minimax_question
from b_lang.types import BError


def ask(candidates, outputs, answers=(), *, strategy="minimax"):
    ir = compile_b("fn f(x: Int) -> Int = x").ir
    return compare(ir, "f", candidates, {"x": [0]}, outputs, answers, strategy=strategy)


def test_all_small_binary_catalogs_match_an_independent_decision_tree():
    cells = [((0,), q) for q in range(3)]

    @cache
    def depth(rows):
        if len(rows) == 1:
            return 0
        depths = []
        for q in range(3):
            yes = tuple(r for r in rows if r & (1 << q))
            no = tuple(r for r in rows if not r & (1 << q))
            if yes and no:
                depths.append(1 + max(depth(yes), depth(no)))
        return min(depths)

    for size in range(2, 9):
        for catalog in combinations(range(8), size):
            q, plan = minimax_question(cells, catalog, set(), "question")
            yes = tuple(r for r in catalog if r & (1 << q))
            no = tuple(r for r in catalog if not r & (1 << q))
            assert 1 + max(depth(yes), depth(no)) == depth(catalog)
            assert plan["worst_case_remaining_questions"] == depth(catalog)


def test_abstention_distinguishes_only_observable_classes():
    candidates = {"A": "result == 0", "B": "false", "C": "result == 1"}
    skipped = [({"x": 0}, 0, None)]
    report = ask(candidates, [0, 1], skipped)
    assert report["question"]["result"] == 1
    plan = report["planning"]
    assert plan["remaining_full_classes"] == 3 and plan["observable_classes"] == 2
    assert plan["full_class_identification_possible"] is False
    assert plan["worst_case_remaining_questions"] is None
    assert plan["observable_worst_case_remaining_questions"] == 1

    terminal = ask(candidates, [0, 1], skipped + [({"x": 0}, 1, False)])
    assert terminal["status"] == "undetermined" and terminal["survivors"] == ["A", "B"]
    assert terminal["planning"]["observable_worst_case_remaining_questions"] == 0
    assert terminal["planning"]["worst_case_remaining_questions"] is None


def test_duplicate_labels_and_complementary_questions_are_counted_once():
    candidates = {**{str(i): "result == 0" for i in range(13)}, "other": "result != 0"}
    report = ask(candidates, [-2, -1, 0, 1, 2])
    plan = report["planning"]
    assert (plan["used"], plan["observable_classes"], plan["distinct_partitions"]) == ("minimax", 2, 1)
    assert report["question"]["result"] == 0
    assert len(report["question"]["allowed_by"]) == 13
    assert plan["worst_case_remaining_questions"] == 1


def test_class_limit_falls_back_to_the_actual_balanced_question():
    candidates = {str(i): f"result == {i}" for i in range(11)}
    fallback = ask(candidates, range(11))
    default = ask(candidates, range(11), strategy="balanced")
    assert fallback["question"] == default["question"]
    assert fallback["planning"]["used"] == "balanced"
    assert fallback["planning"]["reason"] == "observable-class-limit"
    assert fallback["planning"]["worst_case_remaining_questions"] is None


def test_partition_limit_stops_before_exact_search():
    # Different nonempty bipartitions among seven observable classes.
    patterns = range(1, MAX_PARTITIONS + 2)
    cells = [((0,), column) for column in patterns]
    masks = [sum(1 << j for j, p in enumerate(patterns) if p & (1 << r)) for r in range(7)]
    index, plan = minimax_question(cells, masks, set(), "question")
    assert index is None and plan["used"] == "balanced"
    assert plan["reason"] == "distinct-partition-limit"
    assert plan["observable_worst_case_remaining_questions"] is None


def test_no_depth_claim_for_empty_or_conflicting_catalog_and_invalid_strategy():
    candidates = {"yes": "true", "no": "false"}
    for report in [ask(candidates, []),
                   ask(candidates, [0], [({"x": 0}, 0, True), ({"x": 0}, 0, False)])]:
        assert report["question"] is None
        assert report["planning"]["worst_case_remaining_questions"] is None
        assert report["planning"]["full_class_identification_possible"] is None
    with pytest.raises(BError, match="strategy"):
        ask(candidates, [0], strategy="random")
