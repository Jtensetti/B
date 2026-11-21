"""Small independent B syntax tree. No Python source is evaluated as B source."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from lark import Lark, Transformer, Token
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
    def let_stmt(self, xs): return Stmt("let", (str(xs[0]), xs[1], xs[2]))
    def fn_stmt(self, xs):
        return Stmt("fn", (str(xs[0]), xs[1] or [], xs[2], xs[3]))
    def print_stmt(self, xs): return Stmt("print", (xs[0],))
    def assert_stmt(self, xs): return Stmt("assert", (xs[0],))

_PARSER = Lark(resources.files("b_lang").joinpath("syntax.lark").read_text(), parser="lalr", maybe_placeholders=True)

def parse(source: str) -> list[Stmt]:
    return ToModel().transform(_PARSER.parse(source + ("\n" if source and not source.endswith("\n") else "")))
