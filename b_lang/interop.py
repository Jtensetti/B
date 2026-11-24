"""Unified foreign-function catalog consumed by B's typed IR checker.

Python annotations and .NET snapshots are mapped to one representation. The
catalog does not run untrusted source, and it does not equate metadata with a
verified implementation.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .ir import ForeignSymbol
from .types import BINDINGS, Binding, BError


@dataclass
class ForeignCatalog:
    symbols: dict[str, ForeignSymbol] = field(default_factory=dict)

    def add(self, path: str, binding: Binding, provenance: str) -> None:
        if path in self.symbols:
            raise BError("E_FOREIGN", f"Duplicate foreign binding for {path}")
        backend = path.split(":", 1)[0]
        if backend not in ("py", "net", "js", "go", "rust"):
            raise BError("E_FOREIGN", f"Unsupported foreign backend {backend}")
        self.symbols[path] = ForeignSymbol(path, backend, binding, provenance, backend)

    def add_python_module(self, path: str, discovered) -> None:
        for name, binding in discovered.signatures.items():
            key = f"py:{path}.{name}"
            # Preserve explicitly curated legacy interfaces where present.
            if key not in BINDINGS and key not in self.symbols:
                self.add(key, binding, discovered.source_kind)

    def add_net_registry(self, signatures: dict[str, Binding]) -> None:
        for key, binding in signatures.items():
            if key not in self.symbols:
                self.add(key, binding, "verified-host-snapshot")

    def lookup(self, path: str | None) -> ForeignSymbol | None:
        if not path:
            return None
        if path in BINDINGS:
            return ForeignSymbol(path, path.split(":", 1)[0], BINDINGS[path], "curated-builtin", "py")
        return self.symbols.get(path)

    def export(self, paths: set[str]) -> tuple[ForeignSymbol, ...]:
        return tuple(self.lookup(path) for path in sorted(paths) if self.lookup(path) is not None)
