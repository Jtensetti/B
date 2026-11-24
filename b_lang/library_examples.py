"""Decisions about libraries: an `example` on an imported function.

    use py:b_examples.aviation as aviation
    foreign aviation.fuel_burn(Duration[h]) -> Volume[gal]
    example aviation.fuel_burn(2 h) == 19 gal within 0.01 gal

The example is a fact about a relative's library. B cannot evaluate foreign
code while it type checks, so the fact is checked where it stands in the
program, normally right after the import: a library whose behavior changed
stops the program before anything else runs. `b check --library-examples`
runs only these facts, each on its own, and reports every one.
"""
from __future__ import annotations

from .model import Expr, Quantity, Stmt
from .precedent import literal
from .types import BError


def _value_expr(value) -> Expr:
    if isinstance(value, Quantity):
        return Expr("quantity", (value.value, value.unit))
    return Expr("literal", (value,))


def _value_text(value) -> str:
    if isinstance(value, Quantity):
        name, per = value.unit
        return f"{literal(value.value)} {name}" + (f" per {per}" if per else "")
    return literal(value)


def _target(path: str) -> Expr:
    first, *rest = path.split(".")
    node = Expr("name", (first,))
    for member in rest:
        node = Expr("attr", (node, member))
    return node


def describe(statement: Stmt) -> str:
    name, arguments, value, _, _, tolerance = statement.parts
    text = f"example {name}({', '.join(_value_text(a) for a in arguments)}) == {_value_text(value)}"
    return text + (f" within {_value_text(tolerance)}" if tolerance is not None else "")


def to_checks(statements: list[Stmt]) -> list[Stmt]:
    """Turn examples of imported functions into checks that run in program order."""
    result = []
    for statement in statements:
        if statement.kind != "example" or "." not in statement.parts[0]:
            result.append(statement)
            continue
        name, arguments, value, _, has_previous, tolerance = statement.parts
        if has_previous:
            raise BError("E_EXAMPLE", f"{describe(statement)}: 'was' records a change to a B decision. "
                         "A library's result is whatever the library returns; state the new value instead")
        call = Expr("invoke", (_target(name), tuple(_value_expr(a) for a in arguments)))
        expected, margin, label = _value_expr(value), None if tolerance is None else _value_expr(tolerance), ""
        if isinstance(value, Quantity):
            # Compare in the unit the example is written in, so a failure reads in that unit.
            call = Expr("convert", (call, value.unit))
            expected = Expr("literal", (value.value,))
            if margin is not None:
                margin = Expr("convert", (margin, value.unit))
            label = " " + value.unit[0] + (f" per {value.unit[1]}" if value.unit[1] else "")
        result.append(Stmt("library_example", (call, expected, margin, describe(statement) + "\t" + label)))
    return result


def run_each(program) -> list[dict]:
    """Run every library example on its own, with only the imports it needs."""
    from dataclasses import replace

    from .lowering import PythonLowerer
    from .runtime import BExampleError

    setup = [s for s in program.statements if s.op in ("import", "foreign", "permit")]
    results = []
    for check in (s for s in program.statements if s.op == "example_check"):
        text = check.target.partition("\t")[0]
        module = PythonLowerer().lower(replace(program, statements=(*setup, check)))
        try:
            exec(compile(module, "<B library example>", "exec"), {"__name__": "__b_library_example__"})
            results.append({"example": text, "status": "holds"})
        except BExampleError as exc:
            results.append({"example": text, "status": "changed", "message": str(exc)})
        except Exception as exc:  # the library itself failed or is missing
            results.append({"example": text, "status": "error", "message": f"{type(exc).__name__}: {exc}"})
    return results
