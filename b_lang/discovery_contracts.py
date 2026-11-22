"""Generate tentative integer laws from bounded observations of checked native BIR."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations, islice, product
import operator

from .composition import _render
from .contracts import Interval, int_comparison, narrow
from .ir import ExprIR, ProgramIR, StmtIR
from .types import BError, BOOL, INT


MAX_PARAMS = 4
MAX_BITS = 128
MAX_STEPS = 512
MAX_DEPTH = 48
MAX_NODES = 1024
DISCOVERY_BUDGET = 8
CHALLENGE_BUDGET = 12

_BINARY = {"add": operator.add, "sub": operator.sub, "mul": operator.mul, "mod": operator.mod}
_COMPARE = {"==": operator.eq, "!=": operator.ne, "<": operator.lt, "<=": operator.le,
            ">": operator.gt, ">=": operator.ge}
_OPS = {"guard", "literal", "name", "call", "neg", "not", "and", "or", "cmp", "conditional", *_BINARY}


class Unsupported(ValueError):
    """The target or one of its transitive callees is outside the observation language."""


class ProbeFailure(ValueError):
    """An input could not produce an observable native result within the budget."""


def _check_int(value: int) -> int:
    if type(value) is not int or value.bit_length() > MAX_BITS:
        raise ProbeFailure(f"integer exceeds the {MAX_BITS}-bit observation domain")
    return value


class _Evaluator:
    def __init__(self, program: ProgramIR, target: str):
        self.functions = {s.name: s for s in program.statements if s.op == "fn"}
        self.target = target
        self.nodes = 0
        self.checked: set[str] = set()
        self.steps = 0
        self._check_function(target, (), 0)

    def _check_function(self, name: str, stack: tuple[str, ...], depth: int):
        if name in stack:
            raise Unsupported(f"recursive native call to {name}")
        if name in self.checked:
            return
        fn = self.functions.get(name)
        if fn is None:
            raise Unsupported(f"unknown native function {name}")
        if fn.effects or fn.typ != INT or len(fn.params) > MAX_PARAMS or any(t != INT for _, t in fn.params):
            raise Unsupported(f"{name} must be a closed native Int function with at most {MAX_PARAMS} Int parameters and no external effects")
        names = {n for n, _ in fn.params}
        active = (*stack, name)
        self._check_expr(fn.expr, names, active, depth)
        if fn.requires is not None:
            self._check_expr(fn.requires, names, active, depth)
        if fn.ensures is not None and name != self.target:
            self._check_expr(fn.ensures, names | {"result"}, active, depth)
        self.checked.add(name)

    def _check_expr(self, e: ExprIR, names: set[str], stack: tuple[str, ...], depth: int):
        self.nodes += 1
        if self.nodes > MAX_NODES or depth > MAX_DEPTH:
            raise Unsupported("observation expression or call graph is too large")
        if e.typ not in (INT, BOOL) or e.op not in _OPS or e.foreign_path is not None:
            raise Unsupported(f"unsupported observation operation {e.op} ({e.typ})")
        if e.op == "literal" and type(e.data) is int and e.data.bit_length() > MAX_BITS:
            raise Unsupported(f"integer literal exceeds {MAX_BITS} bits")
        if e.op == "name" and e.data not in names:
            raise Unsupported(f"observation cannot capture {e.data}")
        children = e.operands
        if e.op == "call":
            callee = children[0]
            if callee.op != "name" or callee.typ.name != "Function":
                raise Unsupported("only direct native calls can be observed")
            self._check_function(callee.data, stack, depth + 1)
            children = children[1:]
        for child in children:
            self._check_expr(child, names, stack, depth + 1)

    def can_audit_post(self, fn: StmtIR) -> bool:
        if fn.ensures is None:
            return False
        try:
            self._check_expr(fn.ensures, {"result", *(n for n, _ in fn.params)}, (fn.name,), 0)
        except Unsupported:
            return False
        return True

    def eval(self, e: ExprIR, env: dict, depth: int = 0):
        self.steps += 1
        if self.steps > MAX_STEPS or depth > MAX_DEPTH:
            raise ProbeFailure("per-probe evaluation budget exhausted")
        level = depth + 1
        op, args = e.op, e.operands
        if op == "literal":
            return e.data
        if op == "name":
            return env[e.data]
        if op == "guard":
            return self.eval(args[0], env, level)
        if op == "call":
            fn = self.functions[args[0].data]
            actuals = [self.eval(a, env, level) for a in args[1:]]
            local = dict(zip((n for n, _ in fn.params), actuals, strict=True))
            if fn.requires is not None and not self.eval(fn.requires, local, level):
                raise ProbeFailure(f"nested precondition failed in {fn.name}")
            value = self.eval(fn.expr, local, level)
            if fn.ensures is not None and not self.eval(fn.ensures, {**local, "result": value}, level):
                raise ProbeFailure(f"nested postcondition failed in {fn.name}")
            return value
        left = self.eval(args[0], env, level)
        if op == "neg":
            return -left
        if op == "not":
            return not left
        if op == "and":
            return left and self.eval(args[1], env, level)
        if op == "or":
            return left or self.eval(args[1], env, level)
        if op == "conditional":
            return self.eval(args[1] if left else args[2], env, level)
        right = self.eval(args[1], env, level)
        if op == "cmp":
            return _COMPARE[e.data](left, right)
        if op == "mod" and right == 0:
            raise ProbeFailure("integer remainder by zero")
        return _check_int(_BINARY[op](left, right))


@dataclass(frozen=True)
class _Candidate:
    coefficients: tuple[int, ...]
    constant: int

    def predict(self, point):
        return self.constant + sum(c * v for c, v in zip(self.coefficients, point))

    def form(self, names):
        return {"coefficients": {name: c for name, c in zip(names, self.coefficients) if c},
                "constant": self.constant}

    def contract(self, names):
        terms = [(c, n) for c, n in zip(self.coefficients, names) if c]
        if not terms:
            expression = str(self.constant)
        else:
            first, *more = terms
            expression = ("-" if first[0] < 0 else "") + first[1]
            for coefficient, name in more:
                expression += (" - " if coefficient < 0 else " + ") + name
            if self.constant:
                expression += (" - " if self.constant < 0 else " + ") + str(abs(self.constant))
        return "ensures result == " + expression


def _candidates(arity, observed):
    yield _Candidate((0,) * arity, observed)
    for width in (1, 2):
        for indices in combinations(range(arity), width):
            for signs in product((1, -1), repeat=width):
                weights = [0] * arity
                for index, sign in zip(indices, signs):
                    weights[index] = sign
                for offset in (0, -1, 1):
                    yield _Candidate(tuple(weights), offset)
    if arity > 2:
        for offset in (0, -1, 1):
            yield _Candidate((1,) * arity, offset)


def _pools(fn, names):
    # Only domain information shapes the probes. Body literals and the target
    # postcondition would leak potential answers or the location of exceptions.
    bounds = {name: Interval() for name in names}
    anchors = {name: [] for name in names}
    if fn.requires is not None:
        try:
            narrow(fn.requires, bounds)
        except BError:
            return [], []
        pending = [fn.requires]
        while pending:
            expr = pending.pop()
            match = int_comparison(expr)
            if match is not None:
                name, _, k = match
                anchors[name].extend([k, k + 1, k - 1])
            pending.extend(expr.operands)
    def clamp(name, v):
        b = bounds[name]
        if b.lo is not None:
            v = max(v, b.lo)
        if b.hi is not None:
            v = min(v, b.hi)
        if v == 0 and b.nonzero:
            v = -1 if b.hi is not None and b.hi <= 0 else 1
        return v

    pivot = tuple(clamp(n, 0) for n in names)
    def points(offsets):
        pool = {}
        for step in offsets:
            for pattern in (tuple(step for _ in names), tuple(step * (-1) ** i for i in range(len(names)))):
                point = tuple(clamp(n, p + s) for n, p, s in zip(names, pivot, pattern))
                pool[point] = None
            for i, name in enumerate(names):
                point = list(pivot)
                point[i] = clamp(name, point[i] + step)
                pool[tuple(point)] = None
        return pool

    initial = points((0, 1, -1, 2, -2, 3, -3))
    axis = [list(dict.fromkeys([pivot[i], *(clamp(n, k) for k in anchors[n])]))[:8]
            for i, n in enumerate(names)]
    initial.update(dict.fromkeys(islice(product(*axis), 128)))
    challenges = points((17, -7, 7, -17, 31, -31, 5, -5))
    # Reserve novel points before observing any result.
    return list(initial), [p for p in challenges if p not in initial]


def _discrimination(candidates, point):
    counts = Counter(c.predict(point) for c in candidates)
    return len(candidates) ** 2 - sum(n * n for n in counts.values())


def discover(program: ProgramIR, function: str) -> dict:
    """Observe a finite candidate family. No outcome authorizes a contract."""
    report = {"schema": "b-contract-discovery", "version": 1, "function": function,
              "status": "inconclusive", "reason": None, "proved": False,
              "candidate_form": None, "proposed_contract": None, "survivors": [],
              "observations": [], "counterexamples": [], "declared_counterexample": None,
              "declared_audit": "unavailable",
              "inadmissible_inputs": 0}
    try:
        interpreter = _Evaluator(program, function)
    except Unsupported as exc:
        return {**report, "status": "unsupported", "reason": str(exc)}
    fn = interpreter.functions[function]
    names = [n for n, _ in fn.params]
    if "result" in names:
        return {**report, "status": "unsupported", "reason": "result is reserved in a proposed ensures clause"}
    audit_post = interpreter.can_audit_post(fn)
    report["declared_audit"] = ("absent" if fn.ensures is None else
                                "unobserved" if audit_post else "unsupported")
    initial, reserve = _pools(fn, names)
    candidates = None

    def admissible(point):
        if any(x.bit_length() > MAX_BITS for x in point):
            return False
        interpreter.steps = 0
        allowed = fn.requires is None or interpreter.eval(fn.requires, dict(zip(names, point)))
        if not allowed:
            report["inadmissible_inputs"] += 1
        return allowed

    def observe(point, phase):
        nonlocal candidates
        local = dict(zip(names, point))
        interpreter.steps = 0
        try:
            actual = _check_int(interpreter.eval(fn.expr, local))
        except ProbeFailure as exc:
            report["probe_failure"] = {"inputs": local, "phase": phase, "reason": str(exc)}
            raise
        sample = {"phase": phase, "inputs": local, "result": actual}
        report["observations"].append(sample)
        if audit_post and report["declared_counterexample"] is None:
            interpreter.steps = 0
            try:
                holds = interpreter.eval(fn.ensures, {**local, "result": actual})
            except ProbeFailure:
                holds = None
                report["declared_audit"] = "incomplete"
            if holds is False:
                report["declared_audit"] = "counterexample"
                report["declared_counterexample"] = {"inputs": local, "result": actual,
                                                     "declared": "ensures " + _render(fn.ensures)}
            elif holds is True and report["declared_audit"] == "unobserved":
                report["declared_audit"] = "no-observed-violation"
        if candidates is None:
            candidates = list(_candidates(len(names), actual))
            report["candidate_count"] = len(candidates)
        kept = []
        eliminated = 0
        for candidate in candidates:
            expected = candidate.predict(point)
            if expected == actual:
                kept.append(candidate)
            else:
                # Count every rejected law. Show one illustrative elimination
                # per training observation and every surprise on reserved input.
                if phase == "challenge" or eliminated == 0:
                    report["counterexamples"].append({"contract": candidate.contract(names), "inputs": local,
                                                      "phase": phase, "expected": expected, "observed": actual})
                eliminated += 1
        if eliminated:
            sample["eliminated_candidates"] = eliminated
        candidates = kept

    try:
        initial = [p for p in initial if admissible(p)]
        reserve = [p for p in reserve if admissible(p)]
        if not reserve and len(initial) > 1:
            # A small bounded domain can collapse every distant challenge onto
            # the initial grid. Partition that grid BEFORE the first output.
            count = min(CHALLENGE_BUDGET, max(1, len(initial) // 3))
            held_indices = {(i + 1) * (len(initial) - 1) // count for i in range(count)}
            reserve = [p for i, p in enumerate(initial) if i in held_indices]
            initial = [p for i, p in enumerate(initial) if i not in held_indices]
        if not initial and reserve:
            initial.append(reserve.pop(0))
        for _ in range(DISCOVERY_BUDGET):
            if not initial or (candidates is not None and len(candidates) <= 1):
                break
            if candidates is None:
                point = initial[0]
            else:
                point = max(initial, key=lambda p: _discrimination(candidates, p))
                if _discrimination(candidates, point) == 0:
                    break
            initial.remove(point)
            observe(point, "discovery")
        for point in reserve[:CHALLENGE_BUDGET]:
            observe(point, "challenge")
    except ProbeFailure as exc:
        return {**report, "reason": str(exc)}

    if candidates is None:
        return {**report, "reason": "no admissible input found within the probe pools"}
    report["survivors"] = [c.contract(names) for c in candidates]
    if not candidates:
        return {**report, "status": "no-match", "reason": "every candidate disagrees with an observation"}
    if len(candidates) > 1:
        return {**report, "status": "ambiguous", "reason": "multiple candidates fit the admissible probes"}
    if names and not reserve:
        return {**report, "reason": "no distinct admissible challenge in the reserved pool"}
    best, = candidates
    return {**report, "status": "candidate", "reason": "one candidate fits the recorded observations",
            "candidate_form": best.form(names), "proposed_contract": best.contract(names)}
