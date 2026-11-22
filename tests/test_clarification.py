"""Finite policy comparisons use the specified alternatives and domain only."""
from copy import deepcopy
from dataclasses import replace
from itertools import product

import pytest

from b_lang.clarification import compare, evaluate_space
from b_lang.compiler import compile_b
from b_lang.types import BError


def ir(source="fn f(x: Int) -> Int = x"):
    return compile_b(source).ir


def test_masks_match_independent_relation_oracle_and_respect_requires():
    program = ir("fn f(x: Int, y: Int) -> Int requires x + y >= 0 = x")
    candidates = {"equal": "result == x + y", "nonnegative": "result >= 0",
                  "signed": "(x * -2 + y < result and not (x == y)) or result == -y"}
    oracle = {"equal": lambda x, y, r: r == x + y,
              "nonnegative": lambda x, y, r: r >= 0,
              "signed": lambda x, y, r: (x * -2 + y < r and x != y) or r == -y}
    xs = [-2, -1, 0, 1, 2]
    space = evaluate_space(program, "f", candidates, {"x": xs, "y": xs}, xs)
    assert space.cells == tuple(((x, y), r) for x, y, r in product(xs, repeat=3) if x + y >= 0)
    for i, ((x, y), result) in enumerate(space.cells):
        for name, accepts in oracle.items():
            assert bool((space.masks[name] >> i) & 1) == accepts(x, y, result)
    assert space.report["scope"]["admissible_inputs"] == 15
    assert space.report["scope"]["cells"] == 75


def test_body_and_declared_contract_do_not_supply_answers_or_run():
    class Unreadable:
        def __getattr__(self, name):
            raise AssertionError("Read body or declared postcondition")

    program = ir("fn f(x: Int) -> Int ensures result == x = x")
    unread = replace(program.statements[0], expr=Unreadable(), ensures=Unreadable())
    program = replace(program, statements=(unread,))
    policies = {"exact": "result == x", "lower": "result >= x"}
    response = compare(program, "f", policies, {"x": [0]}, [0, 1])
    assert response["status"] == "question" and response["scope"]["body_evaluated"] is False
    assert response["question"]["inputs"] == {"x": 0} and response["question"]["result"] == 1
    chosen = compare(program, "f", policies, {"x": [0]}, [0, 1], [({"x": 0}, 1, True)])
    assert chosen["status"] == "selected" and chosen["survivors"] == ["lower"]


def test_equivalent_names_do_not_vote_twice_and_permutations_do_not_change_the_question():
    policies = {"a": "result==1", "b": "result==0", "c": "result!=1", "d": "result==2"}
    axes = {"x": [0]}
    outputs = [0, 1, 2]
    initial = compare(ir(), "f", policies, axes, outputs)
    aliases = {**policies, **{f"a{i}": "result>0 and result<2" for i in range(7)}}
    reordered = dict(reversed(list(aliases.items())))
    more = compare(ir(), "f", reordered, {"x": [0, 0]}, [2, 1, 0, 1])
    assert initial["question"]["result"] == more["question"]["result"] == 0
    assert more["question"]["allowed_classes"] == more["question"]["forbidden_classes"] == 2
    assert more["disclosures"]["initial_classes"] == 4
    assert sorted(more["question"]["allowed_by"] + more["question"]["forbidden_by"]) == sorted(aliases)


def test_equivalence_is_scoped_and_all_aliases_survive():
    cases = {"true": "true", "bounded": "result < 4"}
    report = compare(ir(), "f", cases, {"x": [0]}, [0, 1])
    assert report["status"] == "equivalent-on-grid"
    assert report["classes"] == [["bounded", "true"]] and report["question"] is None
    larger = compare(ir(), "f", cases, {"x": [0]}, [0, 4])
    assert larger["question"]["result"] == 4


def test_abstentions_do_not_filter_and_definite_evidence_overrides_them_in_either_order():
    cases = {"any": "true", "zero": "result == 0"}
    args = (ir(), "f", cases, {"x": [0]}, [0, 1, 2])
    answers = [({"x": 0}, 1, None)]
    skipped = evaluate_space(*args, answers)
    assert skipped.report["question"]["result"] == 2 and len(skipped.skipped) == 1
    answers.append(({"x": 0}, 2, None))
    undecided = compare(*args, answers)
    assert undecided["status"] == "undetermined" and len(undecided["survivors"]) == 2
    definite = ({"x": 0}, 1, False)
    for replay in (answers + [definite], [definite] + answers):
        report = compare(*args, replay)
        assert report["survivors"] == ["zero"] and report["disclosures"]["skipped_cells"] == 1
        assert report["disclosures"]["abstentions"] == 2 and report["disclosures"]["definite_cells"] == 1


