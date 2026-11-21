"""The finite fragment of conditional result bounds recognized in B contracts."""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import Interval, int_comparison, narrow
from .ir import ExprIR, StmtIR
from .types import INT

MAX_CONDITIONAL_GUARANTEES = 8


@dataclass(frozen=True)
class ConditionalGuarantee:
    # The declared clause is "guard or conclusion". The bound becomes available
    # only when the guard is false, after the entire contract has been proved.
    guard: ExprIR
    conclusion: ExprIR
    parameter: str
    bound: Interval


@dataclass(frozen=True)
class Contract:
    # Conjuncts must all be proved before the function can publish anything.
    clauses: tuple[tuple[ExprIR, ConditionalGuarantee | None], ...]
    rules: tuple[ConditionalGuarantee, ...]


def _rule(clause: ExprIR, parameters: set[str]) -> ConditionalGuarantee | None:
    if clause.op != "or":
        return None
    guard, conclusion = clause.operands
    condition, result = int_comparison(guard), int_comparison(conclusion)
    if condition is None or condition[0] not in parameters or result is None or result[0] != "result":
        return None
    published = {"result": Interval()}
    narrow(conclusion, published)
    if published["result"] == Interval():  # e.g. result != 3 is not an interval
        return None
    return ConditionalGuarantee(guard, conclusion, condition[0], published["result"])


def read_contract(fn: StmtIR) -> Contract | None:
    if fn.ensures is None or fn.typ != INT:
        return None
    parameters = {name for name, typ in fn.params if typ == INT}
    clauses, rules = [], []
    pending = [fn.ensures]
    while pending:
        clause = pending.pop()
        if clause.op == "and":
            pending.extend(reversed(clause.operands))
            continue
        rule = _rule(clause, parameters)
        if rule is not None:
            rules.append(rule)
            if len(rules) > MAX_CONDITIONAL_GUARANTEES:
                return None
        clauses.append((clause, rule))
    return Contract(tuple(clauses), tuple(rules)) if rules else None
