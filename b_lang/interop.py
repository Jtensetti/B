"""Unified foreign-function catalog consumed by B's typed IR checker.

Python, .NET, Node.js, Go and Rust metadata are mapped to one representation,
including semantic facets (rounding mode, string measurement unit, regex mode,
remainder convention, integer width) used to catch cross-ecosystem false friends
before execution.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .ir import ForeignSymbol
from .types import BINDINGS, Binding, BError

BACKENDS = ("py", "net", "js", "go", "rs")

# Known cross-ecosystem semantic facets for curated / stdlib symbols.
DEFAULT_SEMANTICS: dict[str, dict[str, str]] = {
    "py:builtins.round": {"rounding": "half_even"},
    "py:builtins.len": {"string_unit": "codepoints"},
    "py:re.match": {"regex_mode": "prefix"},
    "py:re.search": {"regex_mode": "search"},
    "py:re.fullmatch": {"regex_mode": "full"},
    "py:statistics.stdev": {"variance": "sample"},
    "py:statistics.pstdev": {"variance": "population"},
    "py:math.remainder": {"remainder": "ieee"},
    "net:System.Math.Round": {"rounding": "half_even"},
    "net:System.Text.RegularExpressions.Regex.IsMatch": {"regex_mode": "search"},
    "net:System.Text.RegularExpressions.Regex.Replace": {"regex_mode": "search"},
    "js:fastest-levenshtein.distance": {"string_unit": "utf16_units", "int_width": "safe_i53"},
    "js:fastest-levenshtein.closest": {"string_unit": "utf16_units"},
    "js:semver.compare": {"int_width": "safe_i53"},
}


@dataclass
class ForeignCatalog:
    symbols: dict[str, ForeignSymbol] = field(default_factory=dict)

    def add(self, path: str, binding: Binding, provenance: str,
            semantics: dict[str, str] | None = None) -> None:
        if path in self.symbols:
            raise BError("E_FOREIGN", f"Duplicate foreign binding for {path}")
        backend = path.split(":", 1)[0]
        if backend not in BACKENDS:
            raise BError("E_FOREIGN", f"Unsupported foreign backend {backend}")
        merged = dict(DEFAULT_SEMANTICS.get(path, {}))
        if backend == "js":
            merged.setdefault("int_width", "safe_i53")
        if semantics:
            merged.update(semantics)
        self.symbols[path] = ForeignSymbol(
            path, backend, binding, provenance, backend,
            semantics=tuple(sorted(merged.items())),
        )

    def add_python_module(self, path: str, discovered) -> None:
        for name, binding in discovered.signatures.items():
            key = f"py:{path}.{name}"
            if key not in BINDINGS and key not in self.symbols:
                self.add(key, binding, discovered.source_kind)

    def add_net_registry(self, signatures: dict[str, Binding]) -> None:
        for key, binding in signatures.items():
            if key not in self.symbols:
                self.add(key, binding, "verified-host-snapshot")

    def add_go_registry(self, signatures: dict[str, Binding],
                        semantics: dict[str, dict[str, str]] | None = None) -> None:
        semantics = semantics or {}
        for key, binding in signatures.items():
            if key not in self.symbols:
                self.add(key, binding, "verified-go-host-snapshot", semantics.get(key))

    def add_rs_registry(self, signatures: dict[str, Binding],
                        semantics: dict[str, dict[str, str]] | None = None) -> None:
        semantics = semantics or {}
        for key, binding in signatures.items():
            if key not in self.symbols:
                self.add(key, binding, "verified-rs-host-snapshot", semantics.get(key))

    def lookup(self, path: str | None) -> ForeignSymbol | None:
        if not path:
            return None
        if path in BINDINGS:
            sem = tuple(sorted(DEFAULT_SEMANTICS.get(path, {}).items()))
            return ForeignSymbol(path, path.split(":", 1)[0], BINDINGS[path], "curated-builtin", "py", semantics=sem)
        return self.symbols.get(path)

    def export(self, paths: set[str]) -> tuple[ForeignSymbol, ...]:
        return tuple(self.lookup(path) for path in sorted(paths) if self.lookup(path) is not None)
