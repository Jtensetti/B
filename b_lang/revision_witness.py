"""Compare closed native scalar functions without executing generated code.

With equality as the only observation of Text or Int, a permutation of values
which fixes program literals commutes with evaluation. For n arguments of a
type, the literals plus n distinct fresh values represent every equality
pattern, including equality between arguments. When an operation can observe
more than equality we can still find witnesses, but samples give no proof.
"""
from __future__ import annotations

import itertools
import operator
from collections.abc import Iterable
from dataclasses import dataclass, field

from .ir import ExprIR, ProgramIR, StmtIR
from .types import BOOL, INT, TEXT, Type

_SCALARS = {BOOL: bool, INT: int, TEXT: str}
_INT_OPS = {"add": operator.add, "sub": operator.sub, "mul": operator.mul}
_COMPARE = {"==": operator.eq, "!=": operator.ne, "<": operator.lt,
            "<=": operator.le, ">": operator.gt, ">=": operator.ge}
_MAX_CASES = 4096
_MAX_WORK = 200_000
_MAX_NODES = 4096
_MAX_INT_BITS = 4096


class _Outside(ValueError):
    pass


@dataclass
class _Domain:
    literals: dict[Type, set] = field(default_factory=lambda: {INT: set(), TEXT: set()})
    ordered_or_computed: set[Type] = field(default_factory=set)


@dataclass
class _Budget:
    remaining: int

    def spend(self):
        self.remaining -= 1
        if self.remaining < 0:
            raise _Outside("scalar comparison work limit reached")


def _exact(value, typ: Type) -> bool:
    return type(value) is _SCALARS.get(typ)


class _Fragment:
    def __init__(self, program: ProgramIR, domain: _Domain):
        self.functions = {fn.name: fn for fn in program.statements if fn.op == "fn"}
        self.domain = domain
        self.checked: set[str] = set()
        self.scan_budget = _Budget(_MAX_NODES)

    def check(self, name: str, visiting: frozenset[str] = frozenset()) -> StmtIR:
        fn = self.functions.get(name)
        if (fn is None or fn.typ not in _SCALARS or fn.expr is None or fn.effects or fn.backend
                or fn.requires is not None or fn.ensures is not None
                or any(t not in _SCALARS for _, t in fn.params)):
            raise _Outside(f"{name} needs a closed scalar function without contracts or effects")
        if name in visiting:
            raise _Outside(f"recursive call to {name}")
        if name not in self.checked:
            self._check_expr(fn.expr, dict(fn.params), visiting | {name})
            self.checked.add(name)
        return fn

    def _check_expr(self, node: ExprIR, params: dict[str, Type], visiting: frozenset[str]):
        self.scan_budget.spend()
        op, args, typ = node.op, node.operands, node.typ
        if node.foreign_path or typ not in _SCALARS:
            raise _Outside("foreign or non-scalar expression")
        if op == "literal" and _exact(node.data, typ):
            if typ in self.domain.literals:
                self.domain.literals[typ].add(node.data)
        elif op == "name" and params.get(node.data) == typ:
            pass
        elif op == "call" and args and args[0].op == "name" and not args[0].foreign_path:
            self.check(args[0].data, visiting)
            args = args[1:]
        elif op == "guard" and args[0].typ == typ:
            pass
        elif op == "cmp" and node.data in _COMPARE and args[0].typ == args[1].typ:
            if node.data not in ("==", "!="):
                self.domain.ordered_or_computed.add(args[0].typ)
        elif (op in _INT_OPS or op == "neg") and typ == INT:
            self.domain.ordered_or_computed.add(INT)
        elif op not in ("conditional", "and", "or", "not"):
            raise _Outside(f"{op} outside scalar comparison")
        for arg in args:
            self._check_expr(arg, params, visiting)

    def evaluate(self, name: str, arguments: tuple, budget: _Budget):
        fn = self.functions[name]
        if (len(arguments) != len(fn.params)
                or any(not _exact(x, t) for x, (_, t) in zip(arguments, fn.params))):
            raise _Outside("argument types outside scalar comparison")
        return self._value(fn.expr, dict(zip((n for n, _ in fn.params), arguments)), budget)

    def _value(self, node: ExprIR, env: dict, budget: _Budget):
        budget.spend()
        op, args = node.op, node.operands

        def at(i):
            return self._value(args[i], env, budget)

        if op == "literal":
            return node.data
        if op == "name":
            return env[node.data]
        if op == "guard":
            return at(0)
        if op == "call":
            values = tuple(self._value(arg, env, budget) for arg in args[1:])
            return self.evaluate(args[0].data, values, budget)
        if op == "conditional":
            return at(1) if at(0) else at(2)
        if op == "and":
            return at(0) and at(1)
        if op == "or":
            return at(0) or at(1)
        if op == "not":
            return not at(0)
        if op == "cmp":
            return _COMPARE[node.data](at(0), at(1))
        value = -at(0) if op == "neg" else _INT_OPS[op](at(0), at(1))
        if value.bit_length() > _MAX_INT_BITS:
            raise _Outside("integer comparison work limit reached")
        return value


