"""Check a B module against its accepted predecessor plus an executable change."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace

from lark.exceptions import LarkError

from .compiler import compile_b
from .ir import ProgramIR, StmtIR
from .model import Stmt, ToModel, parse, parser_input, positioned_parser
from .preservation import function_dependencies, validate_preservation
from .revision_witness import compare_functions, evaluate_rule, evaluate_scalar
from .types import BError


@dataclass(frozen=True)
class _Declaration:
    name: str
    arguments: tuple
    keeping: tuple[str, ...]
    like: tuple | None
    source: str

    @property
    def key(self):
        # Python conflates True, 1 and 1.0. B checks the exact declared type.
        like = None if self.like is None else tuple((type(v), v) for v in self.like)
        return self.name, tuple((type(v), v) for v in self.arguments), frozenset(self.keeping), like


def _read(text: str, *, spans: bool = False) -> tuple[list[Stmt], list[_Declaration]]:
    if not spans:
        statements = parse(text)
        return statements, [_Declaration(*s.parts, "") for s in statements if s.kind == "also"]
    tree = positioned_parser().parse(parser_input(text))
    statements = ToModel().transform(tree)
    declarations = [
        _Declaration(*statement.parts, text[node.meta.start_pos:node.meta.end_pos])
        for node, statement in zip(tree.children, statements, strict=True)
        if statement.kind == "also"
    ]
    return statements, declarations


def _delta_statements(text: str) -> list[Stmt]:
    statements = parse(text)
    if not statements or any(s.kind != "also" for s in statements):
        raise BError("E_REVISION", "Expected a nonempty file containing only also declarations")
    return statements


def _read_delta(text: str) -> list[_Declaration]:
    statements = _delta_statements(text)
    if len(statements) == 1:
        return [_Declaration(*statements[0].parts, text.strip())]
    return _read(text, spans=True)[1]


def _append(base: str, delta: str) -> str:
    return base + ("" if base.endswith("\n") or not base else "\n") + delta


def attach_delta(base_text: str, delta: str) -> str:
    """Use the exact same B declaration file for execution and revision checking."""
    try:
        _delta_statements(delta)
    except LarkError as exc:
        raise BError("E_SYNTAX", str(exc)) from exc
    return _append(base_text, delta)


def _outside(statements: list[Stmt]) -> str | None:
    # Check syntax before compiling. An adopt can consult installed source, a
    # foreign import can trigger discovery, and a pending next disappears in BIR.
    for stmt in statements:
        if stmt.kind not in ("fn", "also", "permit", "print"):
            return f"{stmt.kind} is outside the closed native function module"
        if stmt.kind == "fn" and not stmt.parts[4]:
            return f"Function {stmt.parts[0]} needs an explicit pure declaration"
        if stmt.kind == "permit" and set(stmt.parts[0]) - {"console"}:
            return "Only console permission is supported by the revision checker"
    return None


def _projection(stmt: StmtIR) -> StmtIR:
    # B forbids user declarations starting with _b_. Treat the value of one
    # print as a closed function. Never invoke the print primitive here.
    return StmtIR("fn", name="_b_output", typ=stmt.expr.typ, expr=stmt.expr, declared_pure=True)


def _opaque(program: ProgramIR) -> str | None:
    # Pure is not sufficient here. An attribute on Any may invoke host code.
    # Inspect before optimization so constant folding cannot hide a boundary.
    for stmt in program.statements:
        if stmt.op == "permit":
            continue
        if stmt.op == "print" and stmt.effects != ("console",):
            return "The value printed has external effects"
        definition = _projection(stmt) if stmt.op == "print" else stmt
        try:
            function_dependencies(definition)
        except BError as exc:
            return f"Outside the closed scalar module: {exc.message}"
    return None


def _same_ir(first, second) -> bool:
    # Ordinary dataclass equality erases the sign of floating point zero.
    return json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def _output_text(program: ProgramIR, stmt: StmtIR) -> str | None:
    if stmt.expr.op == "literal":
        value = stmt.expr.data
    else:
        projected = replace(program, statements=(*program.statements, _projection(stmt)))
        known, value = evaluate_scalar(projected, "_b_output", ())
        if not known:
            return None
    # The current B backend uses Python's print(value). Text "1" and Int 1
    # consequently have identical output, while 0.0 and -0.0 differ.
    try:
        return str(value) + "\n"
    except ValueError:  # Python's integer-to-text digit limit
        return None


def _compare_output(reference: ProgramIR, candidate: ProgramIR, left: list[StmtIR],
                    right: list[StmtIR], functions_proved: bool) -> dict:
    # Once all callees are equivalent, the same expression has the same
    # output or failure. Only compute a shared suffix when earlier print
    # calls split their text differently and output is still unmatched.
    last_change = len(left)
    if functions_proved:
        last_change = max((i for i, (a, b) in enumerate(zip(left, right), 1)
                           if not _same_ir(a.expr.to_dict(), b.expr.to_dict())), default=0)
        if not last_change:
            return {"status": "proved"}
    expected = actual = ""
    matched = 0
    for index, (a, b) in enumerate(zip(left, right), 1):
        if functions_proved and index > last_change and len(expected) == len(actual):
            break
        if index > 1024:
            return {"status": "unknown", "reason": "Output comparison work limit reached"}
        x, y = _output_text(reference, a), _output_text(candidate, b)
        if x is None or y is None:
            return {"status": "unknown", "reason": f"Cannot establish the rendered prefix at print {index}"}
        if max(len(expected) + len(x), len(actual) + len(y)) > 1_000_000:
            return {"status": "unknown", "reason": "Output comparison text budget reached"}
        expected += x
        actual += y
        end = min(len(expected), len(actual))
        if expected[matched:end] != actual[matched:end]:
            return {"status": "counterexample", "method": "native-output-stream", "output_index": index,
                    "expected": expected, "actual": actual}
        matched = end
    if len(expected) != len(actual):
        return {"status": "counterexample", "method": "native-output-stream", "output_index": len(left),
                "expected": expected, "actual": actual}
    return {"status": "proved", "output_method": "native-output-stream"}


def check_revision(base_text: str, candidate_text: str, delta: str | None = None) -> dict:
    """Prove equivalence to base + delta, reject a witness, or report uncertainty.

    Without a separate delta the candidate's new declarations are trusted.
    With a pinned delta a candidate can implement it directly in ordinary B.
    Every named function is public in this profile, including helper functions.
    """
    report = {"authority": "candidate" if delta is None else "pinned"}
    stage = "base"
    try:
        base_statements, accepted = _read(base_text)
        stage = "candidate"
        candidate_statements, proposed = _read(candidate_text, spans=delta is None)
        for label, statements in (("base", base_statements), ("candidate", candidate_statements)):
            reason = _outside(statements)
            if reason:
                return {**report, "status": "unknown", "reason": f"{label}: {reason}"}

        accepted_keys = {row.key for row in accepted}
        proposed_keys = {row.key for row in proposed}
        if not accepted_keys <= proposed_keys:
            raise BError("E_REVISION", "An already accepted also declaration was removed or altered")
        additions = [row for row in proposed if row.key not in accepted_keys]
        stage = "delta"
        if delta is None:
            if not additions:
                raise BError("E_REVISION", "No new also declaration in candidate")
            delta = "\n".join(row.source for row in additions)
            authorized = additions
        else:
            authorized = _read_delta(delta)
            authorized_keys = {row.key for row in authorized}
            if any(row.key not in authorized_keys for row in additions):
                raise BError("E_REVISION", "Candidate contains an also declaration outside the pinned delta")
        report["delta"] = [row.source for row in authorized]

        stage = "base"
        base = compile_b(base_text)
        reason = _opaque(base.ir)
        if reason:
            return {**report, "status": "unknown", "reason": f"base: {reason}"}
        stage = "base plus delta"
        reference_text = _append(base_text, delta)
        reference = compile_b(reference_text)
        for row in authorized:
            previous_value = evaluate_rule(base.optimized_ir, row.name, row.arguments)
            if previous_value is None:
                return {**report, "status": "unknown",
                        "reason": f"Cannot establish the prior value of {row.source}"}
            if previous_value:
                raise BError("E_REVISION", f"Requested addition is already true in the accepted base: {row.source}")
            if evaluate_rule(reference.optimized_ir, row.name, row.arguments) is not True:
                return {**report, "status": "unknown",
                        "reason": f"Cannot establish the granted value of {row.source}"}
        stage = "candidate"
        if parser_input(candidate_text) == parser_input(reference_text):
            candidate = reference
        else:
            candidate = compile_b(candidate_text)
            reason = _opaque(candidate.ir)
            if reason:
                return {**report, "status": "unknown", "reason": f"candidate: {reason}"}
            # An independently implemented candidate can omit the declaration
            # text but must meet the same structural keeping constraints.
            validate_preservation(candidate.ir, [
                Stmt("also", (row.name, row.arguments, row.keeping, row.like)) for row in authorized
            ])
        expected = {s.name: s for s in reference.optimized_ir.statements if s.op == "fn"}
        report["functions"] = list(expected)
        prints = [s for s in reference.optimized_ir.statements if s.op == "print"]
        report["prints"] = len(prints)
        if candidate is reference:
            return {**report, "status": "proved", "method": "identical-bir", "cases": 0}
        if candidate.ir.permitted_effects != reference.ir.permitted_effects:
            raise BError("E_REVISION", "Candidate changes the module's declared permissions")
        actual = {s.name: s for s in candidate.optimized_ir.statements if s.op == "fn"}
        if expected.keys() != actual.keys():
            raise BError("E_REVISION", "Candidate changes the set of public functions")
        candidate_prints = [s for s in candidate.optimized_ir.statements if s.op == "print"]
        if len(prints) != len(candidate_prints):
            raise BError("E_REVISION", "Candidate changes the number of print sites")
        changed = []
        for name, left in expected.items():
            right = actual[name]
            if (left.typ, left.params) != (right.typ, right.params):
                raise BError("E_REVISION", f"Candidate changes the public signature of {name}")
            left_ir, right_ir = left.to_dict(), right.to_dict()
            for key in ("requires", "ensures"):
                if not _same_ir(left_ir.get(key), right_ir.get(key)):
                    raise BError("E_REVISION", f"Candidate changes the {key} contract of {name}")
            if not _same_ir(left_ir, right_ir):
                changed.append(name)
        # An unchanged caller can substitute an equivalent, pure callee.
        if changed:
            result = compare_functions(reference.optimized_ir, candidate.optimized_ir, changed)
        else:
            result = {"status": "proved", "method": "identical-bir", "cases": 0}
        if result["status"] == "counterexample":
            return {**report, **result}
        output = _compare_output(reference.optimized_ir, candidate.optimized_ir, prints,
                                 candidate_prints, result["status"] == "proved")
        if output["status"] != "proved":
            return {**report, "cases": result["cases"], **output}
        if "output_method" in output:
            result["output_method"] = output["output_method"]
            if not changed:
                result["method"] = output["output_method"]
        return {**report, **result}
    except (BError, LarkError) as exc:
        return {**report, "status": "invalid", "reason": f"{stage}: {exc}"}
    except RecursionError:
        return {**report, "status": "unknown", "reason": f"{stage}: nesting limit reached"}
