"""Conservative, non-evaluating extraction of Python annotations and overloads.

This reads a module's adjacent .pyi when present, otherwise its .py source.
Only functions whose entire relevant signatures B understands are registered;
no annotations are executed. Importlib.find_spec() can execute parent package
initializers for dotted names, so this is NOT a hostile-code sandbox.
"""
from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path

from .types import ANY, BOOL, FLOAT, INT, TEXT, NONE, Type, Signature, Overloads, Binding, option


@dataclass(frozen=True)
class Discovery:
    signatures: dict[str, Binding]
    source: str | None
    source_kind: str
    skipped: dict[str, str]


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else None
    return None


def _annotation(expr: ast.expr | None) -> Type | None:
    """Only recognize precisely known forms, never evaluate annotations."""
    if expr is None:
        return None
    names = {
        "int": INT, "builtins.int": INT,
        "float": FLOAT, "builtins.float": FLOAT,
        "bool": BOOL, "builtins.bool": BOOL,
        "str": TEXT, "builtins.str": TEXT,
        "None": NONE, "types.NoneType": NONE,
        "Any": ANY, "typing.Any": ANY,
    }
    name = _dotted(expr)
    if name in names:
        return names[name]
    if isinstance(expr, ast.Constant) and expr.value is None:
        return NONE
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        a, b = _annotation(expr.left), _annotation(expr.right)
        if a is not None and b is not None:
            if a == NONE and b != NONE:
                return option(b)
            if b == NONE and a != NONE:
                return option(a)
        return None
    if isinstance(expr, ast.Subscript):
        origin = _dotted(expr.value)
        if origin in ("list", "typing.List", "List"):
            member = _annotation(expr.slice)
            return Type("List", (member,)) if member not in (None, NONE) else None
        if origin in ("dict", "typing.Dict", "Dict"):
            if not isinstance(expr.slice, ast.Tuple) or len(expr.slice.elts) != 2:
                return None
            key, value = (_annotation(x) for x in expr.slice.elts)
            return Type("Dict", (TEXT, value)) if key == TEXT and value not in (None, NONE) else None
        if origin in ("Optional", "typing.Optional"):
            inner = _annotation(expr.slice)
            return option(inner) if inner not in (None, NONE) else None
        if origin in ("Union", "typing.Union"):
            if not isinstance(expr.slice, ast.Tuple) or len(expr.slice.elts) != 2:
                return None
            a, b = (_annotation(x) for x in expr.slice.elts)
            if a == NONE and b not in (NONE, None):
                return option(b)
            if b == NONE and a not in (NONE, None):
                return option(a)
    return None


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Signature | None:
    if isinstance(node, ast.AsyncFunctionDef):
        return None
    a = node.args
    if a.vararg or a.kwarg or a.kwonlyargs:
        return None
    params = [*a.posonlyargs, *a.args]
    types = tuple(_annotation(arg.annotation) for arg in params)
    result = _annotation(node.returns)
    if result is None or any(t is None or t == NONE for t in types):
        return None
    return Signature(types, result, min_arity=len(params) - len(a.defaults))  # type: ignore[arg-type]


def _is_overload(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_dotted(d) in ("overload", "typing.overload") for d in node.decorator_list)


def inspect_python(module_path: str) -> Discovery:
    """Extract static declarations from installed module text, without importing it.

    find_spec() can execute parent-package initializers; this is NOT a sandbox.
    """
    try:
        spec = importlib.util.find_spec(module_path)
    except (ValueError, ImportError, ModuleNotFoundError, AttributeError):
        spec = None
    if spec is None:
        return Discovery({}, None, "unavailable", {})
    origin = spec.origin
    if not origin or not origin.endswith((".py", ".pyi")):
        return Discovery({}, None, "binary-or-namespace", {})
    src = Path(origin)
    stub = src.with_suffix(".pyi")
    candidate = stub if stub.is_file() else src
    try:
        tree = ast.parse(candidate.read_text(encoding="utf-8"), filename=str(candidate))
    except (OSError, SyntaxError, UnicodeError) as e:
        return Discovery({}, str(candidate), "unreadable", {"<module>": type(e).__name__})

    groups: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            groups.setdefault(node.name, []).append(node)

    signatures: dict[str, Binding] = {}
    skipped: dict[str, str] = {}
    for name, group in groups.items():
        overloads = [n for n in group if _is_overload(n)]
        ordinary = [n for n in group if not _is_overload(n)]
        if overloads:
            # A Python implementation is ignored, per the typing specification.
            # Reject unknown decorators: they might change call behavior.
            if len(ordinary) > 1 or any(
                len(n.decorator_list) != 1 or _dotted(n.decorator_list[0]) not in ("overload", "typing.overload")
                for n in overloads
            ):
                skipped[name] = "unsupported overload decorators or repeated implementation"
                continue
            if ordinary and any(n.decorator_list for n in ordinary):
                skipped[name] = "decorated implementation may change call behavior"
                continue
            choices = [_signature(n) for n in overloads]
            if len(choices) < 2 or any(sig is None for sig in choices):
                skipped[name] = "incomplete or unsupported overload signatures"
            else:
                signatures[name] = Overloads(tuple(choices))  # type: ignore[arg-type]
            continue
        if len(group) != 1:
            skipped[name] = "repeated definition"
            continue
        node = group[0]
        if node.decorator_list:
            skipped[name] = "decorated function may change call behavior"
            continue
        sig = _signature(node)
        if sig is None:
            skipped[name] = "unsupported or missing annotation"
        else:
            signatures[name] = sig
    return Discovery(signatures, str(candidate), "pyi" if candidate.suffix == ".pyi" else "py", skipped)
