"""Compare an extended rule's new case with a case the rule already covered.

`also free_entry(true, "sun") like (true, "sat")` says that, after the change,
a Sunday child must be indistinguishable from a Saturday child. B compares every
pure native scalar function that shares a parameter name with the rule. A
shared name denotes the same input; other parameters receive the same value on
both sides. Without `like`, `b ask` searches for the nearest case the rule
already covered, reports where the two cases still differ and turns the
difference into one concrete question.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field, replace

from .ir import ExprIR, ProgramIR, StmtIR
from .revision_witness import _Domain, _Fragment, _Outside, _representatives, evaluate_scalar
from .types import BOOL, FLOAT, INT, TEXT, BError

_SCALAR_TYPES = {bool: BOOL, int: INT, float: FLOAT, str: TEXT}
_MAX_GRID = 4096
_MAX_EXTRA = 64


def literal(value) -> str:
    """Render a scalar exactly as B source."""
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False)
    return repr(value)


def call_text(name: str, values: tuple) -> str:
    return f"{name}({', '.join(literal(v) for v in values)})"


def _functions(program: ProgramIR) -> dict[str, StmtIR]:
    return {s.name: s for s in program.statements if s.op == "fn"}


def with_body(program: ProgramIR, name: str, expr: ExprIR) -> ProgramIR:
    return replace(program, statements=tuple(
        replace(s, expr=expr) if s.op == "fn" and s.name == name else s for s in program.statements))


def _domain(program: ProgramIR) -> _Domain:
    fragment = _Fragment(program, _Domain())
    for name in _functions(program):
        try:
            fragment.check(name)
        except (_Outside, RecursionError):
            pass
    return fragment.domain


def _callees(node: ExprIR, found: set[str]) -> set[str]:
    if node.op == "call" and node.operands and node.operands[0].op == "name":
        found.add(node.operands[0].data)
    for child in node.operands:
        _callees(child, found)
    return found


def _names(node: ExprIR, found: set[str]) -> set[str]:
    if node.op == "name":
        found.add(node.data)
    for child in node.operands:
        _names(child, found)
    return found


def _reaches(functions: dict[str, StmtIR], start: str, target: str) -> bool:
    seen, pending = set(), [start]
    while pending:
        name = pending.pop()
        if name == target:
            return True
        if name in seen or name not in functions or functions[name].expr is None:
            continue
        seen.add(name)
        pending.extend(_callees(functions[name].expr, set()))
    return False


@dataclass
class Observation:
    function: str
    new_arguments: dict
    precedent_arguments: dict
    new_value: object
    precedent_value: object

    def to_dict(self):
        return {"function": self.function, "arguments": self.new_arguments,
                "precedent_arguments": self.precedent_arguments,
                "value": self.new_value, "precedent_value": self.precedent_value}


@dataclass
class Comparison:
    differences: list[Observation] = field(default_factory=list)
    same: list[str] = field(default_factory=list)
    uncompared: list[tuple[str, str]] = field(default_factory=list)
    sampled: list[str] = field(default_factory=list)


def _bindings(fn: StmtIR, rule: dict, domain: _Domain):
    """Yield argument tuples that place the rule's inputs by parameter name."""
    extras = [(n, t) for n, t in fn.params if n not in rule]
    pools = [_representatives(t, sum(1 for _, x in extras if x == t), domain) if t in (BOOL, INT, TEXT)
             else None for _, t in extras]
    if any(p is None for p in pools):
        raise _Outside("an additional parameter has a type outside scalar comparison")
    for chosen in itertools.islice(itertools.product(*pools), _MAX_EXTRA):
        yield dict(zip((n for n, _ in extras), chosen))


def compare(program: ProgramIR, target: str, new: tuple, precedent: tuple) -> Comparison:
    """Compare every function that shares an input name with `target` at two rule inputs."""
    functions = _functions(program)
    rule = dict(functions[target].params)
    names = list(rule)
    new_env, old_env = dict(zip(names, new)), dict(zip(names, precedent))
    domain = _domain(program)
    report = Comparison()
    for name, fn in functions.items():
        if name == target or not fn.declared_pure:
            continue
        shared = [(n, t) for n, t in fn.params if n in rule]
        if not shared:
            continue
        if any(rule[n] != t for n, t in shared):
            report.uncompared.append((name, "a shared parameter name has a different type"))
            continue
        varying = {n for n, _ in shared if new_env[n] != old_env[n] or type(new_env[n]) is not type(old_env[n])}
        if not varying:
            continue
        if not (_names(fn.expr, set()) & varying):
            report.same.append(name)  # the differing inputs never reach this body
            continue
        try:
            difference = None
            extras = [t for n, t in fn.params if n not in rule]
            for extra in _bindings(fn, rule, domain):
                left = tuple(extra.get(n, new_env.get(n)) for n, _ in fn.params)
                right = tuple(extra.get(n, old_env.get(n)) for n, _ in fn.params)
                known_left, value_left = evaluate_scalar(program, name, left)
                known_right, value_right = evaluate_scalar(program, name, right)
                if not (known_left and known_right):
                    raise _Outside("needs a closed scalar function without contracts or effects")
                if type(value_left) is not type(value_right) or value_left != value_right:
                    params = [n for n, _ in fn.params]
                    difference = Observation(name, dict(zip(params, left)), dict(zip(params, right)),
                                             value_left, value_right)
                    break
            if difference:
                report.differences.append(difference)
            else:
                report.same.append(name)
                if set(extras) & domain.ordered_or_computed:
                    report.sampled.append(name)
        except _Outside as exc:
            report.uncompared.append((name, str(exc)))
    return report


