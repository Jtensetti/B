"""Expand literal equality edits using the target function's declared parameters."""
import re

from lark.exceptions import LarkError

from .compiler import compile_b
from .handoff import Handoff
from .model import Expr, _PARSER, parse
from .types import BError


# Use the ordinary B token definitions. Whitespace separates the fields of a row.
_NAME = _PARSER.get_terminal("NAME").pattern.to_regexp()
_NUMBER = _PARSER.get_terminal("NUMBER").pattern.to_regexp()
_STRING = _PARSER.get_terminal("ESCAPED_STRING").pattern.to_regexp()
_LITERAL = rf"(?:-?{_NUMBER}|{_STRING}|true|false|none)"
_ROW = re.compile(rf"(?P<fn>{_NAME})[ \t]+(?:(?P<param>{_NAME})[ \t]+)?"
                  rf"(?P<key>{_LITERAL})[ \t]+(?P<value>{_LITERAL})")


def _literal_identity(expr: Expr):
    # Python equality conflates 1, 1.0 and True, and both signs of zero.
    negative = expr.kind == "neg"
    if negative:
        expr = expr.parts[0]
    if expr.kind != "literal":
        return None
    value = expr.parts[0]
    if negative:
        if type(value) not in (int, float):
            return None
        value = -value
    return type(value), repr(value)


def _same_leading_branch(body, predicate, replacement):
    if body.kind != "conditional":
        return False
    test, value, _ = body.parts
    return (test.kind == "cmp" and test.parts[:2] == predicate.parts[:2]
            and _literal_identity(test.parts[2]) == _literal_identity(predicate.parts[2])
            and _literal_identity(value) == _literal_identity(replacement))


def _append(source, directives):
    if not directives:
        return source
    ending = re.search(r"\r\n|\r|\n", source)
    newline = ending.group() if ending else "\n"
    separator = "" if source.endswith(("\n", "\r")) else newline
    return source + separator + newline.join(directives) + newline


def prepare_shorthand(source: str, rows: str, *, strict: bool = False) -> tuple[str, Handoff | None]:
    """Return the canonical pending source and its checked, one-shot handoff."""
    try:
        statements = parse(source)
    except LarkError as error:
        raise BError("E_SYNTAX", str(error)) from error
    except RecursionError as error:
        raise BError("E_DEPTH", "Source exceeds the compiler’s nesting capacity") from error
    functions = {s.parts[0]: s for s in statements if s.kind == "fn"}
    pending = any(s.kind == "next" for s in statements)
    batch = []
    fresh = []
    seen = set()
    for number, line in enumerate(re.split(r"\r\n?|\n", rows), 1):
        line = line.strip(" \t")
        if not line:
            continue
        if pending:
            raise BError("E_SHORTHAND_PENDING", "This source already contains pending edits. "
                         "Review them with 'b next' before submitting a shorthand batch.")
        match = _ROW.fullmatch(line)
        if match is None:
            raise BError("E_SHORTHAND", f"Row {number}: expected 'function [parameter] key value' "
                         "with two B scalar literals")
        target, parameter, key, value = match.group("fn", "param", "key", "value")
        if target not in functions:
            raise BError("E_SHORTHAND", f"Row {number}: no source function named {target!r}")
        if target in seen:
            raise BError("E_HANDOFF", f"Row {number}: multiple instructions for {target!r} in the same batch")
        seen.add(target)
        fn = functions[target]
        names = [name for name, _ in fn.parts[1]]
        if not names:
            raise BError("E_SHORTHAND", f"Row {number}: {target} has no parameter to compare")
        if parameter is None and len(names) == 1:
            parameter = names[0]
        if parameter not in names:
            reason = "name the parameter explicitly" if parameter is None else f"unknown parameter {parameter!r}"
            raise BError("E_SHORTHAND", f"Row {number}: {target}: {reason}. Choose from {', '.join(names)}")
        directive = f"next {target} when {parameter} == {key} => {value}"
        try:
            _, predicate, replacement = parse(directive)[0].parts
        except (LarkError, ValueError) as error:
            raise BError("E_SHORTHAND", f"Row {number}: invalid B literal or parameter: {error}") from error
        if (predicate.kind != "cmp" or predicate.parts[1] != "=="
                or _literal_identity(predicate.parts[2]) is None or _literal_identity(replacement) is None):
            raise BError("E_SHORTHAND", f"Row {number}: key and value must be B scalar literals")
        if predicate.parts[0] != Expr("name", (parameter,)):
            raise BError("E_SHORTHAND", f"Row {number}: {parameter!r} cannot be read as a B parameter")
        batch.append(directive)
        if not _same_leading_branch(fn.parts[3], predicate, replacement):
            fresh.append(directive)

    # Validate even a repeated edit. In a mixed batch, removing already-applied
    # rows produces a different proposed program which must pass its own checks.
    expanded = _append(source, batch)
    checked = compile_b(expanded, strict=strict)
    if not fresh:
        return source, None
    if fresh != batch:
        expanded = _append(source, fresh)
        checked = compile_b(expanded, strict=strict)
    return expanded, checked.handoff


def expand_shorthand(source: str, rows: str, *, strict: bool = False) -> str:
    """Append checked ordinary next declarations, leaving existing behavior in place."""
    expanded, _ = prepare_shorthand(source, rows, strict=strict)
    return expanded
