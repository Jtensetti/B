"""Small, sound-by-construction interval checker for B function contracts.

This is deliberately NOT a general theorem prover. It only certifies properties
of side-effect-free integer expressions over conservative interval bounds.
Anything else stays a runtime obligation, never an invented proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ir import ExprIR
from .types import BError, INT

_ALLOWED = {"literal", "name", "add", "sub", "mul", "neg", "cmp", "not", "and", "or"}


def validate_predicate(expr: ExprIR, allowed: set[str]) -> None:
    """Reject executable calls and accidental dependencies in specifications."""
    if expr.op not in _ALLOWED:
        raise BError("E_CONTRACT", f"Contract cannot contain {expr.op}; use pure comparisons and arithmetic")
    if expr.op == "name" and expr.data not in allowed:
        raise BError("E_CONTRACT", f"Contract cannot reference {expr.data}; expected only parameters/result")
    for child in expr.operands:
        validate_predicate(child, allowed)


def constant(expr: ExprIR, env: dict[str, Any]) -> Any | None:
    """Evaluate a closed, whitelisted contract expression without eval/exec.

    None signals unknown (it cannot be a legal contract Bool result).
    """
    try:
        op, c = expr.op, expr.operands
        if op == "literal":
            return expr.data
        if op == "name":
            return env.get(expr.data)
        if op == "neg":
            v = constant(c[0], env)
            return -v if type(v) in (int, float) else None
        if op in ("add", "sub", "mul"):
            left, right = constant(c[0], env), constant(c[1], env)
            if type(left) not in (int, float) or type(right) not in (int, float):
                return None
            return {"add": lambda: left + right, "sub": lambda: left - right,
                    "mul": lambda: left * right}[op]()
        if op == "cmp":
            a, b = constant(c[0], env), constant(c[1], env)
            if a is None or b is None:
                return None
            comparisons = {"==": a == b, "!=": a != b, "<": a < b,
                           "<=": a <= b, ">": a > b, ">=": a >= b}
            return comparisons[expr.data]
        if op == "not":
            value = constant(c[0], env)
            return not value if type(value) is bool else None
        if op in ("and", "or"):
            a = constant(c[0], env)
            if type(a) is bool and ((op == "and" and not a) or (op == "or" and a)):
                return a
            b = constant(c[1], env)
            if type(a) is bool and type(b) is bool:
                return a and b if op == "and" else a or b
    except (OverflowError, TypeError, ValueError, KeyError):
        return None
    return None


@dataclass(frozen=True)
class Interval:
    lo: int | None = None  # None means negative infinity
    hi: int | None = None  # None means positive infinity

    def intersect(self, other: "Interval") -> "Interval":
        lo = max(x for x in (self.lo, other.lo) if x is not None) if (self.lo is not None or other.lo is not None) else None
        hi = min(x for x in (self.hi, other.hi) if x is not None) if (self.hi is not None or other.hi is not None) else None
        if lo is not None and hi is not None and lo > hi:
            raise BError("E_PRECONDITION_EMPTY", "Integer requirements have no possible input")
        return Interval(lo, hi)


def restrict(pre: ExprIR | None, names: set[str]) -> dict[str, Interval]:
    bounds = {name: Interval() for name in names}
    def apply(node: ExprIR) -> None:
        if node.op == "and":
            apply(node.operands[0]); apply(node.operands[1]); return
        if node.op != "cmp":
            return
        left, right = node.operands
        op = node.data
        if right.op == "name" and left.op == "literal":
            op = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}[op]
            left, right = right, left
        if left.op != "name" or left.data not in bounds or right.op != "literal" or type(right.data) is not int:
            return
        k = right.data
        limit = {">": Interval(k+1, None), ">=": Interval(k, None),
                 "<": Interval(None, k-1), "<=": Interval(None, k),
                 "==": Interval(k, k)}.get(op)
        if limit is not None:
            bounds[left.data] = bounds[left.data].intersect(limit)
    if pre:
        apply(pre)
    return bounds


def _sum_bound(a: int | None, b: int | None) -> int | None:
    return a + b if a is not None and b is not None else None


def value_interval(node: ExprIR, env: dict[str, Interval]) -> Interval | None:
    op, args = node.op, node.operands
    if node.typ != INT:
        return None
    if op == "literal" and type(node.data) is int:
        return Interval(node.data, node.data)
    if op == "name":
        return env.get(node.data)
    if op == "guard":
        return value_interval(args[0], env)
    if op == "neg":
        v = value_interval(args[0], env)
        return Interval(-v.hi if v.hi is not None else None, -v.lo if v.lo is not None else None) if v else None
    if op in ("add", "sub", "mul"):
        a, b = value_interval(args[0], env), value_interval(args[1], env)
        if a is None or b is None:
            return None
        if op == "add":
            return Interval(_sum_bound(a.lo, b.lo), _sum_bound(a.hi, b.hi))
        if op == "sub":
            return Interval(_sum_bound(a.lo, -b.hi if b.hi is not None else None),
                            _sum_bound(a.hi, -b.lo if b.lo is not None else None))
        # Arbitrary unbounded multiplication is unknown; zero is safe.
        if (a.lo == a.hi == 0) or (b.lo == b.hi == 0):
            return Interval(0, 0)
        if None in (a.lo, a.hi, b.lo, b.hi):
            return None
        products = [x*y for x in (a.lo, a.hi) for y in (b.lo, b.hi)]
        return Interval(min(products), max(products))
    return None


def truth(node: ExprIR, env: dict[str, Interval]) -> bool | None:
    op, args = node.op, node.operands
    if op == "literal" and type(node.data) is bool:
        return node.data
    if op == "not":
        v = truth(args[0], env)
        return not v if v is not None else None
    if op in ("and", "or"):
        a, b = truth(args[0], env), truth(args[1], env)
        if op == "and":
            return False if False in (a, b) else True if a is True and b is True else None
        return True if True in (a, b) else False if a is False and b is False else None
    if op != "cmp":
        return None
    a, b = value_interval(args[0], env), value_interval(args[1], env)
    if a is None or b is None:
        return None
    which = node.data
    if which == ">=":
        if a.lo is not None and b.hi is not None and a.lo >= b.hi: return True
        if a.hi is not None and b.lo is not None and a.hi < b.lo: return False
    if which == ">":
        if a.lo is not None and b.hi is not None and a.lo > b.hi: return True
        if a.hi is not None and b.lo is not None and a.hi <= b.lo: return False
    if which == "<=":
        if a.hi is not None and b.lo is not None and a.hi <= b.lo: return True
        if a.lo is not None and b.hi is not None and a.lo > b.hi: return False
    if which == "<":
        if a.hi is not None and b.lo is not None and a.hi < b.lo: return True
        if a.lo is not None and b.hi is not None and a.lo >= b.hi: return False
    if which in ("==", "!="):
        equality = (a.lo == a.hi == b.lo == b.hi and a.lo is not None)
        disjoint = ((a.hi is not None and b.lo is not None and a.hi < b.lo)
                    or (b.hi is not None and a.lo is not None and b.hi < a.lo))
        if equality: return which == "=="
        if disjoint: return which == "!="
    return None


def verify(pre: ExprIR | None, body: ExprIR, post: ExprIR, params: dict[str, Any], result_type: Any) -> str:
    """Certify only integer interval consequences; otherwise require runtime check."""
    # Floating-point conversions are not exact; do not transfer integer proofs
    # to Float results even if the body computes an Int before coercion.
    if result_type != INT or body.typ != INT:
        return "proved-literal" if post.op == "literal" and post.data is True else "runtime-check"
    integer_names = {name for name, typ in params.items() if typ == INT}
    bounds = restrict(pre, integer_names)
    outcome = truth(post, {**bounds, "result": value_interval(body, bounds) or Interval()})
    if outcome is True:
        return "proved-interval"
    if outcome is False:
        raise BError("E_POSTCONDITION", "The function body necessarily violates its ensures clause")
    return "runtime-check"
