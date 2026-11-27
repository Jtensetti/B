"""Small independent B syntax tree. No Python source is evaluated as B source."""
from __future__ import annotations
from dataclasses import dataclass
from functools import cache
from typing import Any
from lark import Lark, Transformer
from lark.exceptions import LarkError, UnexpectedCharacters, UnexpectedToken, VisitError
from importlib import resources
import re

@dataclass(frozen=True)
class Expr:
    kind: str
    parts: tuple[Any, ...]

@dataclass(frozen=True)
class Stmt:
    kind: str
    parts: tuple[Any, ...]

class ToModel(Transformer):
    def start(self, values): return list(values)
    def names(self, xs): return [str(x) for x in xs]
    def permit_stmt(self, xs): return Stmt("permit", (tuple(xs[0]) if xs and xs[0] is not None else (),))
    def unit_base_stmt(self, xs): return Stmt("unit_base", (tuple(xs[0]),))
    def unit_scale_stmt(self, xs):
        name, factor_expr, base = xs
        return Stmt("unit_scale", (str(name), float(factor_expr.parts[0]), str(base)))
    def currency_stmt(self, xs): return Stmt("currency", (tuple(xs[0]),))
    def record_field(self, xs): return (str(xs[0]), xs[1])
    def record_stmt(self, xs): return Stmt("record", (str(xs[0]), tuple(xs[1:])))
    def record_entry_kv(self, xs): return (str(xs[0]), xs[1])
    def record_entry_shorthand(self, xs): return (str(xs[0]), Expr("name", (str(xs[0]),)))
    def record_lit(self, xs): return Expr("record_lit", tuple(xs))
    def record_with(self, xs): return ("record_with", tuple(xs))
    def probe_stmt(self, xs): return Stmt("probe", (xs[0],))
    def expect_stmt(self, xs): return Stmt("expect", (xs[0], str(xs[1]), str(xs[2])))
    def facet(self, xs): return (str(xs[0]), str(xs[1]))
    def facet_list(self, xs): return tuple(xs)
    def fn_pure(self, xs): return ("pure", True)
    def fn_requires(self, xs): return ("requires", xs[0])
    def fn_ensures(self, xs): return ("ensures", xs[0])
    def path(self, xs): return ".".join(map(str, xs))
    def type_expr(self, xs): return (str(xs[0]), tuple(x for x in xs[1:] if x is not None))
    def params(self, xs): return [x for x in xs if x is not None]
    def type_list(self, xs): return list(xs)
    def param(self, xs): return (str(xs[0]), xs[1])
    def call_args(self, xs): return [x for x in xs if x is not None]
    def named_arg(self, xs): return ("named", str(xs[0]), xs[1])
    def pos_arg(self, xs): return xs[0]
    def number(self, xs):
        token = xs[0]
        try:
            value = float(token) if "." in token else int(token)
        except ValueError as exc:
            raise LarkError(f"Invalid numeric literal at line {token.line}, column {token.column}") from exc
        return Expr("literal", (value,))
    def string(self, xs):
        import json
        token = xs[0]
        try:
            return Expr("literal", (json.loads(token),))
        except json.JSONDecodeError as exc:
            raise LarkError(f"Invalid string literal at line {token.line}, column {token.column}: {exc.msg}") from exc
    def true(self, _): return Expr("literal", (True,))
    def false(self, _): return Expr("literal", (False,))
    def none(self, _): return Expr("literal", (None,))
    def identifier(self, xs): return Expr("name", (str(xs[0]),))
    def grouped(self, xs): return xs[0]
    def list_items(self, xs): return Expr("list", tuple(x for x in xs if x is not None))
    def list_comp(self, xs):
        body, binder, source, guard = xs
        return Expr("list_comp", (body, str(binder), source, guard))
    def list_bracket(self, xs):
        if not xs or xs[0] is None:
            return Expr("list", ())
        return xs[0]
    def pair(self, xs): return (xs[0], xs[1])
    def pairs(self, xs): return [x for x in xs if x is not None]
    def dict_literal(self, xs): return Expr("dict", tuple(xs[0]) if xs and xs[0] is not None else ())
    def attribute(self, xs): return ("attr", str(xs[0]))
    def invoke(self, xs): return ("invoke", tuple(xs[0]) if xs and xs[0] is not None else ())
    def lookup(self, xs): return ("lookup", xs[0])
    def postfix(self, xs):
        base = xs[0]
        for kind, val in xs[1:]: base = Expr(kind, (base, val))
        return base
    def conditional(self, xs): return Expr("conditional", tuple(xs))
    def let_expr(self, xs): return Expr("let_expr", (str(xs[0]), xs[1], xs[2], xs[3]))
    def pipe(self, xs):
        left, right = xs
        if right.kind == "invoke":
            target, args = right.parts
            return Expr("invoke", (target, (left, *args)))
        return Expr("invoke", (right, (left,)))
    def unit_tag(self, xs): return Expr("unit_tag", (xs[0], str(xs[1])))
    def unit_convert(self, xs): return Expr("unit_convert", (xs[0], str(xs[1])))
    def case_row(self, xs):
        operator, threshold, value = xs
        return str(operator), threshold, value

    def case_table(self, xs):
        _, name, *rows, fallback = xs
        if name in {"true", "false", "none", "if", "not"}:
            raise LarkError(f"Decision table pivot '{name}' must be usable as an ordinary variable "
                            f"at line {name.line}, column {name.column}")
        pivot = Expr("name", (str(name),))
        for operator, threshold, value in reversed(rows):
            test = Expr("cmp", (pivot, operator, threshold))
            fallback = Expr("conditional", (test, value, fallback))
        return fallback

    def summary_count(self, xs):
        return "count", None, xs[0], None

    def summary_sum(self, xs):
        value, guard = xs
        return "sum", value, guard, None

    def summary_extremum(self, xs):
        reducer, value, guard, default = xs
        return str(reducer), value, guard, default

    def default_num(self, xs):
        raw = str(xs[0])
        try:
            return float(raw) if "." in raw else int(raw)
        except ValueError as exc:
            raise LarkError("summarize default exceeds the supported numeric literal size") from exc

    def default_negative_num(self, xs):
        return -self.default_num(xs)

    def summary_field(self, xs):
        label, reduction = xs
        return (str(label), *reduction)

    def summary(self, xs):
        binder, source, *fields = xs
        return Expr("summarize", (str(binder), source, tuple(fields)))

    def history_count(self, xs):
        mode, past, current, source, predicate = xs
        return Expr("history_count", (str(mode), str(past), str(current), source, predicate))

    def coalesce(self, xs): return Expr("coalesce", tuple(xs))
    def not_op(self, xs): return Expr("not", (xs[0],))
    def neg(self, xs): return Expr("neg", (xs[0],))
    def add(self, xs): return Expr("add", tuple(xs))
    def subtract(self, xs): return Expr("sub", tuple(xs))
    def multiply(self, xs): return Expr("mul", tuple(xs))
    def divide(self, xs): return Expr("div", tuple(xs))
    def modulo(self, xs): return Expr("mod", tuple(xs))
    def and_op(self, xs): return Expr("and", tuple(xs))
    def or_op(self, xs): return Expr("or", tuple(xs))
    def comparison(self, xs): return Expr("cmp", (xs[0], str(xs[1]), xs[2]))
    def foreign_stmt(self, xs):
        facets = xs[3] if len(xs) > 3 and xs[3] is not None else ()
        return Stmt("foreign", (xs[0], xs[1] or [], xs[2], facets))
    def use_stmt(self, xs): return Stmt("use", (str(xs[0]), xs[1], str(xs[2])))
    def js_use(self, xs): return Stmt("use", ("js", xs[0], str(xs[1])))
    def js_string_use(self, xs):
        import json
        return Stmt("use", ("js", json.loads(str(xs[0])), str(xs[1])))
    def adopt_stmt(self, xs): return Stmt("adopt", (str(xs[0]), str(xs[1])))
    def let_stmt(self, xs): return Stmt("let", (str(xs[0]), xs[1], xs[2]))
    def fn_stmt(self, xs):
        flags = {key: value for item in xs[3:-1] if item is not None for key, value in (item,)}
        return Stmt("fn", (str(xs[0]), xs[1] or [], xs[2], xs[-1],
                            bool(flags.get("pure", False)), flags.get("requires"), flags.get("ensures")))
    def next_stmt(self, xs): return Stmt("next", (str(xs[0]), xs[1], xs[2]))
    def also_args(self, xs):
        values = []
        for literal in xs:
            if literal.kind == "neg":
                number, = literal.parts
                values.append(-number.parts[0])
            else:
                values.append(literal.parts[0])
        return tuple(values)
    def also_stmt(self, xs): return Stmt("also", (str(xs[0]), xs[1] or (), tuple(xs[2] or ())))
    def print_stmt(self, xs): return Stmt("print", (xs[0],))
    def assert_stmt(self, xs): return Stmt("assert", (xs[0],))

