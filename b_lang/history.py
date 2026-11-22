"""Select exact implementations of checked predicates on pairs of list items."""
from __future__ import annotations

from dataclasses import replace

from .ir import ExprIR
from .types import BOOL, INT, NONE, TEXT, BError, Type


_SCALARS = {BOOL, INT, NONE, TEXT}
_PREDICATE_OPS = {"literal", "name", "lookup", "coalesce", "conditional", "cmp",
                  "and", "or", "not", "neg", "add", "sub", "mul"}
_REVERSE = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}
_COMPLEMENT = {"<": ">=", "<=": ">", ">": "<=", ">=": "<"}


def _supported_type(typ: Type) -> bool:
    if typ.name == "Option":
        return _supported_type(typ.args[0])
    if typ.name == "Dict":
        return typ.args[0] == TEXT and _supported_type(typ.args[1])
    return typ in _SCALARS


def _is_scalar(typ: Type) -> bool:
    return _is_scalar(typ.args[0]) if typ.name == "Option" else typ in _SCALARS


def _validate(node: ExprIR) -> None:
    # The frontend already checked each operator's operand types. Enforce the
    # narrower fragment whose operands may also be evaluated early or once.
    if node.op not in _PREDICATE_OPS:
        raise BError("E_HISTORY_PREDICATE", f"History predicates cannot use {node.op}")
    if not _supported_type(node.typ):
        raise BError("E_HISTORY_PREDICATE", f"History predicates cannot use {node.typ}")
    if node.op in {"add", "sub", "mul", "neg"} and node.typ != INT:
        raise BError("E_HISTORY_PREDICATE", "History arithmetic requires Int operands")
    if node.op == "cmp":
        left, right = (part.typ for part in node.operands)
        if node.data in _REVERSE:
            if left != right or left not in {INT, BOOL, TEXT}:
                raise BError("E_HISTORY_PREDICATE", "History ordering requires matching scalar operands")
        elif NONE not in (left, right) and not (_is_scalar(left) and _is_scalar(right)):
            raise BError("E_HISTORY_PREDICATE", "History equality supports scalars and presence checks")
    for child in node.operands:
        _validate(child)


def _references(node: ExprIR, binders: set[str]) -> set[str]:
    if node.op == "name" and node.data in binders:
        return {node.data}
    result = set()
    for child in node.operands:
        result.update(_references(child, binders))
    return result


def order_comparison(predicate: ExprIR) -> ExprIR | None:
    """Normalize a direct or negated ordering of two exact integers."""
    negated = predicate.op == "not"
    comparison = predicate.operands[0] if negated else predicate
    if (comparison.op != "cmp" or comparison.data not in _REVERSE
            or any(child.typ != INT for child in comparison.operands)):
        return None
    return replace(comparison, data=_COMPLEMENT[comparison.data]) if negated else comparison


def history_plan(predicate: ExprIR, past: str, current: str, mode: str) -> dict:
    """Return a plan equivalent to the ordered pair predicate on valid inputs."""
    if mode not in ("adjacent", "earlier"):
        raise BError("E_INTERNAL", f"Unknown history mode {mode}")
    if predicate.typ != BOOL:
        raise BError("E_HISTORY_PREDICATE", "History predicates must return Bool")
    _validate(predicate)
    fallback = {"plan": "previous-item" if mode == "adjacent" else "prefix-search"}
    if mode == "adjacent":
        if predicate.op != "and":
            return fallback
    else:
        comparison = order_comparison(predicate)
        if comparison is None:
            return fallback
        predicate = comparison

    binders = {past, current}
    left, right = (_references(part, binders) for part in predicate.operands)
    if left == {past} and right == {current}:
        past_side = 0
    elif left == {current} and right == {past}:
        past_side = 1
    else:
        return fallback
    if mode == "adjacent":
        return {"plan": "previous-test", "past_side": past_side}
    # Normalize to past op current. Some past value > current holds precisely
    # when the prefix maximum > current, and dually for the minimum.
    op = _REVERSE[predicate.data] if past_side else predicate.data
    return {"plan": "prefix-min" if op in ("<", "<=") else "prefix-max",
            "past_side": past_side, "comparison": op}
