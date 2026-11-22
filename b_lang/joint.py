"""Check a relation on pairs of normal native calls over named finite input grids."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from itertools import product
from math import prod

from . import clarification as finite
from .compiler import parse_postcondition
from .discovery_contracts import NativeEvaluator, ProbeFailure, Unsupported
from .ir import ExprIR, ProgramIR, StmtIR
from .types import BError, INT

MAX_PAIRS = 4096


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() <= set(required) | set(optional):
        raise BError("E_JOINT_INPUT", f"Expected fields {', '.join(required)}; optional {', '.join(optional) or 'none'}")


def _joint_error(exc: BError) -> BError:
    codes = {"E_CLARIFY_LIMIT": "E_JOINT_LIMIT", "E_CLARIFY_INPUT": "E_JOINT_INPUT"}
    return BError(codes.get(exc.code, "E_JOINT_UNSUPPORTED"), exc.message)


@dataclass(frozen=True)
class _Role:
    name: str
    params: tuple[str, ...]
    axes: tuple[tuple[int, ...], ...]

    def inputs(self, point):
        return dict(zip(self.params, point, strict=True))


def _role(functions, data):
    _fields(data, ("function", "axes"))
    name, axes = data["function"], data["axes"]
    if not isinstance(name, str) or name not in functions:
        raise BError("E_JOINT_INPUT", f"Unknown native function {name!r}")
    fn = functions[name]
    params = tuple(n for n, _ in fn.params)
    if "result" in params:
        raise BError("E_JOINT_UNSUPPORTED", f"Parameter 'result' in {name} would shadow its output in the relation")
    if not isinstance(axes, dict) or axes.keys() != set(params):
        raise BError("E_JOINT_INPUT", f"Expected one input axis per parameter of {name}{params}")
    try:
        values = tuple(finite._axis(axes[n]) for n in params)
    except BError as exc:
        raise _joint_error(exc) from exc
    return _Role(name, params, values)


def _predicate(source: str, names: tuple[str, ...]) -> ExprIR:
    # Type-check the exact same expression fragment and arithmetic used for
    # finite policy questions. Only the named role variables are in scope.
    scope = StmtIR("fn", typ=INT, params=tuple((name, INT) for name in names))
    try:
        finite._preflight(source)
        predicate = parse_postcondition(source, scope)
        finite._check_expression(predicate, set(names))
    except BError as exc:
        raise _joint_error(exc) from exc
    except (RecursionError, ValueError) as exc:
        raise BError("E_JOINT_UNSUPPORTED", "Could not check the joint predicate") from exc
    return predicate


def _failed_comparison(node, env):
    # An AND needs every conjunct. Only report a single comparison when it is
    # enough to explain the failure (a false arm of an OR would not be).
    while node.op == "and":
        lhs, rhs = node.operands
        node = rhs if finite._evaluate(lhs, env) else lhs
    if node.op == "cmp":
        lhs, rhs = node.operands
        return {"left_value": finite._evaluate(lhs, env), "operator": node.data,
                "right_value": finite._evaluate(rhs, env)}
    return None


def check_joint(program: ProgramIR, request: dict) -> dict:
    """Test each ordered pair selected by the input-only guard, on this revision.

    A reported violation includes two actual normal returns. Unsupported bodies,
    failed calls and exhausted arithmetic bounds can never yield a pass. A
    concrete violating pair takes priority over an earlier incomplete pair.
    """
    _fields(request, ("left", "ensures"), ("right", "where"))
    functions = {s.name: s for s in program.statements if s.op == "fn"}
    left = _role(functions, request["left"])
    right = _role(functions, request["right"]) if "right" in request else left
    lsize, rsize = (prod(map(len, role.axes)) for role in (left, right))
    if max(lsize, rsize, lsize * rsize) > MAX_PAIRS:
        raise BError("E_JOINT_LIMIT", f"Joint input grid exceeds {MAX_PAIRS} ordered pairs or calls per role")
    left_names = tuple("left_" + n for n in left.params)
    right_names = tuple("right_" + n for n in right.params)
    names = left_names + right_names
    guard = _predicate(request["where"], names) if "where" in request else None
    relation = _predicate(request["ensures"], (*names, "left_result", "right_result"))
    report = {"schema": "b-joint-check", "version": 1, "scope": "declared-finite-grid",
              "left": left.name, "right": right.name, "grid_pairs": lsize * rsize,
              "relation": request["ensures"], "checked_pairs": 0}
    if not report["grid_pairs"]:
        return {**report, "status": "inconclusive", "reason": "no pairs were selected"}

    evaluators = {}
    try:
        for name in dict.fromkeys((left.name, right.name)):
            evaluators[name] = NativeEvaluator(program, name, check_target_post=True)
    except Unsupported as exc:
        return {**report, "status": "inconclusive", "reason": str(exc)}

    @cache
    def observe(name, point):
        fn = functions[name]
        inputs = dict(zip((n for n, _ in fn.params), point, strict=True))
        call = {"function": name, "inputs": inputs}
        try:
            call["result"] = evaluators[name].public_result(inputs)
        except (ProbeFailure, Unsupported) as exc:
            call["error"] = str(exc)
        return call

    incomplete = None
    for a, b in product(product(*left.axes), product(*right.axes)):
        env = dict(zip(names, a + b, strict=True))
        try:
            if guard is not None and not finite._evaluate(guard, env):
                continue
        except BError as exc:
            if incomplete is None:
                incomplete = {"reason": exc.message,
                              "witness": {"left": {"function": left.name, "inputs": left.inputs(a)},
                                          "right": {"function": right.name, "inputs": right.inputs(b)}}}
            continue
        ca, cb = observe(left.name, a), observe(right.name, b)
        witness = {"left": ca, "right": cb}
        if "error" in ca or "error" in cb:
            if incomplete is None:
                incomplete = {"reason": "a selected call could not produce a checked normal return",
                              "witness": witness}
            continue
        env.update(left_result=ca["result"], right_result=cb["result"])
        try:
            holds = finite._evaluate(relation, env)
        except BError as exc:
            if incomplete is None:
                incomplete = {"reason": exc.message, "witness": witness}
            continue
        report["checked_pairs"] += 1
        if not holds:
            failure = {**report, "status": "violated", "witness": witness}
            comparison = _failed_comparison(relation, env)
            if comparison is not None:
                failure["failed_comparison"] = comparison
            return failure
    if incomplete is not None:
        return {**report, "status": "inconclusive", **incomplete}
    if not report["checked_pairs"]:
        return {**report, "status": "inconclusive", "reason": "no pairs were selected"}
    return {**report, "status": "passed"}