_GRAMMAR = resources.files("b_lang").joinpath("syntax.lark").read_text()
_PARSER = Lark(_GRAMMAR, parser="lalr", maybe_placeholders=True)


@cache
def positioned_parser():
    """Only source-rewriting callers need token offsets."""
    return Lark(_GRAMMAR, parser="lalr", maybe_placeholders=True, propagate_positions=True)


def _strip_enclosed_newlines(source: str) -> str:
    """Replace newlines inside (...) and [...] (when innermost delimiter is not {) with spaces,
    preserving exact 1-to-1 character offsets for source rewriters."""
    if "\n" not in source:
        return source
    out: list[str] = []
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in source:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
        elif ch in "([{":
            stack.append(ch)
            out.append(ch)
        elif ch in ")]}":
            if stack:
                stack.pop()
            out.append(ch)
        elif ch == "\n" and stack and stack[-1] in ("(", "["):
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def parser_input(source: str) -> str:
    # Preserve character offsets for source rewriters, including CRLF pairs.
    if "\r" in source:
        source = re.sub(r"\r(?!\n)", "\n", source)
    source = _strip_enclosed_newlines(source)
    return source + ("\n" if source and not source.endswith("\n") else "")


def parse(source: str) -> list[Stmt]:
    try:
        tree = _PARSER.parse(parser_input(source))
    except UnexpectedCharacters as error:
        if error.char == "#":
            raise LarkError(f"Free-form # comments were removed in B 0.14 (line {error.line}, "
                            f"column {error.column}). Run 'b migrate-comments FILE' to print migrated source.") from error
        raise
    except UnexpectedToken as error:
        if error.token.type == "RBRACE" and (
            "_ROW_SEMI" in error.accepts or {"COMP", "ELSE"} <= error.accepts
        ):
            raise LarkError(f"Expected a final 'else => result' row before '}}' "
                            f"at line {error.line}, column {error.column}") from error
        raise
    try:
        return ToModel().transform(tree)
    except VisitError as error:
        if isinstance(error.orig_exc, (LarkError, RecursionError)):
            raise error.orig_exc from error
        raise
