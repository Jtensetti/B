"""Agent-facing contract proposals and independent checks of equality expectations."""
from __future__ import annotations

from . import affine
from .compiler import parse_postcondition
from .discovery_contracts import discover
from .ir import ProgramIR
from .types import BError, INT


def _sample_contradiction(form: affine.Form, observations: list[dict]) -> dict | None:
    for row in observations:
        inputs = row["inputs"]
        prediction = form.constant + sum(c * inputs[k] for k, c in form.terms)
        if prediction != row["result"]:
            return {"inputs": inputs, "expected": prediction, "observed": row["result"]}
    return None


def report(program: ProgramIR, function: str, *, expect: str | None = None, trace: bool = False) -> dict:
    functions = {s.name: s for s in program.statements if s.op == "fn"}
    if function not in functions:
        raise BError("E_FUNCTION", f"Unknown B function {function}")
    fn = functions[function]
    expectation = None
    if expect is not None:
        checked = parse_postcondition(expect, fn)
        if fn.typ == INT and all(t == INT for _, t in fn.params):
            expectation = affine.declared(checked, [n for n, _ in fn.params])
        if expectation is None:
            raise BError("E_EXPECT", "Expected an exact affine Int equality involving result")

    observations = discover(program, function)
    candidate = observations["candidate_form"]
    # This proof sees no observations, no target postcondition as an assumption,
    # and no externally supplied summaries. Each native body dependency is checked.
    evidence = None
    if candidate is not None or expectation is not None:
        evidence = affine.implementation(fn, functions, {}, expand_bodies=True)
    verification = {"status": "not-attempted" if candidate is None else "unknown"}
    if candidate is not None and evidence is not None and evidence.form.to_dict() == candidate:
        verification = {"status": "proved", "method": "affine-normalization",
                        "body_dependencies": list(evidence.body_dependencies)}
    samples = observations["observations"]
    survivors_count = None
    if observations["survivors"] or observations["status"] == "no-match":
        survivors_count = len(observations["survivors"])
    result = {
        "schema": "b-contract-discovery", "version": 1, "function": function,
        "status": observations["status"], "reason": observations["reason"],
        "proposed_contract": observations["proposed_contract"], "verification": verification,
        "proposal_origin": "current-implementation", "intent": "unspecified",
        "observed_value": "body-result-before-target-ensures",
        "observations_count": len(samples),
        "survivors_count": survivors_count,
        "declared_audit": observations["declared_audit"],
        "declared_counterexample": observations["declared_counterexample"],
    }
    if "probe_failure" in observations:
        result["probe_failure"] = observations["probe_failure"]
    if expectation is not None:
        witness = _sample_contradiction(expectation, samples)
        expected = {"expression": expect, "origin": "caller-supplied", "status": "unknown"}
        if witness is not None:
            expected.update(status="refuted", counterexample=witness)
        elif evidence is not None and evidence.form == expectation:
            expected.update(status="proved", method="affine-normalization",
                            body_dependencies=list(evidence.body_dependencies))
        result["expectation"] = expected
    if trace:
        result["trace"] = observations
    return result
