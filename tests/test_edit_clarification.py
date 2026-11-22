"""A pending edit may have a determinate outcome before its policy has a name."""
from itertools import product

import pytest

from b_lang.compiler import compile_b
from b_lang.clarification import compare
from b_lang.edit_clarification import decide_edit
from b_lang.runtime import BContractError


def program(body, *, requires="", ensures=""):
    return compile_b(f"fn gap(x: Int) -> Int pure {requires} {ensures} = {body}").ir


AXES = {"x": [0, 1]}
OUTPUTS = [0, 1, 2, 3]
POLICIES = {"exact": "result == x", "one_more": "result >= x and result <= x + 1",
            "two_more": "result >= x and result <= x + 2", "nonnegative": "result >= 0"}


def decide(edited, *, old=None, candidates=None, answers=()):
    return decide_edit(old if old is not None else program("x"), edited, "gap",
                       candidates if candidates is not None else POLICIES, AXES, OUTPUTS, answers)


def test_unambiguous_edit_needs_no_policy_identity_or_runtime_import(capsys):
    # Top-level code is observable in ordinary B execution.
    before = compile_b("fn gap(x: Int) -> Int = x + 1000\nprint 12345").ir
    after = compile_b("fn gap(x: Int) -> Int = x\nprint 6789").ir
    assert compare(before, "gap", POLICIES, AXES, OUTPUTS)["status"] == "question"
    decision = decide(after, old=before)
    assert decision["status"] == "approve" and decision["question"] is None
    assert decision["decisions"] == {"approve": sorted(POLICIES), "reject": []}
    assert decision["examined_outputs"] == 2
    assert capsys.readouterr().out == ""


def test_question_is_an_actual_output_and_no_directly_rejects_edit():
    revised = program("x + 1")
    decision = decide(revised)
    q = decision["question"]
    assert decision["status"] == "needs-answer"
    assert q["result"] == q["inputs"]["x"] + 1 and q["forbidden_by"] == ["exact"]
    assert decide(revised, answers=[(q["inputs"], q["result"], True)])["status"] == "approve"
    negative = decide(revised, answers=[(q["inputs"], q["result"], False)])
    assert negative["status"] == "reject" and negative["survivors"] == ["exact"]


def test_each_policy_can_reject_the_edit_at_a_different_input():
    candidates = {"accept_first": "x == 0 or result == 0",
                  "accept_second": "x == 1 or result == 0"}
    decision = decide(program("1"), candidates=candidates)
    assert decision["status"] == "reject" and decision["question"] is None
    assert {w["inputs"]["x"] for w in decision["rejections"]} == {0, 1}
    assert all(len(w["forbidden_by"]) == 1 for w in decision["rejections"])


def test_edit_split_counts_distinct_behaviors_and_handles_abstention():
    candidates = {
        "all": "true", "at_zero": "x != 0 or result != 1",
        "copy_one": "x != 0 or result != 1", "copy_two": "x != 0 or result != 1",
        "at_one": "x != 1 or result != 1",
        "also_at_one": "(x != 1 or result != 1) and result != 3",
    }
    initial = decide(program("1"), candidates=candidates)
    q = initial["question"]
    assert q["inputs"] == {"x": 1} and set(q["forbidden_by"]) == {"at_one", "also_at_one"}
    skipped = [(q["inputs"], q["result"], None)]
    q2 = decide(program("1"), candidates=candidates, answers=skipped)["question"]
    assert q2["inputs"] == {"x": 0}
    skipped.append((q2["inputs"], q2["result"], None))
    undecided = decide(program("1"), candidates=candidates, answers=skipped)
    assert undecided["status"] == "inconclusive" and undecided["question"] is None
    assert set(undecided["survivors"]) == set(candidates)
    answered = decide(program("1"), candidates=candidates, answers=skipped + [({"x": 0}, 1, False)])
    assert answered["status"] == "reject"


