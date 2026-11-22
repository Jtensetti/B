"""Decide a proposed native function's outputs against named finite policies."""
from __future__ import annotations

from collections.abc import Sequence
from itertools import product

from .clarification import Answer, Space, evaluate_space
from .discovery_contracts import NativeEvaluator, ProbeFailure, Unsupported
from .ir import ProgramIR
from .types import INT


def _point(space: Space, index: int) -> dict:
    inputs, output = space.cells[index]
    return {"inputs": dict(zip(space.parameters, inputs, strict=True)), "result": output}


def _collect_outputs(space: Space, revised: ProgramIR, function: str) -> tuple[list[int], str | None, dict | None]:
    """Compare entry domains, then evaluate only a bounded, contract-checked edit."""
    indices = {cell: index for index, cell in enumerate(space.cells)}
    admitted = set(space.inputs)
    cells = []
    local = None
    try:
        evaluator = NativeEvaluator(revised, function, check_target_post=True)
        axes = space.report["scope"]["axes"]
        for point in product(*(axes[name] for name in space.parameters)):
            local = dict(zip(space.parameters, point, strict=True))
            accepts = evaluator.accepts_input(local)
            if accepts != (point in admitted):
                return cells, "revised entry domain differs on this grid", {
                    "inputs": local, "original_admits": point in admitted, "revised_admits": accepts,
                }
            if accepts:
                output = evaluator.public_result(local)
                index = indices.get((point, output))
                if index is None:
                    return cells, "revised result falls outside the output grid", {"inputs": local, "result": output}
                cells.append(index)
    except (Unsupported, ProbeFailure) as exc:
        return cells, str(exc), {"inputs": local} if local is not None else None
    return cells, None, None


def decide_edit(program: ProgramIR, revised_program: ProgramIR, function: str,
                candidates: dict[str, str], axes: dict[str, Sequence[int]],
                outputs: Sequence[int], answers: Sequence[Answer] = ()) -> dict:
    """Compare the edited target's normal returns on every admissible grid input.

    Question selection works on the edited behavior alone. A 'no' rules out
    every candidate that accepts the edit. For 'yes', prefer the cell which
    eliminates the most rejecting behavioral classes.
    """
    space = evaluate_space(program, function, candidates, axes, outputs, answers)
    policy = space.report
    names = policy["survivors"]
    scope = dict(policy["scope"])
    scope.pop("body_evaluated", None)
    scope.update(
        subject="revised-target-normal-outputs", input_domain="supplied-grid",
        policy_domain="remaining-named-candidates", original_body_evaluated=False,
        revised_evaluation="bounded-native-public-returns",
    )
    report = {
        "schema": "b-edit-clarification", "version": 1, "function": function,
        "status": "inconclusive", "scope": scope, "survivors": names,
        "policy_status": policy["status"], "disclosures": policy["disclosures"],
        "decisions": {"approve": [], "reject": []}, "rejections": [],
        "question": None, "examined_outputs": 0,
    }
    if policy["status"] in {"empty-domain", "inconsistent"}:
        return {**report, "reason": policy["status"]}
    original = next(stmt for stmt in program.statements if stmt.op == "fn" and stmt.name == function)
    revised = next((stmt for stmt in revised_program.statements if stmt.op == "fn" and stmt.name == function), None)
    if revised is None or revised.typ != INT or revised.params != original.params:
        return {**report, "reason": "revised target must preserve the named integer signature"}
    cells, failure, witness = _collect_outputs(space, revised_program, function)
    report["examined_outputs"] = len(cells)
    if failure:
        return {**report, "reason": failure, "witness": witness}
    if not cells:
        return {**report, "reason": "no admissible revised result on this grid"}

    # One concrete failing row per rejecting candidate suffices to audit the decision.
    rejected_at = {}
    approved = []
    for name in names:
        mask = space.masks[name]
        first = next((i for i in cells if not (mask & (1 << i))), None)
        if first is None:
            approved.append(name)
        else:
            rejected_at.setdefault(first, []).append(name)
    rejected = sorted(name for group in rejected_at.values() for name in group)
    report["decisions"] = {"approve": approved, "reject": rejected}
    report["rejections"] = [
        {**_point(space, i), "forbidden_by": [name for name in names if not (space.masks[name] & (1 << i))]}
        for i in rejected_at
    ]
    if not rejected:
        return {**report, "status": "approve", "reason": "all remaining policies admit every revised output on this grid"}
    if not approved:
        return {**report, "status": "reject", "reason": "each remaining policy forbids at least one revised output on this grid"}

    # Equivalent labels have one vote. The simplicity ordering is independent
    # of the user's order of candidate labels, parameter axes and output lists.
    representatives = [group[0] for group in policy["classes"]]
    choices = []
    for i in cells:
        if i in space.skipped:
            continue
        forbidden = sum(not (space.masks[name] & (1 << i)) for name in representatives)
        if forbidden:
            inputs, result = space.cells[i]
            values = (*inputs, result)
            choices.append(((-forbidden, sum(map(abs, values)), tuple(map(abs, values)), values), i))
    if not choices:
        return {**report, "reason": "all distinguishing revised outputs have unanswered questions"}
    _, best = min(choices)
    bit = 1 << best
    question = {**_point(space, best),
                "allowed_by": [name for name in names if space.masks[name] & bit],
                "forbidden_by": [name for name in names if not (space.masks[name] & bit)]}
    return {**report, "status": "needs-answer", "reason": "remaining policies disagree about this edit",
            "question": question}
