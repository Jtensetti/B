"""Small independent B syntax tree. No Python source is evaluated as B source."""
from __future__ import annotations
from dataclasses import dataclass
from functools import cache
from typing import Any
from lark import Lark, Transformer
from lark.exceptions import LarkError, UnexpectedCharacters, UnexpectedToken, VisitError
from importlib import resources
import re
import unicodedata

@dataclass(frozen=True)
class Expr:
    kind: str
    parts: tuple[Any, ...]

@dataclass(frozen=True)
class Quantity:
    """A literal with a unit in an example, such as 9.5 gal."""
    value: int | float
    unit: tuple

@dataclass(frozen=True)
class Stmt:
    kind: str
    parts: tuple[Any, ...]

class ToModel(Transformer):
    def start(self, values): return list(values)
    def names(self, xs): return [str(x) for x in xs]
    def permit_stmt(self, xs): return Stmt("permit", (tuple(xs[0]) if xs and xs[0] is not None else (),))
    def fn_pure(self, xs): return ("pure", True)
    def fn_requires(self, xs): return ("requires", xs[0])
    def fn_ensures(self, xs): return ("ensures", xs[0])
    def path(self, xs): return ".".join(map(str, xs))
    def type_expr(self, xs): return (str(xs[0]), tuple(x for x in xs[1:] if x is not None))
    def params(self, xs): return list(xs)
    def type_list(self, xs): return list(xs)
    def param(self, xs): return (str(xs[0]), xs[1])
    def args(self, xs): return list(xs)
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
    def record_field(self, xs): return (str(xs[0]), xs[1])
    def record_entry(self, xs): return (str(xs[0]), xs[1])
    def record_stmt(self, xs): return Stmt("record", (str(xs[0]), tuple(xs[1:])))
    def record_literal(self, xs): return Expr("record", tuple(xs))
    def binders(self, xs): return tuple(str(x) for x in xs if x is not None)
    def list_each(self, xs):
        value, binders, source, condition = xs
        return Expr("each", ("list", None, value, binders, source, condition))
    def dict_each(self, xs):
        key, value, binders, source, condition = xs
        return Expr("each", ("dict", key, value, binders, source, condition))
    def list_literal(self, xs): return Expr("list", tuple(xs[0]) if xs and xs[0] is not None else ())
    def pair(self, xs): return (xs[0], xs[1])
    def pairs(self, xs): return list(xs)
    def dict_literal(self, xs): return Expr("dict", tuple(xs[0]) if xs and xs[0] is not None else ())
    def attribute(self, xs): return ("attr", str(xs[0]))
    def invoke(self, xs): return ("invoke", tuple(xs[0]) if xs and xs[0] is not None else ())
    def lookup(self, xs): return ("lookup", xs[0])
    def postfix(self, xs):
        base = xs[0]
        for kind, val in xs[1:]: base = Expr(kind, (base, val))
        return base
    def conditional(self, xs): return Expr("conditional", tuple(xs))
    def case_row(self, xs):
        operator, threshold, value = xs
        return str(operator), threshold, value

    def case_table(self, xs):
        _, name, *rows, fallback = xs
        # These spellings start a literal, operator or conditional where the
        # equivalent ordinary comparison must read a variable.
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
        reducer, value, default = xs
        return str(reducer), value, None, default

    def default_int(self, xs):
        try:
            return int(xs[0])
        except ValueError as exc:
            raise LarkError("summarize default exceeds the supported integer literal size") from exc

    def default_negative_int(self, xs):
        return -self.default_int(xs)

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
    def foreign_type_stmt(self, xs): return Stmt("foreign_type", (str(xs[0]), xs[1]))
    def foreign_stmt(self, xs): return Stmt("foreign", (xs[0], xs[1] or [], xs[2]))
    def foreign_on_stmt(self, xs): return Stmt("foreign_on", (xs[0], xs[1] or [], xs[2], tuple(str(x) for x in xs[3:])))
    def use_stmt(self, xs): return Stmt("use", (str(xs[0]), xs[1], str(xs[2])))
    def js_use(self, xs): return Stmt("use", ("js", xs[0], str(xs[1])))
    def js_string_use(self, xs):
        import json
        return Stmt("use", ("js", json.loads(str(xs[0])), str(xs[1])))
    def go_use(self, xs):
        import json
        return Stmt("use", ("go", json.loads(str(xs[0])), str(xs[1])))
    def rust_use(self, xs):
        import json
        return Stmt("use", ("rust", json.loads(str(xs[0])), str(xs[1])))
    def cs_use(self, xs):
        import json
        return Stmt("use", ("cs", json.loads(str(xs[0])), str(xs[1])))
    def adopt_stmt(self, xs): return Stmt("adopt", (str(xs[0]), str(xs[1])))
    def let_stmt(self, xs): return Stmt("let", (str(xs[0]), xs[1], xs[2]))
    def fn_stmt(self, xs):
        flags = {key: value for item in xs[3:-1] if item is not None for key, value in (item,)}
        return Stmt("fn", (str(xs[0]), xs[1] or [], xs[2], xs[-1],
                            bool(flags.get("pure", False)), flags.get("requires"), flags.get("ensures")))
    def local(self, xs): return (str(xs[0]), xs[1], xs[2])
    def fn_body(self, xs):
        *bindings, result = xs
        return Expr("locals", (tuple(bindings), result)) if bindings else result
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
    def also_like(self, xs): return ("like", xs[0] or ())
    def also_stmt(self, xs):
        like = xs[2][1] if xs[2] is not None else None
        return Stmt("also", (str(xs[0]), xs[1] or (), tuple(xs[3] or ()), like))
    def domain_stmt(self, xs): return Stmt("domain", (str(xs[0]), xs[1]))
    def group_stmt(self, xs): return Stmt("group", (str(xs[0]), str(xs[1]), xs[2]))
    def know_stmt(self, xs): return Stmt("know", (str(xs[0]),))
    def unit(self, xs): return (str(xs[0]), None if xs[1] is None else str(xs[1]))
    def quantity(self, xs): return Expr("quantity", (xs[0].parts[0], xs[1]))
    def convert(self, xs): return Expr("convert", (xs[0], xs[1]))
    def membership(self, xs):
        container = xs[1]
        if isinstance(container, Expr) and container.kind == "name":
            return Expr("member", (xs[0], container.parts[0]))  # a group, or a collection by name
        return Expr("contains", (xs[0], container))
    def learned_stmt(self, xs):
        return Stmt("learn", (str(xs[0]), xs[1] or [], xs[2], xs[3] is not None))
    def quantity_value(self, xs): return ("quantity", xs[0].parts[0], xs[1])
    def example_args(self, xs): return tuple(self._example_value(x) for x in xs)
    def _example_value(self, node):
        if isinstance(node, tuple) and node and node[0] == "quantity":
            return Quantity(node[1], node[2])
        return self.also_args([node])[0]
    def example_stmt(self, xs):
        name, arguments, operator, value, tolerance, previous = xs
        if str(operator) != "==":
            raise LarkError(f"An example states one result with ==, found {operator} "
                            f"at line {operator.line}, column {operator.column}")
        optional = lambda node: None if node is None else self._example_value(node)
        return Stmt("example", (str(name), arguments or (), self._example_value(value), optional(previous),
                                previous is not None, optional(tolerance)))
    def print_stmt(self, xs): return Stmt("print", (xs[0],))
    def assert_stmt(self, xs): return Stmt("assert", (xs[0],))

