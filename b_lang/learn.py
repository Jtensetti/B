"""Derive a function from examples, and find the example that would settle it.

`fn price(child: Bool, day: Text) -> Int pure by examples` has no body. The
compiler searches ordered rule lists of the form

    if A then x else if B and C then y else z

where each test compares one parameter with a value seen in an example or in a
comparison elsewhere in the program. It keeps the lists with the fewest tests
and cases that agree with every example. If those simplest lists agree on every
input B considers, the function is determined. Otherwise B picks the input on
which they disagree most evenly and asks for its result. The answer is one
more example.

The search is deliberately small and exhaustive. Its candidates, its notion of
"simplest" and the inputs it compares are documented in docs/examples.md.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from .model import Expr, Stmt
from .precedent import call_text, literal
from .types import BError

_SCALARS = {"Bool": bool, "Int": int, "Text": str, "Float": float}
_MAX_CASES = 4
_MAX_COST = 10
_MAX_WORK = 400_000
_MAX_GRID = 20_000
_SLACK = 1  # plausible readings may use this many more cases or tests
_COVERAGE = True  # ask about a domain neighbor of a value only one example supports
_FRESH = object()  # a Text value no example or rule mentions


class _Limit(Exception):
    pass


@dataclass(frozen=True)
class Atom:
    index: int
    op: str  # "is", "==", "<", ">=", "in"
    value: object
    label: str | None = None  # the group name for "in"

    def holds(self, argument) -> bool:
        if self.op == "is":
            return argument is self.value
        if argument is _FRESH:
            return False
        if self.op == "in":
            return argument in self.value
        if self.op == "==":
            return argument == self.value
        return argument < self.value if self.op == "<" else argument >= self.value


@dataclass(frozen=True)
class Rule:
    """An ordered list of (conjunction, output) cases and a fallback output."""
    cases: tuple[tuple[tuple[Atom, ...], object], ...]
    fallback: object

    @property
    def cost(self) -> int:
        return sum(1 + len(tests) for tests, _ in self.cases)

    def apply(self, arguments: tuple):
        for tests, output in self.cases:
            if all(atom.holds(arguments[atom.index]) for atom in tests):
                return output
        return self.fallback


def _test_text(atom: Atom, names: list[str]) -> str:
    name = names[atom.index]
    if atom.op == "is":
        return name if atom.value else f"not {name}"
    if atom.op == "in":
        return f"{name} in {atom.label}"
    return f"{name} {atom.op} {literal(atom.value)}"


def render(rule: Rule, names: list[str]) -> str:
    text = ""
    for tests, output in rule.cases:
        text += f"if {' and '.join(_test_text(a, names) for a in tests)} then {literal(output)} else "
    return text + literal(rule.fallback)


def to_expr(rule: Rule, names: list[str]) -> Expr:
    def test(atom: Atom) -> Expr:
        name = Expr("name", (names[atom.index],))
        if atom.op == "is":
            return name if atom.value else Expr("not", (name,))
        if atom.op == "in":
            return Expr("member", (name, atom.label))
        return Expr("cmp", (name, atom.op, Expr("literal", (atom.value,))))

    body = Expr("literal", (rule.fallback,))
    for tests, output in reversed(rule.cases):
        condition = test(tests[0])
        for atom in tests[1:]:
            condition = Expr("and", (condition, test(atom)))
        body = Expr("conditional", (condition, Expr("literal", (output,)), body))
    return body


@dataclass
class Learned:
    name: str
    names: list[str]
    examples: list[tuple[tuple, object]]
    rule: Rule
    alternatives: list[Rule]  # simplest rules with a different behavior, canonical first
    question: tuple | None  # input on which the simplest rules disagree
    answers: list  # their results on that input, canonical first
    unseen_only: bool  # the rules differ only on a Text value no example names
    params: list = None
    result: str = ""
    hints: dict = None
    domains: dict = None
    reason: str | None = None  # "readings" or "coverage"
    groups: dict = None

    def with_example(self, arguments: tuple, value) -> "Learned":
        return learn(self.name, self.params, self.result, [*self.examples, (arguments, value)],
                     self.hints, self.domains, self.groups)

    @property
    def determined(self) -> bool:
        return self.question is None

    def question_text(self) -> str:
        arguments = ", ".join("<another value>" if v is _FRESH else literal(v) for v in self.question)
        return f"{self.name}({arguments}): " + " or ".join(literal(v) for v in self.answers) + "?"


def _exact(value, type_name: str) -> bool:
    return type(value) is _SCALARS.get(type_name)


def resolve_examples(name: str, rows: list[Stmt]) -> list[tuple[tuple, object]]:
    """Apply `was` supersession in source order. A changed result must name its old value."""
    current: dict = {}
    order = []
    for row in rows:
        _, arguments, value, previous, has_previous = row.parts
        key = tuple((type(v), v) for v in arguments)
        if key in current:
            old = current[key][1]
            if not has_previous:
                if type(old) is type(value) and old == value:
                    continue
                raise BError("E_EXAMPLE", f"example {call_text(name, arguments)} == {literal(value)} contradicts "
                             f"an earlier example with result {literal(old)}; write "
                             f"'example {call_text(name, arguments)} == {literal(value)} was {literal(old)}' "
                             "to change it")
            if type(old) is not type(previous) or old != previous:
                raise BError("E_EXAMPLE", f"example {call_text(name, arguments)} says it was "
                             f"{literal(previous)}, but the current example says {literal(old)}")
        elif has_previous:
            raise BError("E_EXAMPLE", f"example {call_text(name, arguments)} uses 'was' but "
                         "no earlier example states that result")
        else:
            order.append(key)
        current[key] = (arguments, value)
    return [current[key] for key in order]


def learn(name: str, params: list[tuple[str, str]], result: str,
          examples: list[tuple[tuple, object]], hints: dict[str, set] | None = None,
          domains: dict[str, tuple] | None = None, groups: dict | None = None) -> Learned:
    names = [n for n, _ in params]
    types = [t for _, t in params]
    if not examples:
        raise BError("E_EXAMPLE", f"{name} is defined by examples but has none")
    for type_name in types:
        if type_name not in ("Bool", "Int", "Text"):
            raise BError("E_EXAMPLE", f"{name}: by examples supports Bool, Int and Text parameters, not {type_name}")
    if result not in _SCALARS:
        raise BError("E_EXAMPLE", f"{name}: by examples supports Bool, Int, Float and Text results, not {result}")
    for arguments, value in examples:
        if len(arguments) != len(params):
            raise BError("E_ARITY", f"example {name} expects {len(params)} literals, got {len(arguments)}")
        for (param, type_name), argument in zip(params, arguments):
            if not _exact(argument, type_name):
                raise BError("E_TYPE", f"example {name}: {param} requires an exact literal of type {type_name}")
        if not _exact(value, result):
            raise BError("E_TYPE", f"example {call_text(name, arguments)}: result must be an exact {result} literal")

    hints = hints or {}
    domains = domains or {}
    values = []
    closed = []
    for i, (param, type_name) in enumerate(params):
        domain = [v for v in domains.get(param, ()) if _exact(v, type_name)]
        closed.append(bool(domain))
        seen = {a[i] for a, _ in examples} | {v for v in hints.get(param, ()) if _exact(v, type_name)}
        if type_name == "Bool":
            values.append([False, True])
        elif domain and type_name == "Text":
            values.append(list(domain))  # keep the declared order
        elif domain:
            # Boundaries come from examples. The whole domain is compared.
            values.append(sorted(seen & set(domain)))
        else:
            values.append(sorted(seen))

    atoms: list[list[Atom]] = []
    grid_axes = []
    for i, type_name in enumerate(types):
        if type_name == "Bool":
            atoms.append([Atom(i, "is", True), Atom(i, "is", False)])
            grid_axes.append([False, True])
        elif type_name == "Text":
            # A named group is one test: knowing "weekend" makes a weekend rule simple.
            known_groups = [Atom(i, "in", frozenset(members), label)
                            for label, (param, members) in sorted((groups or {}).items())
                            if param == params[i][0]]
            atoms.append(known_groups + [Atom(i, "==", v) for v in values[i]])
            grid_axes.append(values[i] if closed[i] else [*values[i], _FRESH])
        else:
            thresholds = {t for v in values[i] for t in (v, v + 1)}
            # A boundary may lie anywhere in a gap between known values. Its
            # midpoint stands for the whole gap, so questions halve it.
            known = sorted(values[i])
            if closed[i]:
                axis = sorted(v for v in domains[params[i][0]] if _exact(v, "Int"))
                known = sorted({axis[0], *known, axis[-1]})
            thresholds |= {(a + b + 1) // 2 for a, b in zip(known, known[1:]) if b - a > 1}
            thresholds = sorted(thresholds)
            # Prefer a boundary to a single value when both explain the examples.
            atoms.append([Atom(i, op, t) for t in thresholds for op in ("<", ">=")]
                         + [Atom(i, "==", v) for v in values[i]])
            points = set(values[i])
            if closed[i]:
                points = set(v for v in domains[params[i][0]] if _exact(v, "Int"))
            else:
                points |= {values[i][0] - 1, values[i][-1] + 1}
                points |= {(a + b) // 2 for a, b in zip(values[i], values[i][1:]) if b - a > 1}
            grid_axes.append(sorted(points))

    tests = [(a,) for row in atoms for a in row]
    for left_row, right_row in itertools.combinations(atoms, 2):
        tests.extend(itertools.product(left_row, right_row))
    for row in atoms:  # an interval on one integer parameter
        lows = [a for a in row if a.op == ">="]
        highs = [a for a in row if a.op == "<"]
        tests.extend((low, high) for low in lows for high in highs if low.value < high.value)

    grid_size = 1
    for axis in grid_axes:
        grid_size *= len(axis)
    if grid_size > _MAX_GRID:
        raise BError("E_EXAMPLE", f"{name}: too many combinations of example values to compare "
                     f"({grid_size}); write the function or split it")
    grid = list(itertools.product(*grid_axes))
    inputs = [a for a, _ in examples]
    outputs = [v for _, v in examples]

    def mask(points, conjunction):
        bits = 0
        for k, point in enumerate(points):
            if all(atom.holds(point[atom.index]) for atom in conjunction):
                bits |= 1 << k
        return bits

    example_masks = [mask(inputs, t) for t in tests]
    useful = [k for k, m in enumerate(example_masks) if m]
    labels: dict = {}
    for k, value in enumerate(outputs):
        key = (type(value), value)
        labels.setdefault(key, [value, 0])[1] |= 1 << k
    distinct = sorted(labels.values(), key=lambda pair: (str(type(pair[0])), pair[0]))
    everything = (1 << len(examples)) - 1

    found: list[Rule] = []
    work = [0]

    def search(remaining: int, budget: int, cases: list):
        work[0] += 1
        if work[0] > _MAX_WORK:
            raise _Limit
        # Without further cases, every remaining example must share the fallback.
        for value, bits in distinct:
            if remaining & ~bits == 0 and budget == 0:
                found.append(Rule(tuple(cases), value))
        if budget < 2 or len(cases) >= _MAX_CASES or remaining == 0:
            return
        for k in useful:
            covered = remaining & example_masks[k]
            if not covered:
                continue
            cost = 1 + len(tests[k])
            if cost > budget:
                continue
            for value, bits in distinct:
                if covered & ~bits == 0:
                    search(remaining & ~covered, budget - cost, [*cases, (tests[k], value)])
                    break

    try:
        for budget in range(_MAX_COST + 1):
            search(everything, budget, [])
            if found:
                break
    except _Limit:
        raise BError("E_EXAMPLE", f"{name}: the examples need a rule beyond the search limit; "
                     "write the function or add examples that separate its cases") from None
    if not found:
        raise BError("E_EXAMPLE", f"{name}: no rule with up to {_MAX_CASES} cases of at most two tests "
                     "fits the examples; write the function")
    simplest = found[:]
    # One more test than the simplest rule is still a plausible reading. It
    # may raise a question, but only between values the examples span, so
    # that questions cannot wander off past the outermost example forever.
    plausible = []
    for extra in range(1, _SLACK + 1):
        found.clear()
        work[0] = 0
        try:
            search(everything, budget + extra, [])
        except _Limit:
            break
        plausible.extend(found)

    # Among equally simple rules, the fallback most examples agree with comes first:
    # an input no example resembles then gets the most common result.
    frequency = {(type(v), v): bin(bits).count("1") for v, bits in distinct}
    simplest.sort(key=lambda rule: -frequency[(type(rule.fallback), rule.fallback)])

    def distinct_behaviors(candidates):
        behaviors: dict[tuple, Rule] = {}
        for rule in candidates:
            signature = tuple((type(r), r) for r in (rule.apply(p) for p in grid))
            behaviors.setdefault(signature, rule)
        return list(behaviors.values())

    rules = distinct_behaviors(simplest)
    wider = distinct_behaviors(rules + plausible)
    canonical = rules[0]
    spans = [(min(a[i] for a in inputs), max(a[i] for a in inputs)) if t == "Int" and not closed[i] else None
             for i, t in enumerate(types)]

    def inner(point) -> bool:
        return all(v is not _FRESH and (span is None or span[0] <= v <= span[1])
                   for v, span in zip(point, spans))

    best = None
    for point in grid:
        candidates = wider if inner(point) else rules
        results = [r.apply(point) for r in candidates]
        tally: dict = {}
        for value in results:
            tally[(type(value), value)] = tally.get((type(value), value), 0) + 1
        if len(tally) < 2:
            continue
        fresh = any(v is _FRESH for v in point)
        # Prefer a question that splits the simplest readings, then an even split.
        splits_simplest = len({(type(v), v) for v in (r.apply(point) for r in rules)}) > 1
        # Then stay near the newest example: a change raises questions about its neighbors.
        # On an integer axis, the point farthest from every example halves the gap.
        distance = sum(1 for i, (a, b) in enumerate(zip(point, inputs[-1]))
                       if types[i] != "Int" and a is not b and a != b)
        gap = min(sum(abs(point[i] - row[i]) for i in range(len(types)) if types[i] == "Int") for row in inputs)
        score = (fresh, not splits_simplest, max(tally.values()) / len(results), distance, -gap, -len(tally))
        if best is None or score < best[0]:
            best = (score, point, results)
    question, answers, unseen_only = None, [], False
    alternatives = []
    if best is not None:
        (fresh, *_), point, results = best
        unseen_only = fresh
        question = point
        for value in results:
            if not any(type(value) is type(a) and value == a for a in answers):
                answers.append(value)
        alternatives = [r for r in wider[1:]
                        if any(type(r.apply(p)) is not type(canonical.apply(p)) or r.apply(p) != canonical.apply(p)
                               for p in grid if inner(p) or r in rules)]
        canonical_value = canonical.apply(point)
        answers.sort(key=lambda v: not (type(v) is type(canonical_value) and v == canonical_value))
    reason = "readings" if question is not None else None
    if question is None and _COVERAGE:
        found_gap = _single_witness_question(canonical, examples, params, domains)
        if found_gap is not None:
            question, answers = found_gap
            reason = "coverage"
    return Learned(name, names, examples, canonical, alternatives, question, answers, unseen_only,
                   list(params), result, hints, domains, reason, groups)


def _single_witness_question(rule: Rule, examples, params, domains):
    """Ask whether a value that one example singled out has a neighbor in the same case.

    A case such as `child and day == "sun"` that only one example supports
    may have been meant for more values. B asks about the value next to it in
    the declared domain order, keeping the witness's other arguments. The
    order is the only notion of similarity B has here.
    """
    stated = {tuple((type(v), v) for v in arguments) for arguments, _ in examples}
    for position, (tests, output) in enumerate(rule.cases):
        witnesses = [a for a, _ in examples
                     if Rule(rule.cases[position:position + 1], object()).apply(a) is output
                     and all(Rule(rule.cases[k:k + 1], object()).apply(a) is not rule.cases[k][1]
                             for k in range(position))]
        if len(witnesses) != 1:
            continue
        witness = witnesses[0]
        for atom in tests:
            param, type_name = params[atom.index]
            domain = domains.get(param) if domains else None
            if atom.op != "==" or type_name != "Text" or not domain or atom.value not in domain:
                continue
            at = domain.index(atom.value)
            for neighbor in (domain[at - 1] if at > 0 else None, domain[at + 1] if at + 1 < len(domain) else None):
                if neighbor is None:
                    continue
                point = tuple(neighbor if i == atom.index else v for i, v in enumerate(witness))
                if tuple((type(v), v) for v in point) in stated:
                    continue
                current = rule.apply(point)
                if type(current) is type(output) and current == output:
                    continue
                return point, [current, output]
    return None


def program_hints(statements: list[Stmt]) -> dict[str, set]:
    """Literals compared with a named parameter anywhere in the program."""
    hints: dict[str, set] = {}

    def visit(node):
        if isinstance(node, Expr):
            if node.kind == "cmp":
                left, _, right = node.parts
                for a, b in ((left, right), (right, left)):
                    if isinstance(a, Expr) and a.kind == "name" and isinstance(b, Expr) and b.kind == "literal":
                        hints.setdefault(a.parts[0], set()).add(b.parts[0])
            for part in node.parts:
                visit(part)
        elif isinstance(node, (tuple, list)):
            for part in node:
                visit(part)

    for statement in statements:
        if statement.kind in ("fn", "let", "print", "assert"):
            visit(statement.parts)
    return hints


def collect_domains(statements: list[Stmt], hints: dict[str, set]) -> dict[str, tuple]:
    """`domain day: "mon", ..., "sun"` names every value an input called day can take."""
    domains: dict[str, tuple] = {}
    for statement in statements:
        if statement.kind != "domain":
            continue
        name, values = statement.parts
        if name in domains:
            raise BError("E_DOMAIN", f"Duplicate domain for {name}")
        if not values or len({type(v) for v in values}) != 1 or type(values[0]) not in (int, str, bool):
            raise BError("E_DOMAIN", f"domain {name} needs one or more Int, Text or Bool literals of one type")
        if len(set(values)) != len(values):
            raise BError("E_DOMAIN", f"domain {name} repeats a value")
        domains[name] = tuple(values)
    known = {name: {(type(v), v) for v in values} for name, values in domains.items()}

    def check(param: str, value, where: str):
        if param in known and type(value) is type(domains[param][0]) and (type(value), value) not in known[param]:
            raise BError("E_DOMAIN", f"{where}: {literal(value)} is not in domain {param}")

    for param, values in hints.items():
        for value in values:
            check(param, value, f"comparison with {param}")
    signatures = {s.parts[0]: [n for n, _ in s.parts[1]] for s in statements if s.kind in ("fn", "learn")}
    for statement in statements:
        if statement.kind in ("example", "also"):
            name, arguments = statement.parts[:2]
            for param, value in zip(signatures.get(name, ()), arguments):
                check(param, value, f"{statement.kind} {call_text(name, arguments)}")
            if statement.kind == "also" and statement.parts[3] is not None:
                for param, value in zip(signatures.get(name, ()), statement.parts[3]):
                    check(param, value, f"like ({', '.join(literal(v) for v in statement.parts[3])})")
    return domains


def include_knowledge(statements: list[Stmt]) -> list[Stmt]:
    """Replace `know calendar` with the domains and groups B ships in b_lang/truths."""
    from importlib import resources
    from .model import parse
    result, seen = [], set()
    for statement in statements:
        if statement.kind != "know":
            result.append(statement)
            continue
        topic, = statement.parts
        if topic in seen:
            continue
        seen.add(topic)
        source = resources.files("b_lang").joinpath("truths", f"{topic}.bee")
        if not source.is_file():
            available = sorted(p.name[:-4] for p in resources.files("b_lang").joinpath("truths").iterdir()
                               if p.name.endswith(".bee"))
            raise BError("E_KNOW", f"B knows no topic {topic!r}; available: {', '.join(available)}")
        known = parse(source.read_text(encoding="utf-8"))
        if any(s.kind not in ("domain", "group") for s in known):
            raise BError("E_KNOW", f"Knowledge file {topic} may only declare domains and groups")
        result.extend(known)
    return result


def collect_groups(statements: list[Stmt], domains: dict[str, tuple]) -> dict[str, tuple[str, tuple]]:
    """`group weekend of day: "sat", "sun"` names a subset of an input's values."""
    groups: dict[str, tuple[str, tuple]] = {}
    for statement in statements:
        if statement.kind != "group":
            continue
        name, param, members = statement.parts
        if name in groups:
            raise BError("E_DOMAIN", f"Duplicate group {name}")
        if not members or len({type(v) for v in members}) != 1 or type(members[0]) is not str:
            raise BError("E_DOMAIN", f"group {name} needs one or more Text literals")
        if param in domains:
            outside = [v for v in members if v not in domains[param]]
            if outside:
                raise BError("E_DOMAIN", f"group {name}: {literal(outside[0])} is not in domain {param}")
        groups[name] = (param, tuple(members))
    return groups


