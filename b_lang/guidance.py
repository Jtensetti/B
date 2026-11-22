"""Explain unresolved arithmetic and native argument bounds at checked BIR sites."""
from __future__ import annotations

from .composition import Analysis, Obligation, _render
from .contracts import int_comparison
from .ir import ExprIR, ProgramIR, StmtIR
from .types import ANY, FLOAT


def _roots(program: ProgramIR) -> dict[tuple[str, str], ExprIR]:
    roots = {}
    ordinals: dict[str, int] = {}
    for statement in program.statements:
        if statement.expr is None:
            continue
        if statement.op == "fn":
            roots[(statement.name, "body")] = statement.expr
        else:
            ordinal = ordinals.get(statement.op, 0)
            ordinals[statement.op] = ordinal + 1
            label = f"let.{statement.name}" if statement.op == "let" else f"{statement.op}.{ordinal}"
            roots[("<module>", label)] = statement.expr
    return roots


def _comparisons(test: ExprIR, branch: bool):
    if test.op == "not":
        yield from _comparisons(test.operands[0], not branch)
    elif (test.op == "and" and branch) or (test.op == "or" and not branch):
        for part in test.operands:
            yield from _comparisons(part, branch)
    elif test.op == "cmp":
        yield test, branch


def _literal(node: ExprIR):
    if node.op == "literal" and type(node.data) in (int, float):
        return node.data
    if node.op == "neg" and node.operands[0].op == "literal":
        value = node.operands[0].data
        if type(value) in (int, float):
            return -value
    return None


def _tested_values(tests, *, nonzero=False):
    for test, branch in tests:
        left, right = test.operands
        for operand, bound in ((left, right), (right, left)):
            limit = _literal(bound)
            if limit is None:
                continue
            # At zero, equality and non-strict inequalities against zero hold.
            if not nonzero or (limit == 0 and branch != (test.data in ("==", "<=", ">="))):
                yield operand


def _site(roots, item: Obligation) -> tuple[ExprIR, list[tuple[ExprIR, bool]]]:
    # Analyze() identifies conditions by branch and other operands by index.
    # Type guards are transparent to a site's address.
    parts = iter(item.site.split("."))
    root = next(parts)
    if item.caller == "<module>":
        root += "." + next(parts)
    node = roots[(item.caller, root)]
    tests = []
    for part in parts:
        while node.op == "guard":
            node = node.operands[0]
        if node.op == "conditional":
            index = {"test": 0, "then": 1, "else": 2}[part]
            if index:
                tests.extend(_comparisons(node.operands[0], index == 1))
        else:
            index = int(part)
            if node.op in ("and", "or") and index == 1:
                tests.extend(_comparisons(node.operands[0], node.op == "and"))
            elif node.op == "summarize":
                for _, _, value, guard, _ in node.data["fields"]:
                    if index == value and guard is not None:
                        tests.extend(_comparisons(node.operands[guard], True))
                        break
        node = node.operands[index]
    while node.op == "guard":
        node = node.operands[0]
    return node, tests


def _divisor_advice(item: Obligation, denominator: ExprIR, tests: list[ExprIR]) -> tuple[str, str]:
    name = _render(denominator)
    if item.status == "refuted":
        return (f"The divisor {name} is zero whenever this operation is reached and its operands return.",
                "Handle zero before this operation according to the required behavior.")

    if denominator.typ == ANY:
        return (f"The divisor {name} has dynamic type Any.",
                "Establish the expected numeric type at the boundary and handle zero on that value.")

    value = denominator
    while value.op == "guard":
        value = value.operands[0]
    if denominator in tests and value.op == "name":
        return (f"This path already tests the divisor {name} against zero.",
                "Keep the guard and test the specified zero behavior. The static obligation is still open.")
    if denominator in tests and value.op == "call":
        return (f"The zero test and the operation evaluate {name} in separate calls.",
                "If both should use one observation, evaluate it once and use that value for the check and "
                "the operation. Keep other effects in their original branches and preserve the specified zero case.")
    elif value.op == "call":
        guarded_inputs = [_render(arg) for arg in value.operands[1:]
                          if arg.op == "name" and arg in tests]
        if guarded_inputs:
            detail = f"The branch tests {guarded_inputs[0]} against zero. The divisor is the result of {name}."
        else:
            detail = f"The checker has no nonzero guarantee for the result of {name} at this site."
    elif value.op == "name":
        detail = f"The checker has no nonzero guarantee for {name} at this site."
        return (detail, f"Test {name} against zero before the operation and implement the specified zero case.")
    else:
        detail = f"The checker has no nonzero guarantee for the expression {name} at this site."

    suggestion = ("Pass the operands once, in their current order, to a helper. Test its divisor parameter "
                  "against zero, use that same parameter in the operation, and implement the specified zero case.")
    if denominator.typ == FLOAT:
        suggestion += " Variable Float guards may still need runtime checks."
    return detail, suggestion


def _argument_advice(function: StmtIR, call: ExprIR, tests, item: Obligation,
                     *, conditional_guarantees: bool) -> dict | None:
    bound_clause = int_comparison(function.requires) if function.requires is not None else None
    if bound_clause is None:
        return None
    parameter, operator, bound = bound_clause
    index = next(i for i, (name, _) in enumerate(function.params) if name == parameter)
    arg = call.operands[index + 1]
    expression = _render(arg)
    required = f"{expression} {operator} {bound}"
    detail = f"{expression} supplies parameter {parameter} in {function.name}."
    if item.status == "refuted":
        detail += f" The bound {required} fails whenever this call is reached and its arguments return."
    else:
        detail += f" The checker cannot establish {required} at this call."
        tested = list(_tested_values(tests))
        if arg.op == "call":
            guarded = next((a.data for a in arg.operands[1:] if a.op == "name" and a in tested), None)
            if guarded is not None:
                detail += f" The branch tests the producer's input {guarded}."
    suggestion = (f"Check {required} on the value passed to {function.name}. "
                  "Preserve the required behavior for values outside the bound.")
    if arg.op == "call" and item.status == "unknown":
        suggestion = f"Evaluate {expression} once and test its result before the call."
        if conditional_guarantees:
            suggestion += f" A contract relating the producer's result to its input could also establish {required}."
        suggestion += " Preserve the required behavior outside the bound."
    return {"parameter": parameter, "argument": expression, "type": str(arg.typ),
            "requirement": item.requirement, "actual_requirement": required,
            "detail": detail, "suggestion": suggestion}


def guidance(program: ProgramIR, analysis: Analysis, *, conditional_guarantees: bool = True) -> list[dict]:
    """Offer a repair direction at open divisor and simple native Int precondition sites."""
    unresolved = [item for item in analysis.obligations
                  if item.kind in ("nonzero", "requires") and item.status != "proved"]
    if not unresolved:
        return []
    roots = _roots(program)
    functions = {s.name: s for s in program.statements if s.op == "fn"}
    rows = []
    for item in unresolved:
        node, tests = _site(roots, item)
        if item.kind == "nonzero":
            denominator = node.operands[1]
            detail, suggestion = _divisor_advice(item, denominator, list(_tested_values(tests, nonzero=True)))
            advice = {"denominator": _render(denominator), "type": str(denominator.typ),
                      "detail": detail, "suggestion": suggestion}
        else:
            advice = _argument_advice(functions[item.target], node, tests, item,
                                      conditional_guarantees=conditional_guarantees)
            if advice is None:
                continue
        rows.append({"caller": item.caller, "site": item.site, "kind": item.kind,
                     "target": item.target, "status": item.status, **advice})
    return rows
