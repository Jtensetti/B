"""Import a strictly limited Python *expression* as a native B function.

No target module or function is evaluated. We locate its .py source with
PathFinder, read and parse it, and translate only a deliberately small,
side-effect-free AST subset. This is not a sandbox, a semantic equivalence proof
for arbitrary Python, or proof of a function's *intended* algorithm.
"""
from __future__ import annotations

import ast
import hashlib
import math
import sys
from dataclasses import dataclass
from importlib.machinery import PathFinder
from importlib.util import find_spec as meta_find_spec
from pathlib import Path

from .model import Expr, Stmt
from .types import BError


TYPE_NAMES = {"int": "Int", "float": "Float", "bool": "Bool", "str": "Text"}
ARITHMETIC = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div", ast.Mod: "mod"}
COMPARATORS = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}


def _source_file(module: str) -> Path:
    """Locate standard filesystem modules without importing their parents.

    PathFinder still consults Python import configuration. This is not safe
    against hostile custom path hooks; source provenance is not attestation.
    """
    pieces = module.split(".")
    if not pieces or any(not p.isidentifier() for p in pieces):
        raise BError("E_ADOPT", "Expected a dotted Python module name")
    search = None
    spec = None
    qualified = ""
    for piece in pieces:
        qualified = f"{qualified}.{piece}" if qualified else piece
        spec = PathFinder.find_spec(qualified, search)
        # PEP 660 editable installations may be exposed by a MetaPathFinder
        # instead of a sys.path entry. Resolve ONLY the top-level package via
        # find_spec: never invoke find_spec on a dotted name (which could import
        # parent __init__.py). Ordinary compiler import hooks remain trusted.
        if spec is None and "." not in qualified:
            spec = meta_find_spec(qualified)
        if spec is None:
            raise BError("E_ADOPT", f"Python source module {qualified} was not found")
        search = spec.submodule_search_locations
    if not spec or not spec.origin or not spec.origin.endswith(".py"):
        raise BError("E_ADOPT", f"{module} has no Python .py source to adopt")
    return Path(spec.origin)


def _annotation(expr: ast.expr | None) -> tuple[str, tuple]:
    if not isinstance(expr, ast.Name) or expr.id not in TYPE_NAMES:
        raise BError("E_ADOPT", "Adopted functions require explicit int/float/bool/str annotations")
    return TYPE_NAMES[expr.id], ()


def _expression(node: ast.expr, variables: set[str]) -> Expr:
    if isinstance(node, ast.Constant):
        item = node.value
        if type(item) not in (int, float, bool, str):
            raise BError("E_ADOPT", "Only Int, Float, Bool and Text literals can be adopted")
        if type(item) is float and not math.isfinite(item):
            raise BError("E_ADOPT", "Non-finite Float constants cannot be adopted")
        return Expr("literal", (item,))
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise BError("E_ADOPT", f"Non-parameter reference {node.id!r} cannot be adopted")
        return Expr("name", (node.id,))
    if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.USub, ast.Not):
        return Expr("neg" if isinstance(node.op, ast.USub) else "not", (_expression(node.operand, variables),))
    if isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
        return Expr(ARITHMETIC[type(node.op)], (
            _expression(node.left, variables), _expression(node.right, variables)))
    if isinstance(node, ast.BoolOp) and type(node.op) in (ast.And, ast.Or) and len(node.values) >= 2:
        op = "and" if isinstance(node.op, ast.And) else "or"
        result = _expression(node.values[0], variables)
        for value in node.values[1:]:
            result = Expr(op, (result, _expression(value, variables)))
        return result
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        op = COMPARATORS.get(type(node.ops[0]))
        if op is not None:
            return Expr("cmp", (_expression(node.left, variables), op, _expression(node.comparators[0], variables)))
    if isinstance(node, ast.IfExp):
        return Expr("conditional", (_expression(node.test, variables),
                   _expression(node.body, variables), _expression(node.orelse, variables)))
    raise BError("E_ADOPT", f"Python expression {type(node).__name__} cannot be statically adopted")


@dataclass(frozen=True)
class Adopted:
    source_module: str
    source_function: str
    source_file: str
    sha256: str
    statement: Stmt


def _extract(module: str, function: str, source: bytes, source_file: str, alias: str) -> Adopted:
    try:
        tree = ast.parse(source, filename=source_file)
    except (UnicodeError, SyntaxError) as e:
        raise BError("E_ADOPT", f"Cannot parse Python source: {e}") from e
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function]
    if len(defs) != 1 or not isinstance(defs[0], ast.FunctionDef):
        raise BError("E_ADOPT", f"Expected exactly one top-level synchronous function {function}")
    node = defs[0]
    arguments = node.args
    if (node.decorator_list or arguments.defaults or arguments.kw_defaults or arguments.kwonlyargs or
            arguments.vararg or arguments.kwarg or getattr(node, "type_params", ()) or node.type_comment):
        raise BError("E_ADOPT", "Decorators, defaults, keyword-only/variadic arguments and generics are not adoptable")
    arg_nodes = [*arguments.posonlyargs, *arguments.args]
    params = [(arg.arg, _annotation(arg.annotation)) for arg in arg_nodes]
    if len({name for name, _ in params}) != len(params):
        raise BError("E_ADOPT", "Duplicate argument name")
    ret = _annotation(node.returns)
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and type(body[0].value.value) is str:
        body.pop(0)  # A docstring is inert metadata, not executable logic.
    if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
        raise BError("E_ADOPT", "Only a single return expression (plus an optional docstring) is adoptable")
    expr = _expression(body[0].value, {name for name, _ in params})
    statement = Stmt("fn", (alias, params, ret, expr, True, None, None))
    return Adopted(module, function, source_file, hashlib.sha256(source).hexdigest(), statement)


def adopt_python(fullname: str, alias: str) -> Adopted:
    module, dot, function = fullname.rpartition(".")
    if not dot or not function.isidentifier():
        raise BError("E_ADOPT", "Expected py:module.name.function")
    path = _source_file(module)
    try:
        source = path.read_bytes()
    except OSError as e:
        raise BError("E_ADOPT", f"Cannot read Python source for {fullname}: {e}") from e
    return _extract(module, function, source, str(path), alias)


def audit_adoptable(module: str) -> dict:
    """Describe compatible *top-level functions* without importing the module."""
    path = _source_file(module)
    try:
        source = path.read_bytes()
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as e:
        raise BError("E_ADOPT", f"Cannot inspect source of {module}: {e}") from e
    names = sorted({n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")})
    accepted, rejected = [], {}
    for name in names:
        try:
            candidate = _extract(module, name, source, str(path), name)
            # Check B type rules too, not only AST shape.
            from .compiler import Compiler
            ir = Compiler().statement(candidate.statement)
            if ir.effects:
                raise BError("E_ADOPT", "B's effect checker could not establish effect-free code")
            accepted.append(name)
        except BError as e:
            rejected[name] = {"code": e.code, "reason": e.message}
    return {"target": f"py:{module}", "source": str(path),
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "public_top_level_functions": len(names), "adoptable": len(accepted),
            "accepted": accepted, "rejected": rejected,
            "note": "AST subset and B type checks only; not a proof of original Python intent"}
