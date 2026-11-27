"""B 0.20 compiler: parse -> typed BIR -> multi-target lowering (Python / JS).

The checker never evaluates B source or foreign implementations. Foreign
signatures are assumptions, not proofs. Units, currencies, records and semantic
facets are enforced statically before execution.
"""
from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass, replace
from typing import Any

from lark.exceptions import LarkError

from .also import additional_cases, extend_predicate
from .composition import Analysis, analyze
from .contracts import validate_predicate, constant as contract_constant, restrict as contract_restrict, verify as verify_post
from .effects import ALLOWED as ALLOWED_EFFECTS, expression_effects, statement_effects
from .discovery import inspect_python
from .adoption import adopt_python
from .gometa import go_bindings, go_semantics
from .handoff import Handoff, materialize, validate_rewrite
from .history import history_plan
from .interop import ForeignCatalog
from . import jsmeta
from .ir import ExprIR, ProgramIR, RecordDef, StmtIR
from .lowering import PythonLowerer
from .optimizer import optimize
from .model import Expr, Stmt, parse
from .netmeta import net_bindings
from .rsmeta import rs_bindings, rs_semantics
from .types import (
    Type, BError, INT, FLOAT, BOOL, TEXT, NONE, ANY, MODULE,
    ATTRIBUTES, BUILTIN_SEMANTIC_UNITS, Signature, Overloads, Binding, assignable,
    base_numeric, dim_of, from_syntax, is_dim_float, is_dim_int, is_dim_numeric,
    is_numeric, is_struct_record, struct_fields, struct_record,
    unify, needs_dynamic_guard, needs_numeric_widening, option,
    supports_ordering, with_dim,
)

NOT_CONST = object()
NUMERIC = (INT, FLOAT)
JS_MAX_SAFE_INT = 2**53 - 1
OPS = {"add": operator.add, "sub": operator.sub, "mul": operator.mul,
       "div": operator.truediv, "mod": operator.mod}
CMP = {"==": operator.eq, "!=": operator.ne, "<": operator.lt,
       ">": operator.gt, "<=": operator.le, ">=": operator.ge}


@dataclass
class Value:
    type: Type
    node: ExprIR
    constant: Any = NOT_CONST
    known_fields: dict[str, Type] | None = None


@dataclass
class Diagnostic:
    level: str
    code: str
    message: str


@dataclass
class Compiled:
    source: str
    code: Any
    diagnostics: list[Diagnostic]
    assumptions: list[str]
    ir: ProgramIR
    optimized_ir: ProgramIR
    folds: int
    analysis: Analysis
    handoff: Handoff | None = None
    pending_analysis: Analysis | None = None


@dataclass
class Symbol:
    type: Type
    foreign: str | None = None
    signature: Binding | None = None
    constant: Any = NOT_CONST
    effects: frozenset[str] | None = frozenset()
    requires: ExprIR | None = None
    parameter_names: tuple[str, ...] = ()
    is_record: bool = False
    known_fields: dict[str, Type] | None = None


