"""BIR v2/v3: typed, backend-neutral semantic operations.

No Python AST, Python bytecode, CLR-specific object, or executable input is
stored in BIR. Both the Python backend and the independent JavaScript backend
consume this same checked representation.

BIR is a *type checked* program, not a mathematical proof of behavior.
Foreign contracts are assumptions from external metadata, explicitly recorded
along with semantic facets for false-friend protection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import Binding, Overloads, Signature, Type


@dataclass(frozen=True)
class ForeignSymbol:
    """An external callable, its declared interface, semantic facets, and trust boundary."""

    path: str
    backend: str
    binding: Binding
    provenance: str
    adapter: str
    verified_behavior: bool = False
    semantics: tuple[tuple[str, str], ...] = ()

    def semantics_dict(self) -> dict[str, str]:
        return dict(self.semantics)

    def to_dict(self) -> dict[str, Any]:
        signatures = self.binding.options if isinstance(self.binding, Overloads) else (self.binding,)
        data: dict[str, Any] = {
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
        if self.semantics:
            data["semantics"] = dict(self.semantics)
        return data


@dataclass(frozen=True)
class RecordDef:
    name: str
    fields: tuple[tuple[str, Type], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fields": [{"name": n, "type": str(t)} for n, t in self.fields],
        }


@dataclass(frozen=True)
class ExprIR:
    op: str
    typ: Type
    operands: tuple["ExprIR", ...] = ()
    data: Any = None
    foreign_path: str | None = None
    precondition_proved: bool = False  # exact scalar check at this call site

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"op": self.op, "type": str(self.typ)}
        if self.operands:
            result["operands"] = [v.to_dict() for v in self.operands]
        if self.data is not None or self.op == "literal":
            result["value"] = self.data
        if self.precondition_proved:
            result["constant_precondition_proved"] = True
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
    records: tuple[RecordDef, ...] = ()
    units: tuple[tuple[str, str, float], ...] = ()  # (name, base_dim, scale_to_base)
    currencies: tuple[str, ...] = ()
    probes: tuple[ExprIR, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": "bir", "version": self.version,
            "statements": [s.to_dict() for s in self.statements],
            "foreign_symbols": [s.to_dict() for s in self.foreign_symbols],
            "assumed_foreign_contracts": list(self.assumptions),
            "behavior_proven": False,
            "permitted_effects": list(self.permitted_effects) if self.permitted_effects is not None else None,
            "detected_effects": list(self.detected_effects),
        }
        if self.records:
            out["records"] = [r.to_dict() for r in self.records]
        if self.units:
            out["units"] = [{"name": n, "base": b, "scale": s} for n, b, s in self.units]
        if self.currencies:
            out["currencies"] = list(self.currencies)
        if self.probes:
            out["probes"] = [p.to_dict() for p in self.probes]
        return out
