"""BIR 1: typed, backend-neutral semantic operations.

No Python AST, Python bytecode, CLR-specific object, or executable input is
stored in BIR. Both the interpreter's lowered Python AST and tooling views are
produced from this same checked representation.

BIR is a *type checked* program, not a mathematical proof of behavior.
Foreign contracts are assumptions from external metadata, explicitly recorded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import Binding, Overloads, Signature, Type


@dataclass(frozen=True)
class ForeignSymbol:
    """An external callable, its declared interface, and the trust boundary.

    `binding` describes an assumed type-level signature; the implementation is
    not automatically verified. Backend adapters preserve the exact original
    import path, rather than guessing behavior or translating source languages.
    """

    path: str
    backend: str
    binding: Binding
    provenance: str
    adapter: str
    verified_behavior: bool = False

    def to_dict(self) -> dict[str, Any]:
        signatures = self.binding.options if isinstance(self.binding, Overloads) else (self.binding,)
        return {
            "path": self.path,
            "backend": self.backend,
            "adapter": self.adapter,
            "provenance": self.provenance,
            "verified_behavior": self.verified_behavior,
            "signatures": [
                {"parameters": [str(t) for t in sig.params], "result": str(sig.result),
                 "required": sig.required} for sig in signatures
            ],
        }


@dataclass(frozen=True)
class ExprIR:
    op: str
    typ: Type
    operands: tuple["ExprIR", ...] = ()
    data: Any = None
    foreign_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"op": self.op, "type": str(self.typ)}
        if self.operands:
            result["operands"] = [v.to_dict() for v in self.operands]
        if self.data is not None or self.op == "literal":
            result["value"] = self.data
        if self.foreign_path:
            result["foreign"] = self.foreign_path
        return result


@dataclass(frozen=True)
class StmtIR:
    op: str
    name: str | None = None
    typ: Type | None = None
    expr: ExprIR | None = None
    params: tuple[tuple[str, Type], ...] = ()
    backend: str | None = None
    target: str | None = None
    effects: tuple[str, ...] = ()
    requires: ExprIR | None = None
    ensures: ExprIR | None = None
    verification: str | None = None
    declared_pure: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"op": self.op}
        if self.name is not None:
            d["name"] = self.name
        if self.typ is not None:
            d["type"] = str(self.typ)
        if self.expr is not None:
            d["expression"] = self.expr.to_dict()
        if self.params:
            d["parameters"] = [{"name": n, "type": str(t)} for n, t in self.params]
        if self.backend:
            d["backend"] = self.backend
        if self.target:
            d["target"] = self.target
        if self.op == "fn":
            d["effects"] = list(self.effects)
            d["declared_pure"] = self.declared_pure
            if self.requires is not None:
                d["requires"] = self.requires.to_dict()
            if self.ensures is not None:
                d["ensures"] = self.ensures.to_dict()
            if self.verification is not None:
                d["postcondition_status"] = self.verification
        return d


@dataclass(frozen=True)
class ProgramIR:
    statements: tuple[StmtIR, ...]
    foreign_symbols: tuple[ForeignSymbol, ...]
    assumptions: tuple[str, ...] = ()
    version: int = 2
    permitted_effects: tuple[str, ...] | None = None
    detected_effects: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "bir", "version": self.version,
            "statements": [s.to_dict() for s in self.statements],
            "foreign_symbols": [s.to_dict() for s in self.foreign_symbols],
            "assumed_foreign_contracts": list(self.assumptions),
            "behavior_proven": False,
            "permitted_effects": list(self.permitted_effects) if self.permitted_effects is not None else None,
            "detected_effects": list(self.detected_effects),
        }
