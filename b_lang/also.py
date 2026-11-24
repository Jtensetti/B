"""Extend a native Boolean predicate at explicitly named input tuples."""
import math

from .contracts import constant
from .ir import ExprIR
from .model import Stmt
from .types import BError, BOOL, FLOAT, INT, TEXT, Type


def additional_cases(statements: list[Stmt]) -> dict[str, list[tuple]]:
    cases = {}
    for statement in statements:
        if statement.kind == "also":
            name, values = statement.parts[:2]
            cases.setdefault(name, []).append(values)
    if cases:
        functions = {s.parts[0] for s in statements if s.kind == "fn"}
        for name in cases:
            if name not in functions:
                raise BError("E_ALSO", f"also requires a source function; no function named {name!r}")
    return cases


def _combine(op: str, terms: list[ExprIR]) -> ExprIR:
    """Balance the tree so the compiler can consume hundreds of independent cases."""
    while len(terms) > 1:
        pairs = [ExprIR(op, BOOL, (terms[i], terms[i + 1])) for i in range(0, len(terms) - 1, 2)]
        if len(terms) % 2:
            pairs.append(terms[-1])
        terms = pairs
    return terms[0]


def extend_predicate(name: str, params: dict[str, Type], cases: list[tuple],
                     pre: ExprIR | None, post: ExprIR | None, fallback: ExprIR) -> ExprIR:
    scalars = {bool: BOOL, int: INT, float: FLOAT, str: TEXT}
    seen = set()
    for values in cases:
        if len(values) != len(params):
            raise BError("E_ARITY", f"also {name} expects {len(params)} literals, got {len(values)}")
        for (param, typ), value in zip(params.items(), values):
            if scalars.get(type(value)) != typ:
                raise BError("E_TYPE", f"also {name}: {param} requires an exact scalar literal of type {typ}")
            if type(value) is float and not math.isfinite(value):
                raise BError("E_TYPE", f"also {name}: {param} requires a finite Float")
        if values in seen:
            raise BError("E_ALSO", f"Duplicate also case for {name}{values!r}")
        seen.add(values)
        env = dict(zip(params, values))
        if pre is not None and constant(pre, env) is not True:
            raise BError("E_ALSO", f"Cannot establish requires for also {name}{values!r}")
        if post is not None and constant(post, {**env, "result": True}) is not True:
            raise BError("E_ALSO", f"Cannot establish ensures for also {name}{values!r} returning true")

    yes = ExprIR("literal", BOOL, data=True)
    matches = []
    # Every tuple has the same exact signature. Sorting gives the same BIR
    # for the same set of facts whatever the order of the declarations.
    for values in sorted(seen):
        tests = [ExprIR("cmp", BOOL, (ExprIR("name", typ, data=param),
                                      ExprIR("literal", typ, data=value)), data="==")
                 for (param, typ), value in zip(params.items(), values)]
        matches.append(_combine("and", tests) if tests else yes)
    return ExprIR("conditional", BOOL, (_combine("or", matches), yes, fallback))