def causes(program: ProgramIR, differences: list[Observation]) -> list[str]:
    """Differing functions whose difference is not explained by a differing callee."""
    functions = _functions(program)
    differing = {d.function for d in differences}
    return [name for name in differing_order(differences)
            if not (_callees(functions[name].expr, set()) & differing)]


def differing_order(differences: list[Observation]) -> list[str]:
    return [d.function for d in differences]


def outcomes(program: ProgramIR, differences: list[Observation]) -> list[str]:
    """Differing functions that no other differing function calls."""
    functions = _functions(program)
    differing = {d.function for d in differences}
    called = set().union(*(_callees(functions[n].expr, set()) for n in differing)) if differing else set()
    return [d.function for d in differences if d.function not in called]


def _same_tree(left: ExprIR, right: ExprIR) -> bool:
    while left.op == "guard":
        left = left.operands[0]
    while right.op == "guard":
        right = right.operands[0]
    return (left.op, left.typ, left.data, left.foreign_path, len(left.operands)) == \
        (right.op, right.typ, right.data, right.foreign_path, len(right.operands)) and \
        all(_same_tree(a, b) for a, b in zip(left.operands, right.operands))


def repeats_rule(fn: StmtIR, rule_body: ExprIR, rule_params: tuple) -> bool:
    """True when `fn` contains the rule's own condition over the same named inputs."""
    if not {n for n, _ in rule_params} <= {n for n, _ in fn.params}:
        return False
    if dict(rule_params) != {n: t for n, t in fn.params if n in dict(rule_params)}:
        return False

    def visit(node: ExprIR) -> bool:
        return _same_tree(node, rule_body) or any(visit(child) for child in node.operands)

    return visit(fn.expr)


def precedents(original: ProgramIR, target: str, new: tuple) -> list[tuple]:
    """Inputs on which the unextended rule was already true, nearest first."""
    fn = _functions(original)[target]
    domain = _domain(original)
    pools = []
    for (name, typ), value in zip(fn.params, new):
        if typ == BOOL:
            pool = [False, True]
        elif typ in (INT, TEXT):
            pool = [v for v in _representatives(typ, 0, domain)]
        else:
            return []
        if value not in pool:
            pool.append(value)
        pools.append(pool)
    found = []
    for count, candidate in enumerate(itertools.product(*pools)):
        if count >= _MAX_GRID:
            break
        if candidate == new:
            continue
        known, value = evaluate_scalar(original, target, candidate)
        if known and value is True:
            found.append(candidate)
    distance = lambda c: sum(1 for a, b in zip(c, new) if a != b or type(a) is not type(b))
    found.sort(key=distance)
    return [c for c in found if distance(c) == distance(found[0])] if found else []


def check_types(target: str, params: tuple, values: tuple, label: str) -> None:
    if len(values) != len(params):
        raise BError("E_ARITY", f"{label} {target} expects {len(params)} literals, got {len(values)}")
    for (param, typ), value in zip(params, values):
        if _SCALAR_TYPES.get(type(value)) != typ:
            raise BError("E_TYPE", f"{label} {target}: {param} requires an exact scalar literal of type {typ}")


def validate_likeness(program: ProgramIR, originals: dict[str, ExprIR], declarations) -> list[tuple[str, str]]:
    """Reject `like` declarations whose new case is distinguishable from the precedent."""
    warnings = []
    functions = _functions(program)
    for declaration in declarations:
        target, new, _, precedent = declaration.parts
        if precedent is None:
            continue
        fn = functions[target]
        check_types(target, fn.params, precedent, "like")
        if precedent == new and all(type(a) is type(b) for a, b in zip(precedent, new)):
            raise BError("E_LIKE", f"also {call_text(target, new)} cannot be like itself")
        original = with_body(program, target, originals[target])
        known, value = evaluate_scalar(original, target, precedent)
        if not known:
            raise BError("E_LIKE", f"Cannot evaluate {call_text(target, precedent)} before the change")
        if value is not True:
            raise BError("E_LIKE", f"like needs a case {target} already covered; "
                         f"{call_text(target, precedent)} was {literal(value)}")
        report = compare(program, target, new, precedent)
        if report.differences:
            shown = outcomes(program, report.differences)[0]
            first = next(d for d in report.differences if d.function == shown)
            root = [n for n in causes(program, report.differences) if n != shown]
            raise BError("E_LIKE", f"also {call_text(target, new)} like ({', '.join(literal(v) for v in precedent)}): "
                         f"{call_text(first.function, tuple(first.new_arguments.values()))} = {literal(first.new_value)}, "
                         f"but {call_text(first.function, tuple(first.precedent_arguments.values()))} = "
                         f"{literal(first.precedent_value)}" + (f"; the difference starts in {', '.join(root)}" if root else ""))
        for name, reason in report.uncompared:
            warnings.append(("W_LIKE_UNCOMPARED", f"like for {target} did not compare {name}: {reason}"))
        for name in report.sampled:
            warnings.append(("W_LIKE_SAMPLED", f"like for {target} compared {name} on sampled values of an "
                             "arithmetic or ordered parameter"))
    return warnings
