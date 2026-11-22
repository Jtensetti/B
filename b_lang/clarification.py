"""Compare alternative postconditions on an explicit, finite set of input/output pairs.

A question asks whether a proposed output is allowed for given inputs. Candidate
expressions and the function's entry condition are interpreted directly. The
function body and its declared postcondition supply no evidence about intent.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product
from math import prod
import operator
import re

from .compiler import parse_postcondition
from .ir import ExprIR, ProgramIR
from .question_planner import minimax_question
from .types import BError, BOOL, INT

MAX_PARAMS = 8
MAX_CANDIDATES = 16
MAX_AXIS_VALUES = 256
MAX_CELLS = 4096
MAX_ANSWERS = 4096
MAX_BITS = 256
MAX_SOURCE_LENGTH = 1536
MAX_NODES = 128
MAX_DEPTH = 32
MAX_WORK = 2_000_000

_COMPARISONS = {"==": operator.eq, "!=": operator.ne, "<": operator.lt, ">": operator.gt,
                "<=": operator.le, ">=": operator.ge}
_ARITHMETIC = {"add": operator.add, "sub": operator.sub, "mul": operator.mul}
_TOKEN = re.compile(r"[ \t]+|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|==|!=|<=|>=|[()+*<>-]")

Point = tuple[int, ...]
Cell = tuple[Point, int]
Answer = tuple[dict[str, int], int, bool | None]


@dataclass(frozen=True)
class Space:
    parameters: tuple[str, ...]
    inputs: tuple[Point, ...]
    cells: tuple[Cell, ...]
    masks: dict[str, int]
    skipped: frozenset[int]
    report: dict


def _invalid(message: str):
    raise BError("E_CLARIFY_INPUT", message)


def _unsupported(message: str):
    raise BError("E_CLARIFY_UNSUPPORTED", message)


def _limit(message: str):
    raise BError("E_CLARIFY_LIMIT", message)


def _integer(value) -> int:
    if type(value) is not int:
        _invalid("Grid coordinates must be exact integers")
    if value.bit_length() > MAX_BITS:
        _limit(f"Integer exceeds the {MAX_BITS}-bit clarification limit")
    return value


def _sequence(values, limit: int, label: str):
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        _invalid(f"{label} must be a finite sequence")
    try:
        length = len(values)
    except OverflowError:
        _limit(f"{label} exceeds the size limit")
    if length > limit:
        _limit(f"{label} allows at most {limit} entries")
    # Index only the declared length. A Sequence may implement iteration with
    # different behavior from indexing; this preserves the pre-allocation bound.
    return tuple(values[i] for i in range(length))


def _axis(values) -> tuple[int, ...]:
    return tuple(sorted({_integer(v) for v in _sequence(values, MAX_AXIS_VALUES, "A grid axis")}))


def _preflight(text: str) -> None:
    # Bound parser work *before* normal type checking and constant folding.
    if type(text) is not str:
        _invalid("Each named policy needs a B postcondition expression")
    if len(text) > MAX_SOURCE_LENGTH:
        _limit("Candidate expression exceeds the source length limit")
    if not text.strip():
        _invalid("Each named policy needs a B postcondition expression")
    position = tokens = depth = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:
            _unsupported("Expected a single Int/Bool expression")
        token = match.group()
        position = match.end()
        if token.isspace():
            continue
        tokens += 1
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        if depth < 0:
            _unsupported("Unbalanced parenthesis in candidate expression")
        if depth > MAX_DEPTH or tokens > 2 * MAX_NODES:
            _limit("Candidate expression exceeds the parsing budget")
        if token[0].isdigit() and (len(token) > 80 or int(token).bit_length() > MAX_BITS):
            _limit("Integer literal exceeds the clarification limit")


def _check_expression(expr: ExprIR, names: set[str]) -> int:
    if expr.typ != BOOL:
        _unsupported("Clarification predicates must return Bool")
    pending = [(expr, 1)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            _limit("Predicate exceeds the clarification expression budget")
        op, args = node.op, node.operands
        if node.foreign_path or node.typ not in (INT, BOOL):
            _unsupported("Only native exact Int and Bool terms are supported")
        if op == "literal":
            if args or type(node.data) is not (int if node.typ == INT else bool):
                _unsupported("Unsupported clarification literal")
            if node.typ == INT:
                _integer(node.data)
        elif op == "name":
            if args or type(node.data) is not str or node.data not in names or node.typ != INT:
                _unsupported("Only integer parameters and the candidate result may be referenced")
        elif op in _ARITHMETIC or op == "neg":
            arity = 1 if op == "neg" else 2
            if len(args) != arity or node.typ != INT or any(a.typ != INT for a in args):
                _unsupported("Arithmetic requires integer operands")
        elif op == "cmp":
            if len(args) != 2 or node.typ != BOOL or node.data not in _COMPARISONS or args[0].typ != args[1].typ:
                _unsupported("Unsupported comparison")
            if args[0].typ == BOOL and node.data not in ("==", "!="):
                _unsupported("Boolean comparison supports only equality and inequality")
        elif op in ("and", "or", "not"):
            arity = 1 if op == "not" else 2
            if len(args) != arity or node.typ != BOOL or any(a.typ != BOOL for a in args):
                _unsupported("Boolean operators require Bool operands")
        else:
            _unsupported(f"Unsupported clarification operation {op}")
        pending.extend((a, depth + 1) for a in args)
    return count


def _evaluate(node: ExprIR, env: dict[str, int]) -> int | bool:
    op, args = node.op, node.operands
    if op == "literal":
        return node.data
    if op == "name":
        return env[node.data]
    left = _evaluate(args[0], env)
    if op == "not":
        return not left
    if op == "neg":
        return -left
    if op == "and":
        return left and _evaluate(args[1], env)
    if op == "or":
        return left or _evaluate(args[1], env)
    right = _evaluate(args[1], env)
    if op == "cmp":
        return _COMPARISONS[node.data](left, right)
    return _integer(_ARITHMETIC[op](left, right))


def _responses(answers, parameters, cells):
    index = {cell: i for i, cell in enumerate(cells)}
    positive = negative = 0
    skipped = set()
    definite = abstentions = 0
    for row in _sequence(answers, MAX_ANSWERS, "Answers"):
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            _invalid("Each answer must give inputs, a result, and true, false or null")
        inputs, result, allowed = row
        if type(inputs) is not dict or inputs.keys() != set(parameters):
            _invalid("Answer inputs must name every parameter exactly once")
        if allowed is not None and type(allowed) is not bool:
            _invalid("An answer must be true, false or null")
        key = (tuple(_integer(inputs[p]) for p in parameters), _integer(result))
        if key not in index:
            _invalid("An answer lies outside the admissible input/output grid")
        i = index[key]
        bit = 1 << i
        if allowed is None:
            abstentions += 1
            skipped.add(i)
        else:
            definite += 1
            if allowed:
                positive |= bit
            else:
                negative |= bit
    known = positive | negative
    skipped = frozenset(i for i in skipped if not ((known >> i) & 1))
    disclosures = {"responses": definite + abstentions, "definite_responses": definite,
                   "abstentions": abstentions, "definite_cells": known.bit_count(),
                   "skipped_cells": len(skipped), "distinct_cells": known.bit_count() + len(skipped)}
    return positive, negative, skipped, disclosures


def _question(parameters, cells, groups, skipped):
    best = None
    for i, (point, result) in enumerate(cells):
        if i in skipped:
            continue
        yes = sum((mask >> i) & 1 for mask in groups)
        split = min(yes, len(groups) - yes)
        if not split:
            continue
        coords = (*point, result)
        magnitudes = tuple(abs(x) for x in coords)
        key = (-split, sum(magnitudes), magnitudes, coords)
        if best is None or key < best[0]:
            best = (key, i)
    if best is None:
        return None
    return _question_at(parameters, cells, groups, best[1])


def _question_at(parameters, cells, groups, i):
    point, result = cells[i]
    allowed, forbidden = [], []
    yes = 0
    for mask, names in groups.items():
        accepts = (mask >> i) & 1
        yes += accepts
        (allowed if accepts else forbidden).extend(names)
    return {"inputs": dict(zip(parameters, point)), "result": result,
            "allowed_by": sorted(allowed), "forbidden_by": sorted(forbidden),
            "allowed_classes": yes, "forbidden_classes": len(groups) - yes}


def evaluate_space(program: ProgramIR, function: str, candidates: dict[str, str],
                   axes: dict[str, Sequence[int]], outputs: Sequence[int], answers: Sequence[Answer] = ()) -> Space:
    fn = next((s for s in program.statements if s.op == "fn" and s.name == function), None)
    if fn is None:
        _invalid(f"Unknown function {function}")
    parameters = tuple(n for n, _ in fn.params)
    if fn.typ != INT or any(t != INT for _, t in fn.params) or "result" in parameters:
        _unsupported("Clarification needs an Int result and Int parameters, with result reserved")
    if len(parameters) > MAX_PARAMS:
        _limit(f"At most {MAX_PARAMS} parameters are supported")
    if type(candidates) is not dict or len(candidates) < 2:
        _invalid("Supply at least two named candidate expressions")
    if len(candidates) > MAX_CANDIDATES:
        _limit(f"At most {MAX_CANDIDATES} candidates are supported")
    if any(type(name) is not str or not name.strip() or len(name) > 128 for name in candidates):
        _invalid("Each candidate needs a nonempty name of at most 128 characters")
    if type(axes) is not dict or axes.keys() != set(parameters):
        _invalid("Supply one input axis per function parameter")
    grid = {name: _axis(axes[name]) for name in parameters}
    results = _axis(outputs)
    points = prod(len(v) for v in grid.values())
    requested = points * len(results)
    if max(points, requested) > MAX_CELLS:
        _limit(f"The supplied Cartesian grid exceeds {MAX_CELLS} rows or cells")
    input_names = set(parameters)
    entry_size = _check_expression(fn.requires, input_names) if fn.requires else 0
    expressions = {}
    size = 0
    for name in sorted(candidates):
        source = candidates[name]
        _preflight(source)
        try:
            predicate = parse_postcondition(source, fn)
        except (BError, RecursionError, ValueError) as exc:
            _unsupported(f"Invalid candidate {name}: {exc}")
        size += _check_expression(predicate, input_names | {"result"})
        expressions[name] = predicate
    if points * entry_size + requested * size > MAX_WORK:
        _limit("Grid times predicate size exceeds the clarification evaluation budget")
    inputs = tuple(p for p in product(*grid.values())
                   if fn.requires is None or _evaluate(fn.requires, dict(zip(parameters, p))))
    cells = tuple(product(inputs, results))
    masks = dict.fromkeys(expressions, 0)
    for i, (point, result) in enumerate(cells):
        env = {**dict(zip(parameters, point)), "result": result}
        for name, predicate in expressions.items():
            if _evaluate(predicate, env):
                masks[name] |= 1 << i
    positive, negative, skipped, disclosures = _responses(answers, parameters, cells)
    groups = {}
    for name, mask in masks.items():
        if (mask & positive) == positive and not (mask & negative):
            groups.setdefault(mask, []).append(name)
    classes = sorted(groups.values())
    survivors = sorted(name for names in classes for name in names)
    question = None
    if not cells:
        status = "empty-domain"
    elif not survivors:
        status = "inconsistent"
    elif len(survivors) == 1:
        status = "selected"
    elif len(classes) == 1:
        status = "equivalent-on-grid"
    else:
        question = _question(parameters, cells, groups, skipped)
        status = "question" if question else "undetermined"
    disclosures.update(initial_classes=len(set(masks.values())), remaining_classes=len(classes))
    scope = {"axes": {n: list(v) for n, v in grid.items()}, "outputs": list(results),
             "input_count": points, "admissible_inputs": len(inputs), "cells": len(cells),
             "uses_requires": fn.requires is not None, "body_evaluated": False}
    report = {"schema": "b-contract-clarification", "version": 1, "function": function,
              "status": status, "survivors": survivors, "classes": classes, "question": question,
              "scope": scope, "disclosures": disclosures}
    if status == "inconsistent":
        report["reason"] = "conflicting-responses" if positive & negative else "no-candidate-fits-responses"
    return Space(parameters, inputs, cells, masks, skipped, report)


def compare(program: ProgramIR, function: str, candidates: dict[str, str],
            axes: dict[str, Sequence[int]], outputs: Sequence[int], answers: Sequence[Answer] = (),
            *, strategy: str = "balanced") -> dict:
    """Ask one bounded question or return the state of the supplied alternatives."""
    if strategy not in ("balanced", "minimax"):
        _invalid("Question strategy must be balanced or minimax")
    space = evaluate_space(program, function, candidates, axes, outputs, answers)
    if strategy == "balanced":
        return space.report
    groups = {space.masks[names[0]]: names for names in space.report["classes"]}
    index, planning = minimax_question(space.cells, tuple(groups), space.skipped, space.report["status"])
    report = {**space.report, "planning": planning}
    if index is not None:
        report["question"] = _question_at(space.parameters, space.cells, groups, index)
    return report
