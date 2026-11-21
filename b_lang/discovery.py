"""Non-executing extraction of a conservative subset of Python signatures.

This does not verify implementations or imports. It reads a module's adjacent
.pyi if present, otherwise its .py source and accepts only fully understood,
fixed or trailing-default positional signatures. Unknown forms are skipped.
"""
from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path

from .types import ANY, BOOL, FLOAT, INT, TEXT, Type, Signature


@dataclass(frozen=True)
class Discovery:
    signatures: dict[str, Signature]
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
    """Map only Python type syntax known to be safe in B's current type lattice.

    Do not evaluate annotation expressions: arbitrary Python annotations can
    have side effects and B's check must not execute user-provided code.
    """
    if expr is None:
        return None
    names = {
        "int": INT, "builtins.int": INT,
        "float": FLOAT, "builtins.float": FLOAT,
        "bool": BOOL, "builtins.bool": BOOL,
        "str": TEXT, "builtins.str": TEXT,
        "Any": ANY, "typing.Any": ANY,
    }
    name = _dotted(expr)
    if name in names:
        return names[name]
    if isinstance(expr, ast.Subscript):
        origin = _dotted(expr.value)
        if origin in ("list", "typing.List", "List"):
            member = _annotation(expr.slice)
            return Type("List", (member,)) if member is not None else None
    return None


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Signature | None:
    if isinstance(node, ast.AsyncFunctionDef):
        return None  # Awaitables are not yet part of B's type model.
    a = node.args
    if a.vararg or a.kwarg or a.kwonlyargs:
        return None
    params = [*a.posonlyargs, *a.args]
    types = tuple(_annotation(arg.annotation) for arg in params)
    result = _annotation(node.returns)
    if result is None or any(t is None for t in types):
        return None
    # Type ignore is intentional: none was excluded by the preceding check.
    return Signature(types, result, min_arity=len(params) - len(a.defaults))  # type: ignore[arg-type]


def inspect_python(module_path: str) -> Discovery:
    """Inspect an installed module's source/stub, without importing that module.

    find_spec may execute *parent package* initializers for dotted imports,
    which is a known limitation. Never use this as a sandbox for hostile modules.
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

    signatures: dict[str, Signature] = {}
    skipped: dict[str, str] = {}
    seen: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name.startswith("_"):
            continue
        name = node.name
        # Duplicate definitions often represent overloads. Do not guess which
        # variant is valid. Later B versions can model overload sets explicitly.
        if name in seen:
            signatures.pop(name, None)
            skipped[name] = "overloaded or repeated definition"
            continue
        seen.add(name)
        decorators = [_dotted(d) for d in node.decorator_list]
        if any(d is None or d not in ("overload", "typing.overload") for d in decorators):
            skipped[name] = "decorated function with potentially changed signature"
            continue
        sig = _signature(node)
        if sig is None:
            skipped[name] = "unsupported or missing annotation"
        else:
            signatures[name] = sig
    return Discovery(signatures, str(candidate), "pyi" if candidate.suffix == ".pyi" else "py", skipped)