def desugar_membership(node, groups: dict):
    """Rewrite `x in weekend` as equality tests the type checker already understands."""
    if isinstance(node, Expr):
        if node.kind == "member":
            subject, name = node.parts
            if name not in groups:
                raise BError("E_NAME", f"No group named {name!r}")
            subject = desugar_membership(subject, groups)
            tests = [Expr("cmp", (subject, "==", Expr("literal", (v,)))) for v in groups[name][1]]
            result = tests[0]
            for test in tests[1:]:
                result = Expr("or", (result, test))
            return result
        return Expr(node.kind, tuple(desugar_membership(p, groups) for p in node.parts))
    if isinstance(node, tuple):
        return tuple(desugar_membership(p, groups) for p in node)
    if isinstance(node, list):
        return [desugar_membership(p, groups) for p in node]
    return node


def expand(statements: list[Stmt]) -> tuple[list[Stmt], dict[str, Learned]]:
    """Replace each `by examples` declaration with an ordinary pure function."""
    statements = include_knowledge(statements)
    rows: dict[str, list[Stmt]] = {}
    for statement in statements:
        if statement.kind == "example":
            rows.setdefault(statement.parts[0], []).append(statement)
    hints = program_hints(statements)
    domains = collect_domains(statements, hints)
    groups = collect_groups(statements, domains)
    learned = {}
    expanded = []
    for statement in statements:
        if statement.kind != "learn":
            expanded.append(statement)
            continue
        name, params, result, _ = statement.parts
        if any(type_args for _, (_, type_args) in params) or result[1]:
            raise BError("E_EXAMPLE", f"{name}: by examples supports scalar parameters and results")
        examples = resolve_examples(name, rows.get(name, []))
        found = learn(name, [(n, t[0]) for n, t in params], result[0], examples, hints, domains, groups)
        learned[name] = found
        expanded.append(Stmt("fn", (name, params, result, to_expr(found.rule, found.names), True, None, None)))
    for name in rows:
        if name not in learned and not any(s.kind == "fn" and s.parts[0] == name for s in statements):
            raise BError("E_EXAMPLE", f"example names no function {name!r}")
    expanded = [Stmt(s.kind, desugar_membership(s.parts, groups)) for s in expanded]
    return expanded, learned