class Compiler:
    def __init__(self):
        self.symbols: dict[str, Symbol] = {}
        self.diagnostics: list[Diagnostic] = []
        self.assumptions: list[str] = []
        self.registry = ForeignCatalog()
        self.registry.add_net_registry(net_bindings())
        self.registry.add_go_registry(go_bindings(), go_semantics())
        self.registry.add_rs_registry(rs_bindings(), rs_semantics())
        self.used_foreign: set[str] = set()
        self.permitted_effects: tuple[str, ...] | None = None
        self.started_statements = False
        self.additional_cases: dict[str, list[tuple]] = {}
        self.units: dict[str, tuple[str, float]] = {}
        self.currencies: set[str] = set()
        self.records: dict[str, RecordDef] = {}
        self.probes: list[ExprIR] = []

    def _all_dims(self) -> set[str]:
        return set(self.units) | self.currencies | set(BUILTIN_SEMANTIC_UNITS)

    def _parse_type(self, node) -> Type:
        return from_syntax(node, units=self._all_dims(), records=self.records.keys())

    def _mismatch_code(self, actual: Type, expected: Type) -> str:
        da, de = dim_of(actual), dim_of(expected)
        if da in self.currencies or de in self.currencies:
            return "E_CURRENCY"
        if da is not None or de is not None:
            return "E_UNIT"
        if actual.name == "List" and expected.name == "List":
            return self._mismatch_code(actual.args[0], expected.args[0])
        if actual.name == "Option" and expected.name == "Option":
            return self._mismatch_code(actual.args[0], expected.args[0])
        return "E_TYPE"

    def warn(self, code: str, message: str):
        d = Diagnostic("warning", code, message)
        if d not in self.diagnostics:
            self.diagnostics.append(d)

    @staticmethod
    def val(typ: Type, op: str, *parts: ExprIR, constant: Any = NOT_CONST,
            data: Any = None, foreign: str | None = None) -> Value:
        return Value(typ, ExprIR(op, typ, tuple(parts), data, foreign), constant)

    @staticmethod
    def guard(node: ExprIR, typ: Type) -> ExprIR:
        return ExprIR("guard", typ, (node,))

    def _widen(self, value: Value, wanted: Type) -> Value:
        if not needs_numeric_widening(value.type, wanted):
            return value
        scalar = wanted.args[0] if wanted.name == "Option" else wanted
        known = (None if value.constant is None and wanted.name == "Option"
                 else self._at_runtime_constant(value.constant, scalar))
        return Value(wanted, self.guard(value.node, wanted), known)

    def _check_type(self, value: Value, expected: Type, context: str):
        if not assignable(value.type, expected):
            code = self._mismatch_code(value.type, expected)
            raise BError(code, f"{context}: expected {expected}, got {value.type}")
        if needs_dynamic_guard(value.type, expected):
            self.warn("W_DYNAMIC_TYPE", f"{context} comes from an untyped boundary; checked at runtime")
            value.node = self.guard(value.node, expected)

    def _new(self, name: str, symbol: Symbol):
        if name.startswith("_b_"):
            raise BError("E_NAME", "Names starting _b_ are reserved for the B runtime")
        if name in self.symbols:
            raise BError("E_NAME", f"Redefinition of {name}")
        self.symbols[name] = symbol

    @staticmethod
    def _at_runtime_constant(value: Any, wanted: Type) -> Any:
        if value is NOT_CONST:
            return NOT_CONST
        if (wanted == INT or is_dim_int(wanted)) and type(value) is int:
            return value
        if wanted == BOOL and type(value) is bool:
            return value
        if wanted == TEXT and type(value) is str:
            return value
        if (wanted == FLOAT or is_dim_float(wanted)) and type(value) in (int, float):
            try:
                converted = float(value)
                return converted if math.isfinite(converted) else NOT_CONST
            except (OverflowError, ValueError):
                return NOT_CONST
        return NOT_CONST

    @staticmethod
    def _const_op(fn, *args):
        if any(v is NOT_CONST for v in args):
            return NOT_CONST
        try:
            return fn(*args)
        except ZeroDivisionError:
            raise BError("E_DIV_ZERO", "Division by zero is guaranteed")
        except (ValueError, TypeError, OverflowError):
            return NOT_CONST

    def _resolve_binding(self, binding: Binding, values: list[Value], target: str) -> Signature:
        if isinstance(binding, Signature):
            return binding
        arities = [sig for sig in binding.options if sig.required <= len(values) <= len(sig.params)]
        if not arities:
            raise BError("E_ARITY", f"No overload of {target} accepts {len(values)} arguments")
        candidates = [sig for sig in arities if all(
            assignable(v.type, t) for v, t in zip(values, sig.params))]
        if not candidates:
            options = "; ".join("(" + ", ".join(map(str, sig.params)) + ")" for sig in arities)
            raise BError("E_TYPE", f"No overload of {target} matches argument types; choices: {options}")
        if len(candidates) == 1:
            return candidates[0]
        exact = [sig for sig in candidates if all(v.type == t for v, t in zip(values, sig.params))]
        if len(exact) == 1:
            return exact[0]
        if len(set(candidates)) == 1:
            return candidates[0]
        raise BError("E_OVERLOAD_AMBIGUOUS", f"Ambiguous overload of {target}; annotate or narrow arguments")

    def _foreign_path(self, ex: Expr, scope: dict[str, Symbol]) -> str | None:
        if ex.kind == "name":
            sym = scope.get(ex.parts[0])
            return sym.foreign if sym else None
        if ex.kind == "attr":
            base = self._foreign_path(ex.parts[0], scope)
            return f"{base}.{ex.parts[1]}" if base else None
        return None

    def _list_scope(self, operation: str, source: Expr, scope: dict[str, Symbol],
                    *binders: str) -> tuple[Value, dict[str, Symbol]]:
        collection = self.infer(source, scope)
        if collection.type.name != "List":
            raise BError("E_TYPE", f"{operation} needs a List[T] source, got {collection.type}")
        elements = scope.copy()
        for name in binders:
            if name in elements or name.startswith("_b_") or name in {"true", "false", "none", "if", "not"}:
                raise BError("E_NAME", f"{operation} cannot bind {name}: name is already in scope or reserved")
            elements[name] = Symbol(collection.type.args[0])
        return collection, elements

    def _summarize(self, ex: Expr, scope: dict[str, Symbol]) -> Value:
        binder, source, fields = ex.parts
        collection, elements = self._list_scope("summarize", source, scope, binder)
        operands = [collection.node]
        reductions = []
        labels = set()
        named_fields: list[tuple[str, Type]] = []
        for label, reducer, raw_value, raw_guard, default in fields:
            if label in labels:
                raise BError("E_NAME", f"Duplicate summarize field {label}")
            labels.add(label)
            guard_index = value_index = None
            if raw_guard is not None:
                guard = self.infer(raw_guard, elements)
                self._check_type(guard, BOOL, f"summarize {label} filter")
                guard_index = len(operands)
                operands.append(guard.node)
            if raw_value is not None:
                value = self.infer(raw_value, elements)
                if not (is_numeric(value.type) or value.type == ANY):
                    raise BError("E_TYPE", f"summarize {label} value: expected numeric type, got {value.type}")
                if value.type == ANY:
                    self._check_type(value, INT, f"summarize {label} value")
                    ftype = INT
                else:
                    ftype = value.type
                if reducer in ("min", "max"):
                    if (ftype == INT or is_dim_int(ftype)) and type(default) is float:
                        raise BError("E_TYPE", f"summarize {label} default: expected Int, got Float")
                    if (ftype == FLOAT or is_dim_float(ftype)) and type(default) is int:
                        default = float(default)
                value_index = len(operands)
                operands.append(value.node)
                named_fields.append((label, ftype))
            else:
                named_fields.append((label, INT))
            reductions.append((label, reducer, value_index, guard_index, default))
        field_types = [ft for _, ft in named_fields]
        if len(set(field_types)) == 1:
            result_type = Type("Dict", (TEXT, field_types[0]))
            res = self.val(result_type, "summarize", *operands,
                           data={"binder": binder, "fields": tuple(reductions)})
            res.known_fields = dict(named_fields)
            return res
        result_type = struct_record(named_fields)
        return self.val(result_type, "summarize", *operands,
                        data={"binder": binder, "fields": tuple(reductions)})

    def _infer_builtin(self, name: str, raw_args: tuple[Expr, ...], symbols: dict[str, Symbol],
                       expected_type: Type | None = None) -> Value | None:
        if name in symbols:
            return None
        if name == "from_json":
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"from_json expects 1 argument, got {len(raw_args)}")
            txt = self.infer(raw_args[0], symbols)
            self._check_type(txt, TEXT, "argument 1 to from_json")
            target = expected_type if expected_type is not None else ANY
            return self.val(target, "builtin_from_json", txt.node, data=str(target))
        if name == "stdin_text":
            if raw_args:
                raise BError("E_ARITY", f"stdin_text expects 0 arguments, got {len(raw_args)}")
            return self.val(TEXT, "builtin", data="stdin_text")
        if name == "json_encode":
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"json_encode expects 1 argument, got {len(raw_args)}")
            v = self.infer(raw_args[0], symbols)
            return self.val(TEXT, "builtin", v.node, data="json_encode")
        if name == "len":
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"len expects 1 argument, got {len(raw_args)}")
            v = self.infer(raw_args[0], symbols)
            if v.type not in (TEXT, ANY) and v.type.name not in ("List", "Dict"):
                raise BError("E_TYPE", f"len expects Text, List or Dict, got {v.type}")
            const = len(v.constant) if isinstance(v.constant, (str, list)) else NOT_CONST
            return self.val(INT, "builtin", v.node, data="len", constant=const)
        if name == "abs":
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"abs expects 1 argument, got {len(raw_args)}")
            v = self.infer(raw_args[0], symbols)
            if not is_numeric(v.type):
                raise BError("E_TYPE", f"abs expects numeric value, got {v.type}")
            return self.val(v.type, "builtin", v.node, data="abs",
                            constant=self._const_op(abs, v.constant))
        if name in ("min", "max"):
            if len(raw_args) != 2:
                raise BError("E_ARITY", f"{name} expects 2 arguments, got {len(raw_args)}")
            a, b = self.infer(raw_args[0], symbols), self.infer(raw_args[1], symbols)
            if not (is_numeric(a.type) and is_numeric(b.type)):
                raise BError("E_TYPE", f"{name} expects numeric values, got {a.type} and {b.type}")
            if dim_of(a.type) != dim_of(b.type):
                raise BError(self._mismatch_code(a.type, b.type), f"{name} cannot mix {a.type} and {b.type}")
            res_t = unify(a.type, b.type)
            fn = min if name == "min" else max
            return self.val(res_t, "builtin", a.node, b.node, data=name,
                            constant=self._const_op(fn, a.constant, b.constant))
        if name in ("round_even", "round_away"):
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"{name} expects 1 argument, got {len(raw_args)}")
            v = self.infer(raw_args[0], symbols)
            self._check_type(v, FLOAT, f"argument 1 to {name}")
            return self.val(INT, "builtin", v.node, data=name)
        if name in ("div_euclid", "rem_euclid", "rem_trunc"):
            if len(raw_args) != 2:
                raise BError("E_ARITY", f"{name} expects 2 arguments, got {len(raw_args)}")
            a, b = self.infer(raw_args[0], symbols), self.infer(raw_args[1], symbols)
            self._check_type(a, INT, f"argument 1 to {name}")
            self._check_type(b, INT, f"argument 2 to {name}")
            if b.constant == 0:
                raise BError("E_DIV_ZERO", "Division by zero is guaranteed")
            return self.val(INT, "builtin", a.node, b.node, data=name)
        if name == "scalar":
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"scalar expects 1 argument, got {len(raw_args)}")
            v = self.infer(raw_args[0], symbols)
            if not is_numeric(v.type):
                raise BError("E_TYPE", f"scalar expects numeric value, got {v.type}")
            return self.val(base_numeric(v.type), "builtin", v.node, data="scalar", constant=v.constant)
        if name == "to_text":
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"to_text expects 1 argument, got {len(raw_args)}")
            v = self.infer(raw_args[0], symbols)
            return self.val(TEXT, "builtin", v.node, data="to_text")
        if name == "to_float":
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"to_float expects 1 argument, got {len(raw_args)}")
            v = self.infer(raw_args[0], symbols)
            self._check_type(v, FLOAT, "argument 1 to to_float")
            return self.val(FLOAT, "builtin", v.node, data="to_float")
        if name == "to_int":
            if len(raw_args) != 1:
                raise BError("E_ARITY", f"to_int expects 1 argument, got {len(raw_args)}")
            v = self.infer(raw_args[0], symbols)
            self._check_type(v, FLOAT, "argument 1 to to_int")
            return self.val(INT, "builtin", v.node, data="to_int")
        str_sigs: dict[str, tuple[tuple[Type, ...], Type]] = {
            "str_contains": ((TEXT, TEXT), BOOL),
            "str_starts": ((TEXT, TEXT), BOOL),
            "str_ends": ((TEXT, TEXT), BOOL),
            "str_lower": ((TEXT,), TEXT),
            "str_upper": ((TEXT,), TEXT),
            "str_trim": ((TEXT,), TEXT),
            "str_split": ((TEXT, TEXT), Type("List", (TEXT,))),
            "str_join": ((Type("List", (TEXT,)), TEXT), TEXT),
            "str_replace": ((TEXT, TEXT, TEXT), TEXT),
        }
        if name in str_sigs:
            params, res = str_sigs[name]
            if len(raw_args) != len(params):
                raise BError("E_ARITY", f"{name} expects {len(params)} arguments, got {len(raw_args)}")
            vals = [self.infer(arg, symbols) for arg in raw_args]
            for idx, (v, expected) in enumerate(zip(vals, params), start=1):
                self._check_type(v, expected, f"argument {idx} to {name}")
            return self.val(res, "builtin", *(v.node for v in vals), data=name)
        return None

    def infer(self, ex: Expr, scope: dict[str, Symbol] | None = None,
              expected_type: Type | None = None) -> Value:
        symbols = self.symbols if scope is None else scope
        kind, p = ex.kind, ex.parts
        if kind == "let_expr":
            name, annotation, value_expr, body_expr = p
            if name.startswith("_b_"):
                raise BError("E_NAME", "Names starting _b_ are reserved for the B runtime")
            wanted = self._parse_type(annotation) if annotation is not None else None
            val = self.infer(value_expr, symbols, expected_type=wanted)
            typ = wanted if wanted is not None else val.type
            if typ == NONE:
                raise BError("E_TYPE", "A variable cannot be annotated None")
            self._check_type(val, typ, f"local binding {name}")
            node = self.guard(val.node, typ) if annotation is not None else val.node
            local = {**symbols, name: Symbol(typ, constant=self._at_runtime_constant(val.constant, typ),
                                             known_fields=val.known_fields)}
            body = self.infer(body_expr, local, expected_type=expected_type)
            res = self.val(body.type, "let_expr", node, body.node, data=name, constant=body.constant)
            res.known_fields = body.known_fields
            return res
        if kind == "record_lit":
            seen: set[str] = set()
            fields_t: list[tuple[str, Type]] = []
            nodes: list[ExprIR] = []
            for fname, fexpr in p:
                if fname in seen:
                    raise BError("E_NAME", f"Duplicate field {fname} in record literal")
                seen.add(fname)
                fv = self.infer(fexpr, symbols)
                fields_t.append((fname, fv.type))
                nodes.append(fv.node)
            return self.val(struct_record(fields_t), "record_make", *nodes,
                            data={"record": "<anonymous>", "fields": tuple(n for n, _ in fields_t)})
        if kind == "list_comp":
            body_expr, binder, source_expr, guard_expr = p
            collection, elements = self._list_scope("list comprehension", source_expr, symbols, binder)
            operands = [collection.node]
            body = self.infer(body_expr, elements)
            operands.append(body.node)
            if guard_expr is not None:
                guard = self.infer(guard_expr, elements)
                self._check_type(guard, BOOL, "list comprehension filter")
                operands.append(guard.node)
            return self.val(Type("List", (body.type,)), "list_comp", *operands, data=binder)
        if kind == "unit_tag":
            raw_expr, dim = p
            if dim not in self._all_dims():
                raise BError("E_UNIT", f"Unknown unit or currency {dim}")
            v = self.infer(raw_expr, symbols)
            if is_dim_numeric(v.type):
                existing = dim_of(v.type)
                code = "E_CURRENCY" if (dim in self.currencies or existing in self.currencies) else "E_UNIT"
                raise BError(code, f"Cannot re-tag {v.type} as {dim}; use 'to' for unit conversion or scalar()")
            if v.type not in (INT, FLOAT):
                raise BError("E_TYPE", f"as {dim} requires Int or Float, got {v.type}")
            return self.val(with_dim(v.type, dim), v.node.op, *v.node.operands,
                            constant=v.constant, data=v.node.data, foreign=v.node.foreign_path)
        if kind == "unit_convert":
            raw_expr, target = p
            v = self.infer(raw_expr, symbols)
            src = dim_of(v.type)
            if src is None:
                raise BError("E_UNIT", f"Cannot convert dimensionless {v.type} to {target}")
            if src in self.currencies or target in self.currencies:
                raise BError("E_CURRENCY", f"Cannot implicitly convert currency {src} to {target}; use an explicit exchange rate")
            if src not in self.units or target not in self.units:
                raise BError("E_UNIT", f"Unknown unit in conversion {src} to {target}")
            src_base, src_scale = self.units[src]
            dst_base, dst_scale = self.units[target]
            if src_base != dst_base:
                raise BError("E_UNIT", f"Incompatible unit dimensions: cannot convert {src} ({src_base}) to {target} ({dst_base})")
            factor = src_scale / dst_scale
            res_type = with_dim(FLOAT, target)
            if factor == 1.0:
                const = float(v.constant) if isinstance(v.constant, (int, float)) and type(v.constant) is not bool else NOT_CONST
                return Value(res_type, self.guard(v.node, res_type), const)
            factor_node = ExprIR("literal", FLOAT, data=factor)
            const = self._const_op(operator.mul, float(v.constant) if isinstance(v.constant, (int, float)) and type(v.constant) is not bool else NOT_CONST, factor)
            return self.val(res_type, "mul", v.node, factor_node, constant=const)
        if kind == "record_with":
            base_expr, raw_updates = p
            bv = self.infer(base_expr, symbols)
            rec = self.records.get(bv.type.name)
            if rec is not None:
                rec_label = rec.name
                field_map = dict(rec.fields)
            elif is_struct_record(bv.type):
                rec_label = str(bv.type)
                field_map = dict(struct_fields(bv.type))
            else:
                raise BError("E_TYPE", f"with update requires a record value, got {bv.type}")
            seen: set[str] = set()
            operands = [bv.node]
            field_names: list[str] = []
            for fname, fexpr in raw_updates:
                if fname not in field_map:
                    raise BError("E_NAME", f"Record {rec_label} has no field {fname}")
                if fname in seen:
                    raise BError("E_NAME", f"Duplicate field {fname} in with update")
                seen.add(fname)
                fv = self.infer(fexpr, symbols, expected_type=field_map[fname])
                self._check_type(fv, field_map[fname], f"field {fname} of {rec_label}")
                fv = self._widen(fv, field_map[fname])
                operands.append(fv.node)
                field_names.append(fname)
            return self.val(bv.type, "record_with", *operands, data=tuple(field_names))
        if kind == "history_count":
            mode, past, current, source, raw_predicate = p
            collection, elements = self._list_scope(f"count {mode}", source, symbols, past, current)
            predicate = self.infer(raw_predicate, elements)
            if predicate.type != BOOL:
                raise BError("E_TYPE", f"count {mode} predicate needs Bool, got {predicate.type}")
            plan = history_plan(predicate.node, past, current, mode)
            return self.val(INT, "history_count", collection.node, predicate.node,
                            data={"mode": mode, "past": past, "current": current, **plan})
        if kind == "summarize":
            return self._summarize(ex, symbols)
        if kind == "lookup":
            dictionary = self.infer(p[0], symbols)
            key = self.infer(p[1], symbols)
            self._check_type(key, TEXT, "dictionary lookup key")
            if dictionary.type.name == "Dict":
                return self.val(option(dictionary.type.args[1]), "lookup", dictionary.node, key.node)
            if is_struct_record(dictionary.type):
                fmap = dict(struct_fields(dictionary.type))
                if type(key.constant) is str and key.constant in fmap:
                    return self.val(option(fmap[key.constant]), "lookup", dictionary.node, key.node)
                vt = list(fmap.values())[0]
                for ft in list(fmap.values())[1:]:
                    vt = unify(vt, ft)
                return self.val(option(vt), "lookup", dictionary.node, key.node)
            raise BError("E_TYPE", f"Key lookup needs a Dict[Text, T], got {dictionary.type}")
        if kind == "coalesce":
            left = self.infer(p[0], symbols)
            if left.type.name != "Option":
                raise BError("E_TYPE", "Left side of ?? must be Option[T]")
            right = self.infer(p[1], symbols)
            inner = left.type.args[0]
            if right.type == NONE:
                typ = left.type
            elif right.type.name == "Option":
                merged = unify(inner, right.type.args[0])
                if merged == ANY and inner != ANY and right.type.args[0] != ANY:
                    raise BError(self._mismatch_code(inner, right.type.args[0]),
                                 f"Incompatible coalesce values: {inner} and {right.type}")
                typ = Type("Option", (merged,))
            elif right.type == ANY and inner != ANY:
                self._check_type(right, inner, "?? fallback")
                typ = inner
            else:
                typ = unify(inner, right.type)
                if typ == ANY and inner != ANY and right.type != ANY:
                    raise BError(self._mismatch_code(inner, right.type),
                                 f"Incompatible coalesce values: {inner} and {right.type}")
            left = self._widen(left, option(typ))
            right = self._widen(right, typ)
            const = right.constant if left.constant is None else left.constant
            if left.constant is NOT_CONST:
                const = NOT_CONST
            return self.val(typ, "coalesce", left.node, right.node, constant=const)
        if kind == "conditional":
            cv = self.infer(p[0], symbols)
            self._check_type(cv, BOOL, "if condition")
            yv = self.infer(p[1], symbols, expected_type=expected_type)
            nv = self.infer(p[2], symbols, expected_type=expected_type)
            typ = unify(yv.type, nv.type)
            if typ == ANY and yv.type != ANY and nv.type != ANY:
                raise BError(self._mismatch_code(yv.type, nv.type),
                             f"if branches have incompatible types: {yv.type} versus {nv.type}")
            if needs_dynamic_guard(yv.type, typ):
                self._check_type(yv, typ, "if then branch")
            if needs_dynamic_guard(nv.type, typ):
                self._check_type(nv, typ, "if else branch")
            yv = self._widen(yv, typ)
            nv = self._widen(nv, typ)
            const = NOT_CONST
            if type(cv.constant) is bool:
                const = yv.constant if cv.constant else nv.constant
            return self.val(typ, "conditional", cv.node, yv.node, nv.node, constant=const)
        if kind == "literal":
            raw = p[0]
            typ = BOOL if type(raw) is bool else INT if type(raw) is int else FLOAT if type(raw) is float else TEXT if type(raw) is str else NONE
            return self.val(typ, "literal", data=raw, constant=raw)
        if kind == "name":
            name = p[0]
            if name not in symbols:
                raise BError("E_NAME", f"Unknown name {name}")
            sym = symbols[name]
            res = self.val(sym.type, "name", data=name, constant=sym.constant)
            res.known_fields = sym.known_fields
            return res
        if kind == "list":
            items = [self.infer(i, symbols) for i in p]
            element_type = ANY
            if items:
                element_type = items[0].type
                for i in items[1:]:
                    merged = unify(element_type, i.type)
                    if merged == ANY and element_type != ANY and i.type != ANY:
                        raise BError(self._mismatch_code(element_type, i.type),
                                     f"List contains incompatible element types: {element_type} versus {i.type}")
                    element_type = merged
            items = [self._widen(item, element_type) for item in items]
            const = [i.constant for i in items] if all(i.constant is not NOT_CONST for i in items) else NOT_CONST
            return self.val(Type("List", (element_type,)), "list", *(v.node for v in items), constant=const)
        if kind == "dict":
            pairs: list[tuple[Value, Value]] = []
            value_type = None
            for key_expr, value_expr in p:
                key, val = self.infer(key_expr, symbols), self.infer(value_expr, symbols)
                self._check_type(key, TEXT, "dictionary key")
                pairs.append((key, val))
                if value_type is None:
                    value_type = val.type
                else:
                    merged = unify(value_type, val.type)
                    if merged == ANY and value_type != ANY and val.type != ANY:
                        raise BError(self._mismatch_code(value_type, val.type),
                                     f"Dictionary values disagree: {value_type} versus {val.type}")
                    value_type = merged
            value_type = value_type or ANY
            flattened = [node for key, val in pairs
                         for node in (key.node, self._widen(val, value_type).node)]
            return self.val(Type("Dict", (TEXT, value_type)), "dict", *flattened)
        if kind == "attr":
            base, name = p
            bv = self.infer(base, symbols)
            if bv.type.name in self.records:
                rec = self.records[bv.type.name]
                for fname, ftype in rec.fields:
                    if fname == name:
                        return self.val(ftype, "record_field", bv.node, data=name)
                raise BError("E_NAME", f"Record {rec.name} has no field {name}")
            if is_struct_record(bv.type):
                for fname, ftype in struct_fields(bv.type):
                    if fname == name:
                        return self.val(ftype, "record_field", bv.node, data=name)
                raise BError("E_NAME", f"Record {bv.type} has no field {name}")
            if bv.known_fields is not None:
                if name in bv.known_fields:
                    return self.val(bv.known_fields[name], "record_field", bv.node, data=name)
                raise BError("E_NAME", f"Summary has no field {name}")
            if bv.type not in (MODULE, ANY):
                raise BError("E_TYPE", f"Cannot access attribute {name} on {bv.type}")
            path = self._foreign_path(ex, symbols)
            if path in ATTRIBUTES:
                ref = self.val(ATTRIBUTES[path], "attr", bv.node, data=name, foreign=path)
                ref.node = self.guard(ref.node, ATTRIBUTES[path])
                return ref
            if path and self.registry.lookup(path):
                if path.startswith("js:"):
                    self.used_foreign.add(path)
                return self.val(Type("Function"), "attr", bv.node, data=name, foreign=path)
            if path and path.startswith("js:"):
                raise BError("E_FOREIGN", f"Unregistered Node export {path}; declare its foreign signature")
            if path and path.startswith("net:"):
                raise BError("E_FOREIGN", f"Unregistered .NET symbol {path}")
            if path and path.startswith("go:"):
                raise BError("E_FOREIGN", f"Unregistered Go symbol {path}")
            if path and path.startswith("rs:"):
                raise BError("E_FOREIGN", f"Unregistered Rust symbol {path}")
            if path and path.startswith("py:"):
                self.warn("W_UNCHECKED_FOREIGN", f"Unspecified Python symbol {path}; no static signature available")
            return self.val(ANY, "attr", bv.node, data=name, foreign=path)
        if kind == "invoke":
            target, raw_args = p
            has_named = any(isinstance(a, tuple) and len(a) == 3 and a[0] == "named" for a in raw_args)
            if not has_named and target.kind == "name":
                builtin_val = self._infer_builtin(target.parts[0], raw_args, symbols, expected_type=expected_type)
                if builtin_val is not None:
                    return builtin_val
            tv = self.infer(target, symbols)
            # Record constructor call (positional or named/shorthand)
            if target.kind == "name" and target.parts[0] in self.records and symbols[target.parts[0]].is_record:
                rec = self.records[target.parts[0]]
                if has_named:
                    field_map = dict(rec.fields)
                    provided: dict[str, Value] = {}
                    for arg in raw_args:
                        if isinstance(arg, tuple) and len(arg) == 3 and arg[0] == "named":
                            _, fname, fexpr = arg
                        elif isinstance(arg, Expr) and arg.kind == "name":
                            fname, fexpr = arg.parts[0], arg
                        else:
                            raise BError("E_TYPE", f"Named record construction for {rec.name} expects field: expr or shorthand field names")
                        if fname not in field_map:
                            raise BError("E_NAME", f"Record {rec.name} has no field {fname}")
                        if fname in provided:
                            raise BError("E_NAME", f"Duplicate field {fname} in {rec.name}")
                        provided[fname] = self.infer(fexpr, symbols, expected_type=field_map[fname])
                    missing = [fname for fname, _ in rec.fields if fname not in provided]
                    if missing:
                        raise BError("E_ARITY", f"Record {rec.name} missing field(s): {', '.join(missing)}")
                    checked_nodes = []
                    for fname, ftype in rec.fields:
                        val = provided[fname]
                        self._check_type(val, ftype, f"field {fname} of {rec.name}")
                        checked_nodes.append(self._widen(val, ftype).node)
                    return self.val(Type(rec.name), "record_make", *checked_nodes,
                                    data={"record": rec.name, "fields": tuple(n for n, _ in rec.fields)})
                values = [self.infer(arg, symbols) for arg in raw_args]
                if len(values) != len(rec.fields):
                    raise BError("E_ARITY", f"Record {rec.name} expects {len(rec.fields)} fields, got {len(values)}")
                checked_nodes = []
                for (fname, ftype), val in zip(rec.fields, values):
                    self._check_type(val, ftype, f"field {fname} of {rec.name}")
                    checked_nodes.append(self._widen(val, ftype).node)
                return self.val(Type(rec.name), "record_make", *checked_nodes,
                                data={"record": rec.name, "fields": tuple(n for n, _ in rec.fields)})
            if has_named:
                raise BError("E_TYPE", "Named arguments are only supported for record constructors")
            values = [self.infer(arg, symbols) for arg in raw_args]
            path = self._foreign_path(target, symbols)
            ref = self.registry.lookup(path)
            binding = ref.binding if ref else None
            if binding is None and target.kind == "name":
                binding = symbols[target.parts[0]].signature
            if binding:
                label = path or target.parts[0]
                sig = self._resolve_binding(binding, values, label)
                if not sig.required <= len(values) <= len(sig.params):
                    wanted = str(sig.required) if sig.required == len(sig.params) else f"{sig.required}–{len(sig.params)}"
                    raise BError("E_ARITY", f"{label} expects {wanted} arguments, got {len(values)}")
                for idx, (v, expected) in enumerate(zip(values, sig.params), start=1):
                    self._check_type(v, expected, f"argument {idx} to {label}")
                    # Static false-friend check: JavaScript Number 53-bit precision boundary.
                    if path and path.startswith("js:") and type(v.constant) is int and abs(v.constant) > JS_MAX_SAFE_INT:
                        raise BError("E_FALSE_FRIEND",
                                     f"Integer literal {v.constant} passed to {label} exceeds JavaScript safe integer range (2^53 - 1)")
                precondition_proved = False
                if not path and target.kind == "name":
                    native = symbols[target.parts[0]]
                    if native.requires is not None:
                        constants = {
                            name: self._at_runtime_constant(value.constant, expected)
                            for name, value, expected in zip(native.parameter_names, values, sig.params)
                        }
                        known = contract_constant(native.requires, {
                            name: value for name, value in constants.items() if value is not NOT_CONST
                        })
                        if known is False:
                            raise BError("E_PRECONDITION", f"Call to {label} violates its requires clause")
                        precondition_proved = known is True
                children = [tv.node] + [self.guard(v.node, t) if path else v.node
                                       for v, t in zip(values, sig.params)]
                if ref is not None:
                    self.used_foreign.add(ref.path)
                    if ref.provenance not in ("curated-builtin", "verified-host-snapshot",
                                              "verified-go-host-snapshot", "verified-rs-host-snapshot",
                                              "user-declaration"):
                        assumed = f"{ref.path} ({ref.provenance}): signature assumed, not behavior proved"
                        if assumed not in self.assumptions:
                            self.assumptions.append(assumed)
                result = self.val(sig.result, "call", *children, foreign=path)
                if precondition_proved:
                    result.node = replace(result.node, precondition_proved=True)
                if path:
                    result.node = self.guard(result.node, sig.result)
                return result
            if path and path.startswith(("net:", "go:", "rs:")):
                raise BError("E_FOREIGN", f"Unregistered foreign call {path}")
            if tv.type != ANY:
                raise BError("E_TYPE", f"Cannot call value of type {tv.type}")
            if not path or not path.startswith("py:"):
                self.warn("W_UNCHECKED_FOREIGN", f"Unspecified call {path or '<computed>'}; no static signature available")
            return self.val(ANY, "call", tv.node, *(v.node for v in values), foreign=path)
        if kind in OPS:
            lhs, rhs = self.infer(p[0], symbols), self.infer(p[1], symbols)
            ld, rd = dim_of(lhs.type), dim_of(rhs.type)
            if kind == "add" and lhs.type == rhs.type == TEXT:
                typ = TEXT
            elif kind == "add" and lhs.type.name == rhs.type.name == "List":
                typ = unify(lhs.type, rhs.type)
                if typ.args[0] == ANY and lhs.type.args[0] != ANY and rhs.type.args[0] != ANY:
                    raise BError(self._mismatch_code(lhs.type.args[0], rhs.type.args[0]),
                                 f"Cannot concatenate lists of {lhs.type.args[0]} and {rhs.type.args[0]}")
                lhs, rhs = self._widen(lhs, typ), self._widen(rhs, typ)
            elif ld is not None or rd is not None:
                if kind in ("add", "sub"):
                    if ld != rd:
                        raise BError(self._mismatch_code(lhs.type, rhs.type),
                                     f"Cannot {kind} incompatible dimensioned types {lhs.type} and {rhs.type}")
                    typ = unify(lhs.type, rhs.type)
                elif kind == "mul":
                    if ld is not None and rd is not None:
                        raise BError(self._mismatch_code(lhs.type, rhs.type),
                                     f"Cannot multiply dimensioned values {lhs.type} and {rhs.type} directly; use scalar()")
                    if ld is not None and rhs.type in NUMERIC:
                        base = FLOAT if (is_dim_float(lhs.type) or rhs.type == FLOAT) else INT
                        typ = with_dim(base, ld)
                    elif rd is not None and lhs.type in NUMERIC:
                        base = FLOAT if (is_dim_float(rhs.type) or lhs.type == FLOAT) else INT
                        typ = with_dim(base, rd)
                    else:
                        raise BError("E_TYPE", f"mul requires numbers, got {lhs.type} and {rhs.type}")
                elif kind == "div":
                    if ld is not None and rd is None and rhs.type in NUMERIC:
                        typ = with_dim(FLOAT, ld)
                    elif ld is not None and ld == rd:
                        typ = FLOAT
                    else:
                        raise BError(self._mismatch_code(lhs.type, rhs.type),
                                     f"Cannot divide {lhs.type} by {rhs.type}")
                elif kind == "mod":
                    if ld != rd or not (is_dim_int(lhs.type) and is_dim_int(rhs.type)):
                        raise BError(self._mismatch_code(lhs.type, rhs.type),
                                     f"Cannot take remainder of {lhs.type} and {rhs.type}")
                    typ = lhs.type
                else:
                    raise BError("E_TYPE", f"Unsupported dimensioned op {kind}")
            elif lhs.type in NUMERIC + (ANY,) and rhs.type in NUMERIC + (ANY,):
                typ = FLOAT if kind == "div" else unify(lhs.type, rhs.type)
            else:
                raise BError("E_TYPE", f"{kind} requires numbers, got {lhs.type} and {rhs.type}")
            if kind in ("div", "mod") and rhs.constant == 0:
                raise BError("E_DIV_ZERO", "Division by zero is guaranteed")
            return self.val(typ, kind, lhs.node, rhs.node,
                            constant=self._const_op(OPS[kind], lhs.constant, rhs.constant))
        if kind == "cmp":
            lhs, op, rhs = p
            lv, rv = self.infer(lhs, symbols), self.infer(rhs, symbols)
            if op not in ("==", "!=") and not (supports_ordering(lv.type) and supports_ordering(rv.type)):
                raise BError("E_TYPE", f"Operator {op} cannot order {lv.type} and {rv.type}")
            if lv.type != ANY and rv.type != ANY and not (assignable(lv.type, rv.type) or assignable(rv.type, lv.type)):
                raise BError(self._mismatch_code(lv.type, rv.type), f"Cannot compare {lv.type} and {rv.type}")
            return self.val(BOOL, "cmp", lv.node, rv.node, data=op,
                            constant=self._const_op(CMP[op], lv.constant, rv.constant))
        if kind in ("and", "or"):
            left, right = self.infer(p[0], symbols), self.infer(p[1], symbols)
            self._check_type(left, BOOL, kind)
            self._check_type(right, BOOL, kind)
            fn = (lambda a, b: a and b) if kind == "and" else (lambda a, b: a or b)
            return self.val(BOOL, kind, left.node, right.node,
                            constant=self._const_op(fn, left.constant, right.constant))
        if kind in ("not", "neg"):
            operand = self.infer(p[0], symbols)
            if kind == "not":
                self._check_type(operand, BOOL, kind)
                return self.val(BOOL, kind, operand.node, constant=self._const_op(operator.not_, operand.constant))
            if is_dim_numeric(operand.type):
                return self.val(operand.type, kind, operand.node, constant=self._const_op(operator.neg, operand.constant))
            wanted = INT if operand.type == INT else FLOAT
            self._check_type(operand, wanted, kind)
            return self.val(operand.type, kind, operand.node,
                            constant=self._const_op(operator.neg, operand.constant))
        raise BError("E_INTERNAL", f"Unrecognized expression {kind}")

    def _contract(self, expr: Expr, scope: dict[str, Symbol], allowed: set[str], label: str) -> ExprIR:
        node = self.infer(expr, scope)
        self._check_type(node, BOOL, label)
        validate_predicate(node.node, allowed)
        return node.node

    def _pure_captures(self, node: ExprIR, locals_: set[str]) -> None:
        if node.op == "let_expr":
            self._pure_captures(node.operands[0], locals_)
            self._pure_captures(node.operands[1], locals_ | {node.data})
            return
        if node.op == "list_comp":
            self._pure_captures(node.operands[0], locals_)
            bound = locals_ | {node.data}
            for child in node.operands[1:]:
                self._pure_captures(child, bound)
            return
        if node.op == "history_count":
            self._pure_captures(node.operands[0], locals_)
            self._pure_captures(node.operands[1], locals_ | {node.data["past"], node.data["current"]})
            return
        if node.op == "summarize":
            self._pure_captures(node.operands[0], locals_)
            bound = locals_ | {node.data["binder"]}
            for field_operand in node.operands[1:]:
                self._pure_captures(field_operand, bound)
            return
        if node.op == "name" and node.data not in locals_:
            sym = self.symbols.get(node.data)
            if not sym or (sym.type != Type("Function")
                           and (sym.constant is NOT_CONST or type(sym.constant) not in (int, float, bool, str))):
                raise BError("E_EFFECT", f"Pure function captures unproven global state: {node.data}")
        for operand in node.operands:
            self._pure_captures(operand, locals_)

    def statement(self, stmt: Stmt) -> StmtIR:
        kind, p = stmt.kind, stmt.parts
        if kind == "permit":
            if self.started_statements or self.permitted_effects is not None:
                raise BError("E_EFFECT", "permit must be the first and only permission declaration")
            declared = p[0]
            if len(declared) != len(set(declared)) or any(x not in ALLOWED_EFFECTS for x in declared):
                raise BError("E_EFFECT", f"Unknown or duplicated permit categories; allowed: {', '.join(sorted(ALLOWED_EFFECTS))}")
            self.permitted_effects = tuple(sorted(declared))
            return StmtIR("permit")
        self.started_statements = True
        if kind == "unit_base":
            for uname in p[0]:
                if uname in self._all_dims():
                    raise BError("E_UNIT", f"Duplicate unit or currency {uname}")
                self.units[uname] = (uname, 1.0)
            return StmtIR("unit", name=",".join(p[0]))
        if kind == "unit_scale":
            uname, factor, base = p
            if uname in self._all_dims():
                raise BError("E_UNIT", f"Duplicate unit or currency {uname}")
            if base in self.currencies:
                raise BError("E_CURRENCY", f"Cannot define fixed unit scale on currency {base}")
            if base not in self.units:
                raise BError("E_UNIT", f"Base unit {base} is not declared")
            if factor <= 0.0 or not math.isfinite(factor):
                raise BError("E_UNIT", f"Unit scale factor for {uname} must be finite and positive")
            root_dim, base_scale = self.units[base]
            self.units[uname] = (root_dim, factor * base_scale)
            return StmtIR("unit", name=uname)
        if kind == "currency":
            for cname in p[0]:
                if cname in self._all_dims():
                    raise BError("E_CURRENCY", f"Duplicate currency or unit {cname}")
                self.currencies.add(cname)
            return StmtIR("currency", name=",".join(p[0]))
        if kind == "record":
            rname, raw_fields = p
            if rname in self.records or rname in self.symbols or rname in self._all_dims():
                raise BError("E_NAME", f"Redefinition of {rname}")
            seen: set[str] = set()
            fields: list[tuple[str, Type]] = []
            for fname, ftype_node in raw_fields:
                if fname in seen:
                    raise BError("E_NAME", f"Duplicate field {fname} in record {rname}")
                seen.add(fname)
                ftype = self._parse_type(ftype_node)
                if ftype == NONE:
                    raise BError("E_TYPE", f"Record field {fname} cannot have type None")
                fields.append((fname, ftype))
            rec = RecordDef(rname, tuple(fields))
            self.records[rname] = rec
            sig = Signature(tuple(t for _, t in fields), Type(rname))
            self._new(rname, Symbol(Type("Function"), signature=sig, effects=frozenset(), is_record=True))
            return StmtIR("record", name=rname)
        if kind == "probe":
            pv = self.infer(p[0])
            self._check_type(pv, BOOL, "probe")
            self.probes.append(pv.node)
            return StmtIR("probe", expr=pv.node)
        if kind == "expect":
            path_str, facet, expected_val = p
            parts = path_str.split(".")
            if len(parts) < 2:
                raise BError("E_FALSE_FRIEND", "expect requires an imported alias and member")
            sym = self.symbols.get(parts[0])
            if not sym or sym.type != MODULE or not sym.foreign:
                raise BError("E_FALSE_FRIEND", f"{parts[0]} must be an imported foreign module")
            fullname = sym.foreign + "." + ".".join(parts[1:])
            ref = self.registry.lookup(fullname)
            if ref is None:
                raise BError("E_FALSE_FRIEND", f"No registered foreign symbol {fullname} for expect")
            actual = ref.semantics_dict().get(facet)
            if actual != expected_val:
                raise BError(
                    "E_FALSE_FRIEND",
                    f"Semantic mismatch on {fullname}: expected {facet}={expected_val}, "
                    f"but ecosystem provides {facet}={actual or 'unspecified'}",
                )
            return StmtIR("expect", target=fullname)
        if kind == "adopt":
            fullname, alias = p
            adopted = adopt_python(fullname, alias)
            native = self.statement(adopted.statement)
            if native.effects or not native.declared_pure:
                raise BError("E_ADOPT", "Adopted code must be a pure B function")
            return replace(native, backend="py-source", target=(
                f"py:{fullname}@sha256:{adopted.sha256}"))
        if kind == "foreign":
            path, params, result, facets = p
            parts = path.split(".")
            if len(parts) < 2:
                raise BError("E_FOREIGN", "Foreign declaration requires an imported alias and a member")
            sym = self.symbols.get(parts[0])
            if not sym or sym.type != MODULE or not sym.foreign:
                raise BError("E_FOREIGN", f"{parts[0]} must be an imported foreign module")
            fullname = sym.foreign + "." + ".".join(parts[1:])
            if self.registry.lookup(fullname):
                raise BError("E_FOREIGN", f"A binding already exists for {fullname}")
            if fullname.startswith(("net:", "go:", "rs:")):
                raise BError("E_FOREIGN", "Custom declarations require a host adapter; only registered bindings work")
            sig = Signature(tuple(self._parse_type(t) for t in params), self._parse_type(result))
            if any(t in (NONE, MODULE) for t in (*sig.params, sig.result)):
                raise BError("E_TYPE", "Foreign signatures cannot use internal None or Module types")
            if fullname.startswith("js:"):
                jsmeta.check_declaration(sym.foreign[3:], parts[1:], sig)
            self.registry.add(fullname, sig, "user-declaration", dict(facets) if facets else None)
            self.assumptions.append(f"{fullname}({', '.join(map(str, sig.params))}) -> {sig.result}")
            return StmtIR("foreign", target=fullname)
        if kind == "use":
            backend, path, alias = p
            if backend == "py":
                found = inspect_python(path)
                if found.source_kind == "unavailable":
                    raise BError("E_IMPORT", f"Python module {path} is not installed")
                self.registry.add_python_module(path, found)
            elif backend == "js":
                jsmeta.check_target(path)
                for name, sig in jsmeta.CATALOG.get(path, {}).items():
                    key = f"js:{path}.{name}"
                    if not self.registry.lookup(key):
                        self.registry.add(key, sig, jsmeta.provenance(path))
            elif backend == "net":
                if not any(k.startswith(f"net:{path}.") for k in self.registry.symbols):
                    raise BError("E_IMPORT", f"No registered .NET metadata for {path}")
            elif backend == "go":
                if not any(k.startswith(f"go:{path}.") for k in self.registry.symbols):
                    raise BError("E_IMPORT", f"No registered Go metadata for {path}")
            elif backend == "rs":
                if not any(k.startswith(f"rs:{path}.") for k in self.registry.symbols):
                    raise BError("E_IMPORT", f"No registered Rust metadata for {path}")
            else:
                raise BError("E_IMPORT", f"Unknown backend {backend}")
            self._new(alias, Symbol(MODULE, foreign=f"{backend}:{path}"))
            return StmtIR("import", name=alias, backend=backend, target=path, effects=("foreign",))
        if kind == "let":
            name, annotation, expr = p
            wanted_hint = self._parse_type(annotation) if annotation is not None else None
            value = self.infer(expr, expected_type=wanted_hint)
            wanted = wanted_hint if wanted_hint is not None else value.type
            if wanted == NONE:
                raise BError("E_TYPE", "A variable cannot be annotated None")
            self._check_type(value, wanted, f"assignment to {name}")
            if wanted.name == "List" and expr.kind == "list":
                for element in expr.parts:
                    self._check_type(self.infer(element), wanted.args[0], f"element of {name}")
            alias = self._foreign_path(expr, self.symbols) if wanted == MODULE else None
            self._new(name, Symbol(wanted, constant=self._at_runtime_constant(value.constant, wanted),
                                   foreign=alias if alias and alias.startswith("js:") else None,
                                   known_fields=value.known_fields if annotation is None else None))
            node = self.guard(value.node, wanted) if annotation is not None else value.node
            return StmtIR("let", name=name, typ=wanted, expr=node,
                          effects=tuple(sorted(expression_effects(node, self.symbols))))
        if kind == "fn":
            name, parameters, result_annotation, expr, declared_pure, raw_pre, raw_post = p
            names = [param_name for param_name, _ in parameters]
            if len(names) != len(set(names)):
                raise BError("E_NAME", f"Duplicate parameter in {name}")
            if any(n in self.symbols or n.startswith("_b_") for n in names):
                raise BError("E_NAME", "Parameters cannot shadow existing names or runtime internals")
            if raw_post is not None and "result" in names:
                raise BError("E_CONTRACT", "result is reserved for the ensures clause")
            types = [self._parse_type(t) for _, t in parameters]
            if result_annotation is not None:
                result_type = self._parse_type(result_annotation)
                signature = Signature(tuple(types), result_type)
                self._new(name, Symbol(Type("Function"), signature=signature, effects=None,
                                       parameter_names=tuple(names)))
                local = {**self.symbols, **{n: Symbol(t) for n, t in zip(names, types)}}
            else:
                local = {**self.symbols, **{n: Symbol(t) for n, t in zip(names, types)}}
                result_type = None
            pre = self._contract(raw_pre, local, set(names), "requires") if raw_pre else None
            if pre is not None:
                contract_restrict(pre, {n for n, t in zip(names, types) if t == INT})
                if contract_constant(pre, {}) is False:
                    raise BError("E_PRECONDITION_EMPTY", "Function requires false for every input")
            body = self.infer(expr, local, expected_type=result_type)
            if result_type is None:
                result_type = body.type
                if result_type == NONE:
                    raise BError("E_TYPE", f"Function {name} cannot infer None return type; annotate Option[...]")
                signature = Signature(tuple(types), result_type)
                self._new(name, Symbol(Type("Function"), signature=signature, effects=None,
                                       parameter_names=tuple(names)))
            else:
                self._check_type(body, result_type, f"return of {name}")
            effects = expression_effects(body.node, local)
            if declared_pure:
                if effects:
                    raise BError("E_EFFECT", f"Function {name} declared pure, but has effects: {', '.join(sorted(effects))}")
                self._pure_captures(body.node, set(names))
            self.symbols[name].effects = effects
            self.symbols[name].requires = pre
            proof = None
            post = None
            if raw_post is not None:
                post_scope = {**local, "result": Symbol(result_type)}
                post = self._contract(raw_post, post_scope, set(names) | {"result"}, "ensures")
            if cases := self.additional_cases.get(name):
                if not declared_pure or result_type != BOOL:
                    raise BError("E_ALSO", f"also requires {name} to declare a pure Bool result")
                body.node = extend_predicate(name, dict(zip(names, types)), cases, pre, post, body.node)
            if post is not None:
                proof = verify_post(pre, body.node, post, dict(zip(names, types)), result_type)
            return StmtIR("fn", name=name, typ=result_type, expr=self.guard(body.node, result_type),
                          params=tuple(zip(names, types)), effects=tuple(sorted(effects)),
                          requires=pre, ensures=post, verification=proof, declared_pure=declared_pure)
        if kind == "print":
            value = self.infer(p[0])
            return StmtIR("print", expr=value.node,
                          effects=tuple(sorted({"console"} | set(expression_effects(value.node, self.symbols)))))
        if kind == "assert":
            value = self.infer(p[0])
            self._check_type(value, BOOL, "assert")
            if value.constant is False:
                raise BError("E_ASSERT", "Assertion is statically false")
            if value.constant is NOT_CONST:
                self.warn("W_RUNTIME_ASSERT", "Assertion can only be checked while executing")
            return StmtIR("assert", expr=value.node,
                          effects=tuple(sorted(expression_effects(value.node, self.symbols))))
        raise BError("E_INTERNAL", f"Unrecognized statement {kind}")

    def compile(self, source: str, *, conditional_guarantees: bool = True) -> Compiled:
        try:
            parsed = parse(source)
        except LarkError as exc:
            raise BError("E_SYNTAX", str(exc)) from exc
        self.additional_cases = additional_cases(parsed)
        statements = tuple(self.statement(s) for s in parsed if s.kind not in ("next", "also"))
        detected = tuple(sorted(set().union(*(statement_effects(s) for s in statements))))
        if self.permitted_effects is not None:
            denied = set(detected) - set(self.permitted_effects)
            if denied:
                raise BError("E_EFFECT", f"Program uses forbidden effects: {', '.join(sorted(denied))}")
        units_ir = tuple((n, b, s) for n, (b, s) in sorted(self.units.items()))
        program = ProgramIR(
            statements, self.registry.export(self.used_foreign),
            tuple(self.assumptions), permitted_effects=self.permitted_effects,
            detected_effects=detected,
            records=tuple(self.records.values()),
            units=units_ir,
            currencies=tuple(sorted(self.currencies)),
            probes=tuple(self.probes),
        )
        if self.additional_cases:
            from .preservation import validate_preservation
            validate_preservation(program, [s for s in parsed if s.kind == "also"])
        analysis = analyze(program, conditional_guarantees=conditional_guarantees)
        upgraded = {}
        for item in analysis.obligations:
            if item.kind == "ensures" and item.status == "proved":
                if item.proof_method == "affine-equality":
                    upgraded[item.caller] = "proved-affine"
                elif item.proof_method == "conditional-guarantee":
                    upgraded[item.caller] = "proved-conditional"
                else:
                    upgraded[item.caller] = "proved-composition" if item.dependencies else "proved-interval"
            elif item.kind in ("ensures", "requires") and item.status != "proved":
                code = "W_RUNTIME_POSTCONDITION" if item.kind == "ensures" else "W_RUNTIME_PRECONDITION"
                self.warn(code, item.describe())
        statements = tuple(
            replace(s, verification=upgraded[s.name])
            if s.op == "fn" and s.name in upgraded and s.verification == "runtime-check" else s
            for s in statements
        )
        program = replace(program, statements=statements)
        optimized = optimize(program)
        python_module = PythonLowerer().lower(optimized.program)
        result = Compiled(ast.unparse(python_module) + "\n", compile(python_module, "<B>", "exec"),
                          self.diagnostics, self.assumptions, program, optimized.program, optimized.folds, analysis)
        targets = [s.parts[0] for s in parsed if s.kind == "next"]
        if targets:
            handoff = materialize(source)
            try:
                revised = Compiler().compile(handoff.source, conditional_guarantees=conditional_guarantees)
            except BError as error:
                raise BError(error.code, f"Pending handoff: {error.message}") from error
            validate_rewrite(result.ir, revised.ir, targets, self.additional_cases)
            for obligation in revised.analysis.obligations:
                if obligation.status == "refuted" and obligation not in result.analysis.obligations:
                    raise BError("E_HANDOFF", f"Pending handoff: {obligation.describe()}")
            for diagnostic in revised.diagnostics:
                if diagnostic not in result.diagnostics:
                    self.warn(diagnostic.code, f"Pending handoff: {diagnostic.message}")
            result.handoff = handoff
            result.pending_analysis = revised.analysis
        return result


