"""Soundness-first, local BIR simplification.

Only pure built-in literal arithmetic, comparisons and boolean expressions are
folded. Foreign calls, runtime guards, unknown purity and mutable values are
never evaluated, reordered, cached or removed by this pass.
"""
from __future__ import annotations

import math
import operator
from dataclasses import dataclass, replace

from .history import history_plan
from .ir import ExprIR, ProgramIR, StmtIR
from .types import BOOL, INT, FLOAT, TEXT, is_dim_int, is_dim_float


_ARITHMETIC = {"add": operator.add, "sub": operator.sub, "mul": operator.mul,
               "div": operator.truediv, "mod": operator.mod}
_COMPARE = {"==": operator.eq, "!=": operator.ne, "<": operator.lt,
            ">": operator.gt, "<=": operator.le, ">=": operator.ge}


@dataclass(frozen=True)
class Optimization:
    program: ProgramIR
    folds: int


def _safe_literal(value, typ):
    if typ == BOOL:
        return type(value) is bool
    if typ == INT or is_dim_int(typ):
        return type(value) is int
    if typ == FLOAT or is_dim_float(typ):
        return type(value) in (int, float) and math.isfinite(value)
    if typ == TEXT:
        return type(value) is str
    return False


def optimize(program: ProgramIR) -> Optimization:
    folds = 0

    def simplify(e: ExprIR) -> ExprIR:
        nonlocal folds
        if e.op == "literal":
            return e
        children = tuple(simplify(x) for x in e.operands)
        e = replace(e, operands=children)
        if e.op == "history_count":
            past, current, mode = (e.data[k] for k in ("past", "current", "mode"))
            plan = history_plan(children[1], past, current, mode)
            return replace(e, data={"past": past, "current": current, "mode": mode, **plan})
        if e.op in ("call", "attr", "name", "guard", "list", "dict", "builtin",
                    "builtin_from_json", "record_make", "record_field", "record_with",
                    "let_expr", "list_comp"):
            return e
        if e.op in ("and", "or") and all(x.op == "literal" and type(x.data) is bool for x in children):
            value = children[0].data and children[1].data if e.op == "and" else children[0].data or children[1].data
        elif e.op == "not" and children[0].op == "literal" and type(children[0].data) is bool:
            value = not children[0].data
        elif e.op == "neg" and children[0].op == "literal" and _safe_literal(children[0].data, e.typ):
            value = -children[0].data
        elif e.op == "conditional" and children[0].op == "literal" and type(children[0].data) is bool:
            chosen = children[1] if children[0].data else children[2]
            if chosen.typ == e.typ:
                folds += 1
                return chosen
            return e
        elif e.op in _ARITHMETIC and all(x.op == "literal" for x in children):
            a, b = children
            if not (_safe_literal(a.data, a.typ) and _safe_literal(b.data, b.typ)):
                return e
            try:
                value = _ARITHMETIC[e.op](a.data, b.data)
            except (ZeroDivisionError, OverflowError, ValueError, TypeError):
                return e
        elif e.op == "cmp" and all(x.op == "literal" for x in children):
            try:
                value = _COMPARE[e.data](children[0].data, children[1].data)
            except (TypeError, ValueError):
                return e
        else:
            return e
        if not _safe_literal(value, e.typ):
            return e
        if e.typ == FLOAT or is_dim_float(e.typ):
            value = float(value)
        folds += 1
        return ExprIR("literal", e.typ, data=value)

    stmts = tuple(replace(s, expr=simplify(s.expr)) if s.expr is not None else s for s in program.statements)
    return Optimization(replace(program, statements=stmts), folds)
