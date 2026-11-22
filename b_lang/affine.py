"""Exact affine identities over checked B Int operations, on normal return.

Modular verification substitutes established, declared summaries at native calls.
Discover mode may additionally inspect native callee bodies. Neither mode runs
B code, samples inputs, or treats unchecked postconditions as axioms.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .contracts import Interval, arithmetic_interval, compare_intervals, narrow
from .ir import ExprIR, StmtIR
from .types import BError, BOOL, INT

MAX_CALL_DEPTH = 16
MAX_NODES = 4096
MAX_TERMS = 64
MAX_BITS = 4096
MAX_EXPRESSION_DEPTH = 96


class _Unsupported(ValueError):
    """Outside the supported fragment or budget. No proof can be returned."""


@dataclass(frozen=True)
class Form:
    terms: tuple[tuple[str, int], ...] = ()
    constant: int = 0

    def __post_init__(self):
        combined = {}
        for name, coefficient in self.terms:
            if type(name) is not str or type(coefficient) is not int:
                raise _Unsupported("Expected named integer coefficients")
            combined[name] = combined.get(name, 0) + coefficient
        terms = tuple(sorted((n, c) for n, c in combined.items() if c))
        if len(terms) > MAX_TERMS or type(self.constant) is not int or self.constant.bit_length() > MAX_BITS:
            raise _Unsupported("Affine form exceeds the supported size")
        if any(c.bit_length() > MAX_BITS for _, c in terms):
            raise _Unsupported("Affine coefficient exceeds the supported size")
        object.__setattr__(self, "terms", terms)

    def scaled(self, scalar: int) -> Form:
        return Form(tuple((n, c * scalar) for n, c in self.terms), self.constant * scalar)

    def plus(self, other: Form) -> Form:
        return Form(self.terms + other.terms, self.constant + other.constant)

    def render(self) -> str:
        pieces = []
        for name, coefficient in (*self.terms, ("", self.constant)):
            if not coefficient:
                continue
            size = abs(coefficient)
            term = (name if size == 1 else f"{size} * {name}") if name else str(size)
            sign = (" - " if coefficient < 0 else " + ") if pieces else ("-" if coefficient < 0 else "")
            pieces.append(sign + term)
        return "".join(pieces) or "0"

    def to_dict(self) -> dict:
        return {"coefficients": dict(self.terms), "constant": self.constant}


@dataclass(frozen=True)
class Evidence:
    form: Form
    contract_dependencies: tuple[str, ...]
    body_dependencies: tuple[str, ...]


@dataclass(frozen=True)
class _Value:
    form: Form
    interval: Interval

    def __post_init__(self):
        if any(k is not None and k.bit_length() > MAX_BITS for k in (self.interval.lo, self.interval.hi)):
            raise _Unsupported("Affine interval exceeds the supported size")

    @classmethod
    def literal(cls, x: int) -> _Value:
        return cls(Form(constant=x), Interval(x, x))

    def plus(self, other: _Value) -> _Value:
        form = self.form.plus(other.form)
        if not form.terms:
            return self.literal(form.constant)
        return _Value(form, arithmetic_interval("add", self.interval, other.interval))

    def scaled(self, scalar: int) -> _Value:
        if not scalar:
            return self.literal(0)
        lo, hi = self.interval.lo, self.interval.hi
        if scalar < 0:
            lo, hi = hi, lo
        bounded = Interval(None if lo is None else lo * scalar, None if hi is None else hi * scalar,
                           self.interval.nonzero)
        return _Value(self.form.scaled(scalar), bounded)


def _symbol(name: str) -> _Value:
    return _Value(Form(((name, 1),)), Interval())


def _eligible(fn: StmtIR) -> bool:
    return (fn.op == "fn" and fn.backend is None and not fn.effects and fn.typ == INT
            and fn.expr is not None and len(fn.params) <= MAX_TERMS and all(t == INT for _, t in fn.params))


class _Interpreter:
    def __init__(self, functions: Mapping[str, StmtIR], summaries: Mapping[str, Form], expand: bool):
        self.functions = functions
        self.summaries = summaries
        self.expand = expand
        self.remaining = MAX_NODES
        self.contracts_used: set[str] = set()
        self.bodies_used: set[str] = set()

    def visit(self, depth: int) -> None:
        self.remaining -= 1
        if self.remaining < 0 or depth > MAX_EXPRESSION_DEPTH:
            raise _Unsupported("Affine analysis budget exhausted")

    def number(self, node: ExprIR, env: dict[str, _Value], trail: tuple[str, ...], depth: int) -> _Value:
        self.visit(depth)
        if node.typ != INT or node.foreign_path:
            raise _Unsupported("Expected a native exact Int")
        op, args = node.op, node.operands
        if op == "name" and node.data in env:
            return env[node.data]
        if op == "literal" and type(node.data) is int:
            return _Value.literal(node.data)
        if op in ("neg", "guard"):
            value = self.number(args[0], env, trail, depth + 1)
            return value.scaled(-1) if op == "neg" else value
        if op in ("add", "sub", "mul"):
            left, right = (self.number(a, env, trail, depth + 1) for a in args)
            if op == "add":
                return left.plus(right)
            if op == "sub":
                return left.plus(right.scaled(-1))
            if not left.form.terms:
                return right.scaled(left.form.constant)
            if not right.form.terms:
                return left.scaled(right.form.constant)
            raise _Unsupported("Product of two variable expressions")
        if op == "call":
            return self.call(node, env, trail, depth)
        if op == "conditional":
            condition, yes, no = args
            decision = self.predicate(condition, env, trail, depth + 1)
            branches = []
            for when, child in ((True, yes), (False, no)):
                if decision is not None and when != decision:
                    continue
                branch = self.refined(condition, env, when)
                if branch is not None:
                    branches.append(self.number(child, branch, trail, depth + 1))
            if len(branches) == 1:
                return branches[0]
            if len(branches) == 2 and branches[0].form == branches[1].form:
                a, b = branches[0].interval, branches[1].interval
                lo = min(a.lo, b.lo) if a.lo is not None and b.lo is not None else None
                hi = max(a.hi, b.hi) if a.hi is not None and b.hi is not None else None
                return _Value(branches[0].form, Interval(lo, hi, a.nonzero and b.nonzero))
        raise _Unsupported("Unsupported affine expression")

    def refined(self, test: ExprIR, env: dict[str, _Value], when: bool) -> dict[str, _Value] | None:
        bounds = {name: value.interval for name, value in env.items()}
        pending = [(test, when, 0)]
        try:
            while pending:
                node, applies, depth = pending.pop()
                self.visit(depth)
                if node.op == "not":
                    pending.append((node.operands[0], not applies, depth + 1))
                elif (applies and node.op == "and") or (not applies and node.op == "or"):
                    pending.extend((arg, applies, depth + 1) for arg in node.operands)
                elif node.op == "cmp":
                    narrow(node, bounds, applies)
        except BError as exc:
            if exc.code != "E_PRECONDITION_EMPTY":
                raise
            return None
        return {name: _Value(value.form, bounds[name]) for name, value in env.items()}

    def predicate(self, node: ExprIR, env: dict[str, _Value], trail: tuple[str, ...], depth: int) -> bool | None:
        self.visit(depth)
        if node.typ != BOOL:
            raise _Unsupported("Expected Bool predicate")
        op, args = node.op, node.operands
        if op == "literal" and type(node.data) is bool:
            return node.data
        if op == "not":
            value = self.predicate(args[0], env, trail, depth + 1)
            return None if value is None else not value
        if op in ("and", "or"):
            left = self.predicate(args[0], env, trail, depth + 1)
            proceed = op == "and"
            if left is not None and left != proceed:
                return left
            right_env = self.refined(args[0], env, proceed)
            if right_env is None:
                return not proceed
            right = self.predicate(args[1], right_env, trail, depth + 1)
            return right if left is not None or right == (not proceed) else None
        if op == "cmp":
            left, right = (self.number(a, env, trail, depth + 1) for a in args)
            ordinary = compare_intervals(node.data, left.interval, right.interval)
            if ordinary is not None:
                return ordinary
            diff = left.plus(right.scaled(-1))
            return compare_intervals(node.data, diff.interval, Interval(0, 0))
        raise _Unsupported("Unsupported affine predicate")

    def call(self, node: ExprIR, env: dict[str, _Value], trail: tuple[str, ...], depth: int) -> _Value:
        target, *args = node.operands
        if target.op != "name" or target.typ.name != "Function":
            raise _Unsupported("Expected a direct named native call")
        name = target.data
        fn = self.functions.get(name)
        if fn is None or not _eligible(fn) or name in trail or len(args) != len(fn.params):
            raise _Unsupported("Opaque or recursive callee")
        actuals = {param: self.number(arg, env, trail, depth + 1) for (param, _), arg in zip(fn.params, args)}
        nested = (*trail, name)
        if fn.requires is not None and self.predicate(fn.requires, actuals, nested, depth + 1) is not True:
            raise _Unsupported("Callee precondition not established")
        if name in self.summaries:
            self.contracts_used.add(name)
            summary = self.summaries[name]
            value = _Value.literal(summary.constant)
            for param, coefficient in summary.terms:
                if param not in actuals:
                    raise _Unsupported("Summary parameter mismatch")
                value = value.plus(actuals[param].scaled(coefficient))
            return value
        if self.expand and len(trail) <= MAX_CALL_DEPTH:
            self.bodies_used.add(name)
            return self.number(fn.expr, actuals, nested, depth + 1)
        raise _Unsupported("No established affine summary")


def declared(clause: ExprIR | None, parameters: Iterable[str]) -> Form | None:
    """Solve an explicit integer equality for result, when the quotient is affine."""
    if clause is None or clause.op != "cmp" or clause.data != "==":
        return None
    names = set(parameters) | {"result"}
    if len(names) > MAX_TERMS + 1:
        return None
    checker = _Interpreter({}, {}, False)
    env = {name: _symbol(name) for name in names}
    try:
        left, right = (checker.number(arg, env, (), 0) for arg in clause.operands)
        difference = left.form.plus(right.form.scaled(-1))
        coefficients = dict(difference.terms)
        divisor = coefficients.pop("result", 0)
        if not divisor or difference.constant % divisor or any(c % divisor for c in coefficients.values()):
            return None
        return Form(tuple((name, -c // divisor) for name, c in coefficients.items()),
                    -difference.constant // divisor)
    except _Unsupported:
        return None


def implementation(fn: StmtIR, functions: Mapping[str, StmtIR], summaries: Mapping[str, Form],
                   *, expand_bodies: bool = False) -> Evidence | None:
    """Return this body's exact parametric value, or None if no proof was found.

    The caller supplies only independently certified whole-contract summaries.
    The entry contract restricts the public input domain. Every native call
    still has to meet its own requires clause before substitution or expansion.
    Expanded callees need no declared equality: their bodies become evidence
    tied to this revision. Runtime postconditions are never assumed as facts.
    """
    if not _eligible(fn):
        return None
    checker = _Interpreter(functions, summaries, expand_bodies)
    env = {param: _symbol(param) for param, _ in fn.params}
    trail = (fn.name,)
    try:
        if fn.requires is not None:
            if checker.predicate(fn.requires, env, trail, 0) is False:
                return None
            env = checker.refined(fn.requires, env, True)
            if env is None:
                return None
        result = checker.number(fn.expr, env, trail, 0)
        return Evidence(result.form, tuple(sorted(checker.contracts_used)), tuple(sorted(checker.bodies_used)))
    except _Unsupported:
        return None
