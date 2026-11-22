"""Check obligations on typed BIR, using independently established native contracts.

Facts apply when the site is reached and its operands return normally. A call
exposes only the bounds in its declared, proved ensures clause. Its body's
stronger accidental properties and foreign signatures are never exported.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json

from . import affine
from .contracts import Interval, arithmetic_interval, compare_intervals, constant, narrow, truth
from .ir import ExprIR, ProgramIR, StmtIR
from .relations import Contract, read_contract
from .types import BError, BOOL, INT


@dataclass(frozen=True)
class Obligation:
    caller: str
    site: str
    kind: str
    target: str
    status: str
    requirement: str
    dependencies: tuple[str, ...]
    expression: str | None = None
    proof_method: str | None = None

    def to_dict(self) -> dict:
        return {key: value for key, value in {**vars(self), "dependencies": list(self.dependencies)}.items()
                if value is not None}

    def describe(self) -> str:
        context = f" (depends on {', '.join(self.dependencies)})" if self.dependencies else ""
        return f"{self.caller} at {self.site}: {self.target} {self.kind} {self.requirement}: {self.status}{context}"


@dataclass(frozen=True)
class Analysis:
    obligations: tuple[Obligation, ...]

    def to_dict(self) -> dict:
        return {"schema": "b-contract-analysis", "version": 1,
                "obligations": [item.to_dict() for item in self.obligations]}


@dataclass(frozen=True)
class Fact:
    interval: Interval | None = None
    boolean: bool | None = None
    sources: frozenset[str] = frozenset()
    conditional: bool = False


@dataclass(frozen=True)
class _Summary:
    interval: Interval
    conditional: bool


_UNKNOWN = Fact()


def _sources(facts) -> frozenset[str]:
    return frozenset().union(*(fact.sources for fact in facts))


def _bounds(env: dict[str, Fact]) -> dict[str, Interval]:
    return {name: f.interval for name, f in env.items() if f.interval is not None}


def _refine(test: ExprIR, env: dict[str, Fact], when: bool) -> dict[str, Fact] | None:
    bounds = _bounds(env)
    try:
        narrow(test, bounds, when)
    except BError as exc:
        if exc.code != "E_PRECONDITION_EMPTY":
            raise
        return None
    return {**env, **{name: replace(env[name], interval=value) for name, value in bounds.items()}}


def _join(left: Fact, right: Fact) -> Fact:
    a, b = left.interval, right.interval
    result = None
    if a is not None and b is not None:
        lo = min(a.lo, b.lo) if a.lo is not None and b.lo is not None else None
        hi = max(a.hi, b.hi) if a.hi is not None and b.hi is not None else None
        result = Interval(lo, hi, a.nonzero and b.nonzero)
    boolean = left.boolean if left.boolean == right.boolean else None
    return Fact(result, boolean, left.sources | right.sources, left.conditional or right.conditional)


def _contract_inputs(node: ExprIR, env: dict[str, Fact]):
    if node.op == "name":
        yield env.get(node.data, _UNKNOWN)
    for child in node.operands:
        yield from _contract_inputs(child, env)


_INFIX = {"add": "+", "sub": "-", "mul": "*", "div": "/", "mod": "%", "and": "and",
          "or": "or", "coalesce": "??"}


def _render(node: ExprIR) -> str:
    op, args = node.op, node.operands
    if op == "literal":
        return "none" if node.data is None else json.dumps(node.data, ensure_ascii=False)
    if op == "name":
        return node.data
    if op in _INFIX or op == "cmp":
        return f"({_render(args[0])} {_INFIX.get(op, node.data)} {_render(args[1])})"
    if op in ("neg", "not"):
        prefix = "-" if op == "neg" else "not "
        return f"{prefix}{_render(args[0])}"
    if op == "guard":
        return _render(args[0])
    if op == "call":
        return f"{_render(args[0])}({', '.join(_render(a) for a in args[1:])})"
    if op == "list":
        return "[" + ", ".join(_render(a) for a in args) + "]"
    if op == "dict":
        entries = (f"{_render(k)}: {_render(v)}" for k, v in zip(args[::2], args[1::2]))
        return "{" + ", ".join(entries) + "}"
    if op == "attr":
        return f"{_render(args[0])}.{node.data}"
    if op == "conditional":
        return f"(if {_render(args[0])} then {_render(args[1])} else {_render(args[2])})"
    return f"<{op}>"


def _conjuncts(node: ExprIR):
    pending = [node]
    while pending:
        part = pending.pop()
        if part.op == "and":
            pending.extend(reversed(part.operands))
        else:
            yield part


class _Pass:
    def __init__(self, functions: dict[str, StmtIR], summaries: dict[str, _Summary],
                 contracts: dict[str, Contract], exact_claims: dict[str, dict[int, affine.Form]],
                 exact_summaries: dict[str, affine.Form], *, collect: bool = True):
        self.functions = functions
        self.contracts = contracts
        self.exact_claims = exact_claims
        self.exact_summaries = exact_summaries
        self.collect = collect
        self.summaries = summaries
        self.obligations: list[Obligation] = []
        self.caller = "<module>"

    def record(self, site, kind, target, outcome, requirement, sources, expression=None, *, conditional=False, used_affine=False):
        status = "proved" if outcome is True else "refuted" if outcome is False else "unknown"
        method = None
        if outcome is True:
            if used_affine:
                method = "affine-equality"
            elif conditional:
                method = "conditional-guarantee"
        self.obligations.append(Obligation(self.caller, site, kind, target, status, requirement,
                                           tuple(sorted(sources)), expression, method))

    def call(self, node: ExprIR, args: list[Fact], site: str) -> Fact:
        target = node.operands[0]
        if node.foreign_path or target.op != "name" or target.typ.name != "Function":
            return _UNKNOWN
        function = self.functions.get(target.data)
        if function is None:
            return _UNKNOWN
        # A Float parameter observes rounded values even when its argument was Int.
        actuals = {name: fact if typ == INT else Fact(sources=fact.sources)
                   for (name, typ), fact in zip(function.params, args)}
        ok = True
        conditional = False
        sources = frozenset({function.name})
        if function.requires is not None:
            ok = True if node.precondition_proved else truth(function.requires, _bounds(actuals))
            inputs = tuple(_contract_inputs(function.requires, actuals))
            input_sources = _sources(inputs)
            conditional = any(f.conditional for f in inputs)
            if self.collect:
                self.record(site, "requires", function.name, ok, _render(function.requires), input_sources,
                            _render(node), conditional=conditional)
            sources |= input_sources
        # Keep the provider visible even if the declared guarantee no longer proves
        # the obligation. Sources describe dependencies, not a certificate by themselves.
        summary = self.summaries.get(function.name) if ok is True else None
        if summary is None:
            return Fact(sources=sources)
        interval = summary.interval
        conditional |= summary.conditional
        contract = self.contracts.get(function.name)
        if contract is not None:
            bounds = _bounds(actuals)
            for rule in contract.rules:
                if truth(rule.guard, bounds) is False:
                    narrowed = interval.intersect(rule.bound)
                    if (narrowed.lo, narrowed.hi, narrowed.nonzero) != (interval.lo, interval.hi, interval.nonzero):
                        conditional = True
                        sources |= actuals[rule.parameter].sources
                    interval = narrowed
        return Fact(interval, sources=sources, conditional=conditional)

    def expr(self, node: ExprIR, env: dict[str, Fact], site: str) -> Fact:
        op, args = node.op, node.operands
        if op == "literal":
            if node.typ == INT:
                return Fact(Interval(node.data, node.data))
            if node.typ == BOOL:
                return Fact(boolean=node.data)
            return _UNKNOWN
        if op == "name":
            return env.get(node.data, _UNKNOWN)
        if op == "conditional":
            condition = self.expr(args[0], env, site + ".test")
            branches = []
            for when, child, suffix in ((True, args[1], ".then"), (False, args[2], ".else")):
                if condition.boolean is not None and condition.boolean != when:
                    continue
                branch_env = _refine(args[0], env, when)
                if branch_env is not None:
                    branches.append(self.expr(child, branch_env, site + suffix))
            if not branches:
                return _UNKNOWN
            value = branches[0] if len(branches) == 1 else _join(*branches)
            return replace(value, interval=value.interval if node.typ == INT else None,
                           sources=value.sources | condition.sources,
                           conditional=value.conditional or condition.conditional)
        if op in ("and", "or"):
            left = self.expr(args[0], env, site + ".0")
            evaluate_right = op == "and"
            if left.boolean == (not evaluate_right):
                return left
            right_env = _refine(args[0], env, evaluate_right)
            if right_env is None:
                return Fact(boolean=not evaluate_right, sources=left.sources, conditional=left.conditional)
            right = self.expr(args[1], right_env, site + ".1")
            known = right.boolean if left.boolean is not None else None
            return Fact(boolean=known, sources=left.sources | right.sources, conditional=left.conditional or right.conditional)
        if op == "guard":
            child = self.expr(args[0], env, site)
            if node.typ == args[0].typ:
                return child
            return Fact(sources=child.sources)
        children = [self.expr(child, env, f"{site}.{i}") for i, child in enumerate(args)]
        sources = _sources(children)
        conditional = any(f.conditional for f in children)
        if op == "call":
            return self.call(node, children[1:], site)
        if self.collect and op in ("div", "mod"):
            denominator = children[1].interval
            nonzero = compare_intervals("!=", denominator, Interval(0, 0))
            if nonzero is None:
                # Closed built-in scalar expressions have Python backend semantics.
                # The whitelist excludes calls and guards, including Float widening.
                value = constant(args[1], {})
                if type(value) in (float, int):
                    nonzero = value != 0
            self.record(site, "nonzero", op, nonzero, f"{_render(args[1])} != 0", children[1].sources,
                        conditional=children[1].conditional)
        if node.typ == INT and op in ("add", "sub", "mul", "neg"):
            interval = arithmetic_interval(op, *(child.interval for child in children))
            return Fact(interval, sources=sources, conditional=conditional)
        if op == "cmp":
            outcome = compare_intervals(node.data, children[0].interval, children[1].interval)
            return Fact(boolean=outcome, sources=sources, conditional=conditional)
        if op == "not":
            b = children[0].boolean
            return Fact(boolean=None if b is None else not b, sources=sources, conditional=conditional)
        return Fact(sources=sources)

    def clause_evidence(self, fn, env, result, contract, claims, actual):
        # Check every conjunct before publishing any part of a function's contract.
        evaluator = _Pass(self.functions, self.summaries, self.contracts, self.exact_claims,
                          self.exact_summaries, collect=False)
        bounds = _bounds({**env, "result": result})
        clauses = contract.clauses if contract else ((part, None) for part in _conjuncts(fn.ensures))
        sources = set()
        used_cases = used_affine = False
        for clause, rule in clauses:
            if truth(clause, bounds) is True:
                continue
            if actual is not None and claims.get(id(clause)) == actual.form:
                sources.update(actual.contract_dependencies)
                used_affine = True
                continue
            if rule is None:
                return None
            used_cases = True
            restricted = _refine(rule.guard, env, False)
            if restricted is None:
                continue
            case_result = evaluator.expr(fn.expr, restricted, "body")
            if truth(rule.conclusion, _bounds({**restricted, "result": case_result})) is not True:
                return None
            sources.update(case_result.sources)
        return sources, used_cases, used_affine

    def function(self, fn: StmtIR) -> None:
        # Prove bodies in a fresh parameter environment, including when callers
        # pass literals. A sample input must never certify a public postcondition.
        self.caller = fn.name
        env = {name: Fact(Interval()) for name, typ in fn.params if typ == INT}
        if fn.requires is not None:
            env = _refine(fn.requires, env, True)
            if env is None:
                # A contradictory entry condition supplies no evidence to export.
                if fn.ensures is not None:
                    self.record("ensures", "ensures", fn.name, None, _render(fn.ensures), ())
                return
        result = self.expr(fn.expr, env, "body")
        if fn.ensures is None:
            return
        post_env = {**env, "result": result}
        inputs = tuple(_contract_inputs(fn.ensures, post_env))
        conditional = any(f.conditional for f in inputs)
        sources = _sources(inputs)
        claims = self.exact_claims.get(fn.name, {})
        used_affine = False
        if fn.typ == INT:
            outcome = truth(fn.ensures, _bounds(post_env))
            contract = self.contracts.get(fn.name)
            if outcome is None and (contract or claims):
                actual = affine.implementation(fn, self.functions, self.exact_summaries) if claims else None
                evidence = self.clause_evidence(fn, env, result, contract, claims, actual)
                if evidence is not None:
                    extra_sources, used_cases, used_affine = evidence
                    outcome = True
                    conditional |= used_cases
                    sources |= extra_sources
        else:
            outcome = True if fn.ensures.op == "literal" and fn.ensures.data is True else None
        self.record("ensures", "ensures", fn.name, outcome, _render(fn.ensures), sources,
                    conditional=conditional, used_affine=used_affine)
        if outcome is True and claims and fn.name not in self.exact_summaries:
            self.exact_summaries[fn.name] = next(iter(claims.values()))
        if outcome is True and fn.typ == INT and fn.name not in self.summaries:
            published = {"result": Interval()}
            narrow(fn.ensures, published)
            self.summaries[fn.name] = _Summary(published["result"], conditional)


def analyze(program: ProgramIR, *, conditional_guarantees: bool = True,
            affine_guarantees: bool = True) -> Analysis:
    """Analyze unoptimized, type-checked BIR without executing the program."""
    functions = {s.name: s for s in program.statements if s.op == "fn"}
    contracts = {}
    if conditional_guarantees:
        for name, fn in functions.items():
            contract = read_contract(fn)
            if contract is not None:
                contracts[name] = contract
    exact_claims = {}
    if affine_guarantees:
        for name, fn in functions.items():
            if fn.typ != INT or fn.ensures is None:
                continue
            params = [param for param, typ in fn.params if typ == INT]
            claims = {id(part): form for part in _conjuncts(fn.ensures)
                      if (form := affine.declared(part, params)) is not None}
            if claims:
                exact_claims[name] = claims
    exact_summaries = {}
    summaries: dict[str, _Summary] = {}
    # Monotone fixed point: an export is the declared interval, independent of
    # caller or iteration. Each function can become certified at most once.
    while True:
        count = len(summaries) + len(exact_summaries)
        check = _Pass(functions, summaries, contracts, exact_claims, exact_summaries)
        for fn in functions.values():
            check.function(fn)
        if len(summaries) + len(exact_summaries) == count:
            break
    check.caller = "<module>"
    env = {}
    ordinals: dict[str, int] = {}
    for stmt in program.statements:
        if stmt.expr is None or stmt.op == "fn":
            continue
        ordinal = ordinals.get(stmt.op, 0)
        ordinals[stmt.op] = ordinal + 1
        site = f"let.{stmt.name}" if stmt.op == "let" else f"{stmt.op}.{ordinal}"
        fact = check.expr(stmt.expr, env, site)
        if stmt.op == "let":
            env[stmt.name] = fact
    return Analysis(tuple(check.obligations))