_GRAMMAR = resources.files("b_lang").joinpath("syntax.lark").read_text()


class _JoinLines:
    """Python's implicit line joining: a newline inside () or [] continues the line.

    Braces keep their newlines, because records, decision tables and summaries
    use a newline as a separator between their entries.
    """
    always_accept = ("_NL",)

    def process(self, stream):
        stack = []
        for token in stream:
            kind = token.type
            if kind in ("LPAR", "LSQB", "LBRACE"):
                stack.append(kind)
            elif kind in ("RPAR", "RSQB", "RBRACE") and stack:
                stack.pop()
            elif kind == "_NL" and stack and stack[-1] in ("LPAR", "LSQB"):
                continue
            yield token
_PARSER = Lark(_GRAMMAR, parser="lalr", maybe_placeholders=True, postlex=_JoinLines())


@cache
def positioned_parser():
    """Only source-rewriting callers need token offsets."""
    return Lark(_GRAMMAR, parser="lalr", maybe_placeholders=True, propagate_positions=True,
                postlex=_JoinLines())


_CONTINUED = re.compile(r"\r?\n[ \t]*(?=then\b|else\b(?![ \t]*=>))")


def parser_input(source: str) -> str:
    # Preserve character offsets for source rewriters, including CRLF pairs.
    if "\r" in source:
        source = re.sub(r"\r(?!\n)", "\n", source)
    # A line starting with `then` or `else` continues the if above it. Spaces of the
    # same length keep every offset; strings cannot contain a raw newline.
    source = _CONTINUED.sub(lambda m: " " * len(m.group(0)), source)
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
        # At the end of a comparison row the grammar expects a separator.
        # After the separator it expects the next comparison or the fallback.
        if error.token.type == "RBRACE" and (
            "_ROW_SEMI" in error.accepts or {"COMP", "ELSE"} <= error.accepts
        ):
            raise LarkError(f"Expected a final 'else => result' row before '}}' "
                            f"at line {error.line}, column {error.column}") from error
        raise
    for token in tree.scan_values(lambda t: getattr(t, "type", None) == "NAME"):
        if not token.isidentifier() or unicodedata.normalize("NFKC", token) != token:
            raise LarkError(f"Name {str(token)!r} at line {token.line} is not in normalized form; "
                            "write it with ordinary letters")
    try:
        return ToModel().transform(tree)
    except VisitError as error:
        if isinstance(error.orig_exc, (LarkError, RecursionError)):
            raise error.orig_exc from error
        raise