def compile_b(source: str, strict: bool = False, *, conditional_guarantees: bool = True) -> Compiled:
    try:
        result = Compiler().compile(source, conditional_guarantees=conditional_guarantees)
    except RecursionError as exc:
        raise BError("E_DEPTH", "Program exceeds the compiler's nesting capacity. "
                     "Split deeply nested expressions or long decision tables into smaller functions.") from exc
    if strict and result.diagnostics:
        raise BError("E_STRICT", "Unresolved checks: " + "; ".join(d.code for d in result.diagnostics))
    return result


def parse_postcondition(text: str, fn: StmtIR) -> ExprIR:
    """Type-check an independently supplied assertion in this function's result scope."""
    if any(name == "result" for name, _ in fn.params):
        raise BError("E_EXPECT", "A parameter named result conflicts with the return value")
    try:
        statements = parse("assert " + text)
    except LarkError as exc:
        raise BError("E_EXPECT", "Expected one B postcondition expression") from exc
    if len(statements) != 1 or statements[0].kind != "assert":
        raise BError("E_EXPECT", "Expected one B postcondition expression")
    scope = {name: Symbol(typ) for name, typ in fn.params}
    scope["result"] = Symbol(fn.typ)
    return Compiler()._contract(statements[0].parts[0], scope, set(scope), "expected postcondition")