def evaluate_scalar(program: ProgramIR, name: str, arguments: tuple) -> tuple[bool, object]:
    """Evaluate a fixed native scalar call. Unsupported cases yield (False, None)."""
    try:
        fragment = _Fragment(program, _Domain())
        fragment.check(name)
        return True, fragment.evaluate(name, arguments, _Budget(_MAX_WORK))
    except (_Outside, RecursionError):
        return False, None


def evaluate_rule(program: ProgramIR, name: str, arguments: tuple) -> bool | None:
    """Return a concrete Bool on an exact native input, or None if unsupported."""
    known, value = evaluate_scalar(program, name, arguments)
    return value if known and type(value) is bool else None


def _representatives(typ: Type, arity: int, domain: _Domain) -> tuple:
    if typ == BOOL:
        return (False, True)
    constants = domain.literals[typ]
    if typ == INT and typ in domain.ordered_or_computed:
        # Include boundary neighbors in a search for concrete differences.
        # A successful search is evidence on one input; exhausting it proves nothing.
        seeds = {0, 1, -1, 2, -2, *constants}
        return tuple(sorted(seeds | {n + off for n in constants for off in (-1, 1)},
                            key=lambda n: (abs(n), n)))
    values = sorted(constants)
    fresh = (i if typ == INT else f"_other_{i}" for i in itertools.count())
    values.extend(itertools.islice((value for value in fresh if value not in constants), arity))
    return tuple(values)


def compare_functions(expected: ProgramIR, candidate: ProgramIR, names: Iterable[str]) -> dict:
    """Compare the named functions over well-typed inputs, respecting proof and search budgets."""
    cases = 0
    work = _Budget(_MAX_WORK)
    incomplete = []
    for name in names:
        try:
            domain = _Domain()
            left, right = _Fragment(expected, domain), _Fragment(candidate, domain)
            fn = left.check(name)
            other = right.check(name)
            types = tuple(t for _, t in fn.params)
            if types != tuple(t for _, t in other.params) or fn.typ != other.typ:
                raise _Outside("function signature differs")
            values = {t: _representatives(t, types.count(t), domain) for t in set(types)}
            for args in itertools.product(*(values[t] for t in types)):
                if cases >= _MAX_CASES:
                    raise _Outside("representative tuple limit reached")
                cases += 1
                expected_value = left.evaluate(name, args, work)
                actual_value = right.evaluate(name, args, work)
                if type(expected_value) is not type(actual_value) or expected_value != actual_value:
                    return {"status": "counterexample", "function": name,
                            "arguments": dict(zip((n for n, _ in fn.params), args)),
                            "expected": expected_value, "actual": actual_value,
                            "cases": cases, "method": "native-scalar-evaluation"}
            if (set(types) - {BOOL}) & domain.ordered_or_computed:
                raise _Outside("unbounded input observed by arithmetic or ordering")
        except (_Outside, RecursionError) as exc:
            incomplete.append(f"{name}: {exc}")
            if cases >= _MAX_CASES or work.remaining <= 0:
                break
    if incomplete:
        return {"status": "unknown", "reason": "; ".join(incomplete), "cases": cases,
                "method": "native-scalar-evaluation"}
    return {"status": "proved", "cases": cases, "method": "exhaustive-scalar-classes"}