@pytest.mark.parametrize("before,after", [("", "requires x > 0"), ("requires x > 0", "")])
def test_widening_and_narrowing_an_input_domain_are_inconclusive(before, after):
    decision = decide(program("x", requires=after), old=program("x", requires=before))
    assert decision["status"] == "inconclusive" and "entry domain" in decision["reason"]
    assert decision["witness"]["inputs"] == {"x": 0}
    assert decision["witness"]["revised_admits"] != decision["witness"]["original_admits"]


@pytest.mark.parametrize("revised,detail", [
    (program("x + 4"), "outside the output"),
    (program("x", ensures="ensures result < 1"), "postcondition failed"),
    (program("4 % x"), "remainder by zero"),
    (program("x", ensures="ensures result <= 2.5"), "unsupported"),
    (compile_b("fn gap(y: Int) -> Int = y").ir, "signature"),
])
def test_outside_scope_and_raising_edits_do_not_gain_approval(revised, detail):
    decision = decide(revised)
    assert decision["status"] == "inconclusive" and detail in decision["reason"]
    assert decision["decisions"] == {"approve": [], "reject": []}


def test_foreign_revisions_are_never_invoked(tmp_path, monkeypatch):
    module = "b_edit_fixture"
    (tmp_path / f"{module}.py").write_text('raise RuntimeError("foreign initialization")\ndef value(x: int) -> int:\n    return x\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    after = compile_b(f"use py:{module} as ext\nfn gap(x: Int) -> Int = ext.value(x)").ir
    decision = decide(after)
    assert decision["status"] == "inconclusive"
    assert decision["decisions"]["approve"] == []


def test_catalog_refuted_by_two_negative_labels_is_inconclusive():
    candidates = {"zero": "result == 0", "one": "result == 1"}
    ans = [({"x": 0}, 0, False), ({"x": 0}, 1, False)]
    decision = decide(program("1"), candidates=candidates, answers=ans)
    assert decision["status"] == "inconclusive" and decision["reason"] == "inconsistent"
    assert decision["survivors"] == []


def test_uniform_catalog_after_finite_answers_cannot_approve_other_inputs():
    before = program("x")
    changed = program("if x == 17 then 100 else x")
    decision = decide(changed, old=before)
    assert decision["status"] == "approve"
    assert decision["scope"]["axes"]["x"] == [0, 1]
    assert decision["examined_outputs"] == 2


def test_agreement_with_independent_allowed_output_tables_for_every_small_edit():
    # Enumerate all edit bodies on two points. One explicit requirement per
    # input/output table; compute scores from Python predicates, not B masks.
    candidates = {"same": "result == x", "at_least": "result >= x",
                  "at_most": "result <= x", "nonnegative": "result >= 0"}
    rules = {"same": lambda x, r: r == x, "at_least": lambda x, r: r >= x,
             "at_most": lambda x, r: r <= x, "nonnegative": lambda x, r: r >= 0}
    for outputs in product(range(3), repeat=2):
        body = f"if x == 0 then {outputs[0]} else {outputs[1]}"
        got = decide(program(body), candidates=candidates)
        approved = sorted(n for n, rule in rules.items() if all(rule(x, r) for x, r in enumerate(outputs)))
        assert got["decisions"]["approve"] == approved
        assert got["decisions"]["reject"] == sorted(set(rules) - set(approved))
        if got["question"]:
            q = got["question"]
            assert q["result"] == outputs[q["inputs"]["x"]]
            assert q["allowed_by"] and q["forbidden_by"]



def test_approval_of_current_returns_does_not_certify_freedom_of_future_edits():
    before = program("x")
    after = program("x", ensures="ensures result == x")
    decision = decide(after, old=before)
    assert decision["status"] == "approve"
    assert decision["scope"]["subject"] == "revised-target-normal-outputs"
    assert decision["scope"]["policy_domain"] == "remaining-named-candidates"
    assert decision["scope"]["input_domain"] == "supplied-grid"
    # Independent interface check: one policy allows returning 1 for x=0.
    # The revised declaration now excludes it, though every actual return is allowed.
    source = "fn gap(x: Int) -> Int pure ensures result == x = x + 1"
    revised_again = compile_b(source)
    ns = {}
    exec(revised_again.code, ns)
    with pytest.raises(BContractError):
        ns["gap"](0)
