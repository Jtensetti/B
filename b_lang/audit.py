"""Conservative empirical audit of B's Python interface coverage.

Coverage measures *directly declared public functions in the inspected file*.
It does not claim coverage of re-exports, methods, dynamically added symbols,
foreign implementations or a package's full public API. All such blind spots
are reported explicitly. The audit reads source, never imports its target.
"""
from __future__ import annotations

import ast
import importlib.metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discovery import inspect_python
from .types import BError


@dataclass(frozen=True)
class Audit:
    result: dict[str, Any]

    def to_dict(self):
        return self.result


def audit_python(module: str) -> Audit:
    discovery = inspect_python(module)
    if discovery.source_kind == "unavailable":
        raise BError("E_IMPORT", f"Python module {module} is not installed")

    try:
        package_version = importlib.metadata.version(module.split(".", 1)[0])
    except importlib.metadata.PackageNotFoundError:
        package_version = None
    output: dict[str, Any] = {
        "target": "py:" + module,
        "source": discovery.source,
        "source_kind": discovery.source_kind,
        "distribution_version": package_version,
        "metric": "direct-declarations-only",
        "static_signatures": len(discovery.signatures),
        "supported_names": sorted(discovery.signatures),
        "unsupported_names": dict(sorted(discovery.skipped.items())),
        "external_implementations_verified": False,
        "target_module_body_evaluated_by_audit": False,
        "parent_package_initializers_may_execute": True,
        "analysis_complete_for_public_api": False,
    }
    if not discovery.source:
        output.update({"public_direct_functions": 0, "public_direct_coverage": None,
                       "public_classes": 0, "named_reexports": 0, "star_reexports": 0,
                       "reason": "Source not available as a readable .py or .pyi; dynamic or binary API cannot be enumerated"})
        return Audit(output)
    try:
        tree = ast.parse(Path(discovery.source).read_text(encoding="utf-8"), filename=discovery.source)
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise BError("E_METADATA", f"Cannot audit source {discovery.source}: {exc}") from exc

    public_functions = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and not n.name.startswith("_")}
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and not n.name.startswith("_")]
    named_imports = [a for n in tree.body if isinstance(n, ast.ImportFrom) for a in n.names
                     if a.name != "*" and not (a.asname or a.name).startswith("_")]
    star_imports = [n for n in tree.body if isinstance(n, ast.ImportFrom) for a in n.names if a.name == "*"]
    output.update({
        "public_direct_functions": len(public_functions),
        "public_direct_coverage": round(len(discovery.signatures) / len(public_functions), 4) if public_functions else None,
        "public_classes": len(classes),
        "named_reexports": len(named_imports),
        "star_reexports": len(star_imports),
        "reexports_not_checked": True,
        "methods_not_checked": True,
        "static_only_no_execute": True,
    })
    return Audit(output)
