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

    excludes_zero: bool = False  # An integer disequality that a single range cannot express.

    @property
    def nonzero(self) -> bool:
        return self.excludes_zero or (self.lo is not None and self.lo > 0) or (self.hi is not None and self.hi < 0)

    def intersect(self, other: "Interval") -> "Interval":
        lo = max(x for x in (self.lo, other.lo) if x is not None) if (self.lo is not None or other.lo is not None) else None
        hi = min(x for x in (self.hi, other.hi) if x is not None) if (self.hi is not None or other.hi is not None) else None
        excludes_zero = self.excludes_zero or other.excludes_zero
        if excludes_zero and lo == 0:
            lo = 1
        if excludes_zero and hi == 0:
            hi = -1
        if lo is not None and hi is not None and lo > hi:
            raise BError("E_PRECONDITION_EMPTY", "Integer requirements have no possible input")
        return Interval(lo, hi, excludes_zero)


def restrict(pre: ExprIR | None, names: set[str]) -> dict[str, Interval]:
    bounds = {name: Interval() for name in names}
    if pre is not None:
        narrow(pre, bounds, extended=False)
    return bounds


def narrow(node: ExprIR, bounds: dict[str, Interval], when: bool = True, *, extended: bool = True) -> None:
    """Intersect simple named Int constraints in place. Empty paths raise BError."""
    if node.op == "not" and extended:
        narrow(node.operands[0], bounds, not when)
        return
    if (when and node.op == "and") or (not when and node.op == "or"):
        for operand in node.operands:
            narrow(operand, bounds, when, extended=extended)
        return
    if node.op != "cmp":
        return
    left, right = node.operands
    op = node.data
    if right.op == "name":
        op = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}[op]
        left, right = right, left
    if left.op != "name" or left.typ != INT or left.data not in bounds:
        return
    if right.op == "literal" and type(right.data) is int:
        k = right.data
    elif extended and right.op == "neg" and right.operands[0].op == "literal" and type(right.operands[0].data) is int:
        k = -right.operands[0].data
    else:
        return
    if not when:
        op = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "==": "!=", "!=": "=="}[op]
    limit = {">": Interval(k+1, None), ">=": Interval(k, None),
             "<": Interval(None, k-1), "<=": Interval(None, k), "==": Interval(k, k)}.get(op)
    if extended and op == "!=" and k == 0:
        limit = Interval(excludes_zero=True)
    if limit is not None:
        bounds[left.data] = bounds[left.data].intersect(limit)


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
    if op in ("neg", "add", "sub", "mul"):
        values = tuple(value_interval(arg, env) for arg in args)
        return arithmetic_interval(op, *values)
    return None


def arithmetic_interval(op: str, a: Interval | None, b: Interval | None = None) -> Interval | None:
    if a is None:
        return None
    if op == "neg":
        return Interval(-a.hi if a.hi is not None else None, -a.lo if a.lo is not None else None,
                        a.excludes_zero)
    if b is None:
        return None
    if op == "add":
        return Interval(_sum_bound(a.lo, b.lo), _sum_bound(a.hi, b.hi))
    if op == "sub":
        return Interval(_sum_bound(a.lo, -b.hi if b.hi is not None else None),
                        _sum_bound(a.hi, -b.lo if b.lo is not None else None))
    if op == "mul":
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
        left = truth(args[0], env)
        # An unsupported first operand can fail before the right operand runs.
        # A tautology on the right supplies no evidence that evaluation finishes.
        if left is None or (op == "and" and not left) or (op == "or" and left):
            return left
        return truth(args[1], env)
    if op != "cmp":
        return None
    a, b = value_interval(args[0], env), value_interval(args[1], env)
    return compare_intervals(node.data, a, b)


def compare_intervals(which: str, a: Interval | None, b: Interval | None) -> bool | None:
    if a is None or b is None:
        return None
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
        if disjoint or (a.lo == a.hi == 0 and b.nonzero) or (b.lo == b.hi == 0 and a.nonzero):
            return which == "!="
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
