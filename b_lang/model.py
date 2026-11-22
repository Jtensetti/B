"""Small independent B syntax tree. No Python source is evaluated as B source."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from lark import Lark, Transformer
from lark.exceptions import LarkError, UnexpectedToken, VisitError
from importlib import resources

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
        s = str(xs[0]); return Expr("literal", (float(s) if "." in s else int(s),))
    def string(self, xs):
        import json
        return Expr("literal", (json.loads(str(xs[0])),))
    def true(self, _): return Expr("literal", (True,))
    def false(self, _): return Expr("literal", (False,))
    def none(self, _): return Expr("literal", (None,))
    def identifier(self, xs): return Expr("name", (str(xs[0]),))
    def grouped(self, xs): return xs[0]
    def list_literal(self, xs): return Expr("list", tuple(xs[0]) if xs and xs[0] is not None else ())
    def pair(self, xs): return (xs[0], xs[1])
    def pairs(self, xs): return list(xs)
    def dict_literal(self, xs): return Expr("dict", tuple(xs[0]) if xs and xs[0] is not None else ())
    def attribute(self, xs): return ("attr", str(xs[0]))
    def invoke(self, xs): return ("invoke", tuple(xs[0]) if xs and xs[0] is not None else ())
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
    def foreign_stmt(self, xs): return Stmt("foreign", (xs[0], xs[1] or [], xs[2]))
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
    def print_stmt(self, xs): return Stmt("print", (xs[0],))
    def assert_stmt(self, xs): return Stmt("assert", (xs[0],))

_PARSER = Lark(resources.files("b_lang").joinpath("syntax.lark").read_text(), parser="lalr", maybe_placeholders=True)

def parse(source: str) -> list[Stmt]:
    try:
        tree = _PARSER.parse(source + ("\n" if source and not source.endswith("\n") else ""))
    except UnexpectedToken as error:
        # At the end of a comparison row the grammar expects a separator.
        # After the separator it expects the next comparison or the fallback.
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