def test_contradictory_and_unexplained_answers_have_distinct_reasons():
    cases = {"original": "result == x", "up": "result == x + 1"}
    args = (ir(), "f", cases, {"x": [0]}, [0, 1, 2])
    for answers, reason in [([({"x": 0}, 1, False), ({"x": 0}, 1, True)], "conflicting-responses"),
                            ([({"x": 0}, 2, True)], "no-candidate-fits-responses")]:
        r = compare(*args, answers)
        assert r["status"] == "inconsistent" and r["survivors"] == [] and r["reason"] == reason


def test_input_arguments_are_never_mutated_or_retained_as_live_report_aliases():
    candidates = {"A": "result == x", "B": "result >= x"}
    coordinates = [1, 0, 1]
    outputs = coordinates
    axes = {"x": coordinates}
    answers = [({"x": 0}, 0, True)]
    original = deepcopy((candidates, axes, outputs, answers))
    report = compare(ir(), "f", candidates, axes, outputs, answers)
    assert (candidates, axes, outputs, answers) == original
    report["scope"]["axes"]["x"].append(42)
    assert outputs == [1, 0, 1]


@pytest.mark.parametrize("xs,ys", [([], [0]), ([0, 1], []), ([-1, -2], [0, 1])])
def test_empty_cells_cannot_select_an_intent(xs, ys):
    src = ir("fn f(x: Int) -> Int requires x >= 0 = 0")
    report = compare(src, "f", {"always": "true", "never": "false"}, {"x": xs}, ys)
    assert report["status"] == "empty-domain" and report["question"] is None
    assert report["scope"]["cells"] == 0


def test_zero_parameter_function_still_has_one_input_row():
    report = compare(ir("fn f() -> Int = 0"), "f", {"one": "result == 1", "zero": "result == 0"}, {}, [1, 0])
    assert report["scope"]["admissible_inputs"] == 1 and report["question"]["inputs"] == {}


@pytest.mark.parametrize("answers", [
    [({"x": -1}, 0, True)], [({"x": 0}, 20, None)], [({}, 0, True)],
    [({"x": True}, 0, True)], [({"x": 0}, False, True)], [({"x": 0}, 0, 1)],
])
def test_out_of_domain_or_non_boolean_answers_are_rejected(answers):
    with pytest.raises(BError) as exc:
        compare(ir("fn f(x:Int)->Int requires x >= 0 = x"), "f",
                {"one": "result == 1", "zero": "result == 0"}, {"x": [-1, 0]}, [0, 1], answers)
    assert exc.value.code == "E_CLARIFY_INPUT"


@pytest.mark.parametrize("bad", ["result / 2 == x", "result >= 1.0", "f(result) == x",
                                  'result == 0\nprint 123', "result == x or x == \"a\""])
def test_unsupported_source_never_becomes_a_vote(bad):
    with pytest.raises(BError) as exc:
        compare(ir(), "f", {"requested": bad, "other": "true"}, {"x": [0]}, [0])
    assert exc.value.code == "E_CLARIFY_UNSUPPORTED"


def test_budget_precedes_cartesian_allocation_and_arithmetic_declines_outside_range():
    options = {"zero": "result == 0", "other": "true"}
    with pytest.raises(BError, match="Cartesian") as exc:
        compare(ir("fn f(x:Int, y:Int)->Int=x"), "f", options, {"x": range(256), "y": range(256)}, [0])
    assert exc.value.code == "E_CLARIFY_LIMIT"
    with pytest.raises(BError) as exc:
        compare(ir(), "f", options, {"x": range(10**40)}, [0])
    assert exc.value.code == "E_CLARIFY_LIMIT"
    with pytest.raises(BError) as exc:
        compare(ir(), "f", {"tiny": "x * x <= result", "free": "true"}, {"x": [2**180]}, [0])
    assert exc.value.code == "E_CLARIFY_LIMIT"


def test_unsupported_entry_contract_fails_even_on_an_empty_grid():
    with pytest.raises(BError) as exc:
        compare(ir("fn f(x:Int)->Int requires x > 0.5 = x"), "f",
                {"a": "true", "b": "false"}, {"x": []}, [])
    assert exc.value.code == "E_CLARIFY_UNSUPPORTED"
