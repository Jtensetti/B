import itertools

import pytest

from b_lang.compiler import compile_b
from b_lang.discovery_contracts import NativeEvaluator
from b_lang.joint import check_joint
from b_lang.types import BError


def request(**changes):
    base = {"left": {"function": "gap", "axes": {"rank": [0, 1, 2]}},
            "where": "left_rank < right_rank",
            "ensures": "left_result - left_rank == right_result - right_rank"}
    return {**base, **changes}


def check(body, **changes):
    return check_joint(compile_b("fn gap(rank: Int) -> Int = " + body).ir, request(**changes))


def test_layout_classifies_all_eight_complete_layouts_against_a_separate_style_oracle():
    for offsets in itertools.product([1, 2], repeat=3):
        body = f"if rank == 0 then rank + {offsets[0]} else if rank == 1 then rank + {offsets[1]} else rank + {offsets[2]}"
        result = check(body)
        if len(set(offsets)) == 1:
            assert result["status"] == "passed" and result["checked_pairs"] == 3
        else:
            assert result["status"] == "violated"
            a, b = (result["witness"][s] for s in ("left", "right"))
            i, j = a["inputs"]["rank"], b["inputs"]["rank"]
            assert i < j and a["result"] == i + offsets[i] and b["result"] == j + offsets[j]
            assert offsets[i] != offsets[j]
            assert result["failed_comparison"] == {"left_value": offsets[i], "operator": "==", "right_value": offsets[j]}


def test_distinct_function_names_params_and_a_changed_helper():
    src = """
fn spare(x: Int) -> Int pure = x - 1
fn remaining(x: Int) -> Int pure = spare(x)
fn booked(initial: Int) -> Int pure = initial + 1
"""
    query = {"left": {"function": "remaining", "axes": {"x": [1, 2]}},
             "right": {"function": "booked", "axes": {"initial": [3, 4]}},
             "ensures": "left_result + right_result == left_x + right_initial"}
    assert check_joint(compile_b(src).ir, query)["checked_pairs"] == 4
    bad = check_joint(compile_b(src.replace("initial + 1", "initial + 2")).ir, query)
    assert bad["status"] == "violated" and bad["failed_comparison"]["left_value"] == 5


def test_symmetric_grid_reuses_program_results_and_collapses_duplicate_rows(monkeypatch):
    calls = []
    original = NativeEvaluator.public_result

    def recorded(self, inputs):
        calls.append(tuple(inputs.values()))
        return original(self, inputs)

    monkeypatch.setattr(NativeEvaluator, "public_result", recorded)
    result = check("rank + 1", left={"function": "gap", "axes": {"rank": [2, 0, 2, 1, 0]}})
    assert result["status"] == "passed" and result["grid_pairs"] == 9
    assert sorted(calls) == [(0,), (1,), (2,)]


def test_failed_target_contract_is_not_a_return_and_guards_limit_which_calls_are_observed():
    src = "fn gap(rank: Int) -> Int requires rank > 0 ensures result > 0 = rank"
    result = check_joint(compile_b(src).ir, request())
    assert result["status"] == "inconclusive"
    assert "precondition" in result["witness"]["left"]["error"]
    valid = check_joint(compile_b(src).ir, request(where="left_rank > 0 and left_rank < right_rank"))
    assert valid["status"] == "passed" and valid["checked_pairs"] == 1
    broken = check_joint(compile_b("fn gap(rank: Int) -> Int ensures result > 0 = rank").ir, request())
    assert broken["status"] == "inconclusive" and "postcondition" in broken["witness"]["left"]["error"]


def test_concrete_counterexample_takes_precedence_over_another_unsuccessful_pair():
    src = "fn gap(rank: Int) -> Int requires rank > 0 = if rank == 1 then 10 else 19"
    result = check_joint(compile_b(src).ir, request())
    assert result["status"] == "violated"
    assert result["witness"]["left"]["inputs"] == {"rank": 1}
    assert result["witness"]["right"]["inputs"] == {"rank": 2}


def test_empty_selection_and_missing_semantics_never_pass(capsys):
    assert check("rank", where="left_rank < 0")["status"] == "inconclusive"
    assert check("rank", left={"function": "gap", "axes": {"rank": []}})["status"] == "inconclusive"
    foreign = "use py:b_examples.demo_lib as lib\nfn gap(rank: Int) -> Int = lib.double(rank)"
    report = check_joint(compile_b(foreign).ir, request())
    assert report["status"] == "inconclusive"
    assert report["checked_pairs"] == 0
    assert check_joint(compile_b("fn gap(rank: Int) -> Int = rank\nprint 8").ir, request())["status"] == "passed"
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("changes", [
    {"where": "left_result > 0"},
    {"ensures": "result == 0"},
    {"ensures": "left_rank + right_rank"},
    {"ensures": "left_rank == 1\nprint 2"},
    {"right": {"function": "absent", "axes": {}}},
    {"left": {"function": "gap", "axes": {}}},
    {"left": {"function": "gap", "axes": {"rank": [True]}}},
    {"ensures": "left_rank * (2.0) > 1"},
    {"typo": 123},
])
def test_invalid_requests_rejected_without_a_result(changes):
    with pytest.raises(BError, match="E_JOINT_"):
        check("rank", **changes)


def test_grid_budget_checked_before_function_calls(monkeypatch):
    def unused(*args, **kwargs):
        raise AssertionError("should not evaluate any body")

    monkeypatch.setattr(NativeEvaluator, "public_result", unused)
    with pytest.raises(BError, match="E_JOINT_LIMIT"):
        check("rank", left={"function": "gap", "axes": {"rank": range(65)}})


def test_known_pass_does_not_extend_to_unlisted_rank():
    assert check("if rank == 99 then rank + 7 else rank + 1")["status"] == "passed"
    wider = check("if rank == 99 then rank + 7 else rank + 1",
                  left={"function": "gap", "axes": {"rank": [0, 1, 2, 99]}})
    assert wider["status"] == "violated" and wider["witness"]["right"]["inputs"] == {"rank": 99}


def test_all_pairs_including_equal_inputs_for_zero_arity_roles():
    program = compile_b("fn first() -> Int = 41\nfn second() -> Int = 42").ir
    query = {"left": {"function": "first", "axes": {}}, "right": {"function": "second", "axes": {}},
             "ensures": "right_result == left_result + 1"}
    assert check_joint(program, query)["status"] == "passed"
    assert check_joint(program, query)["checked_pairs"] == 1


def test_a_failed_disjunction_does_not_present_one_false_arm_as_proof():
    result = check("rank + 1", ensures="left_result < 0 or right_result < 0")
    assert result["status"] == "violated" and "failed_comparison" not in result
    conjunction = check("rank + 1", ensures="left_result > 0 and right_result < 0")
    assert conjunction["failed_comparison"] == {"left_value": 2, "operator": "<", "right_value": 0}


def test_bounded_relation_arithmetic_reports_unevaluable_pairs():
    value = 2 ** 100
    rule = request(left={"function": "gap", "axes": {"rank": [value]}}, where="true",
                   ensures="left_result * left_result * left_result > right_result")
    result = check_joint(compile_b("fn gap(rank: Int) -> Int = rank").ir, rule)
    assert result["status"] == "inconclusive" and result["checked_pairs"] == 0
    assert result["witness"]["left"]["result"] == value
