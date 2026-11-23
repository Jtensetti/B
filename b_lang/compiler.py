"""B 0.25 compiler: parse -> typed BIR -> Python backend.

The checker never evaluates B source or foreign implementations. Foreign
signatures are assumptions, not proofs. The executable backend consumes typed
BIR rather than reconstructing B semantics directly from surface syntax.
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
from .handoff import Handoff, materialize, validate_rewrite
from .history import history_plan
from .interop import ForeignCatalog
from . import jsmeta
from .ir import ExprIR, ProgramIR, StmtIR
from .lowering import PythonLowerer
from .optimizer import optimize
from .model import Expr, Stmt, parse
from .netmeta import net_bindings
from .types import (
    Type, BError, INT, FLOAT, BOOL, TEXT, NONE, ANY, MODULE,
    ATTRIBUTES, Signature, Overloads, Binding, assignable,
    from_syntax, unify, needs_dynamic_guard, needs_numeric_widening, option, supports_ordering,
    record_fields, record_type, KNOWN,
)

NOT_CONST = object()
NUMERIC = (INT, FLOAT)
CORE_WORDS = frozenset({"len", "sorted", "keys", "values", "text", "join"})


def _record_label(typ: Type) -> str:
    from .types import RECORDS
    for name, known in RECORDS.items():
        if known == typ:
            return name
    return "this record"
OPS = {"add": operator.add, "sub": operator.sub, "mul": operator.mul,
       "div": operator.truediv, "mod": operator.mod}
CMP = {"==": operator.eq, "!=": operator.ne, "<": operator.lt,
       ">": operator.gt, "<=": operator.le, ">=": operator.ge}


@dataclass
class Value:
    type: Type
    node: ExprIR
    constant: Any = NOT_CONST


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


class Compiler:
    def __init__(self):
        self.symbols: dict[str, Symbol] = {}
        self.diagnostics: list[Diagnostic] = []
        self.assumptions: list[str] = []
        self.registry = ForeignCatalog()
        self.registry.add_net_registry(net_bindings())
        self.used_foreign: set[str] = set()
        self.permitted_effects: tuple[str, ...] | None = None
        self.started_statements = False
        self.additional_cases: dict[str, list[tuple]] = {}
        self.original_rules: dict = {}
        self.learned: dict = {}

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
        # An Int and its closest representable Float can compare unequal.
        # Record the same conversion in the BIR and in constant evaluation.
        scalar = wanted.args[0] if wanted.name == "Option" else wanted
        known = (None if value.constant is None and wanted.name == "Option"
                 else self._at_runtime_constant(value.constant, scalar))
        return Value(wanted, self.guard(value.node, wanted), known)

    def _check_type(self, value: Value, expected: Type, context: str):
        if not assignable(value.type, expected):
            raise BError("E_TYPE", f"{context}: expected {expected}, got {value.type}")
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
        """Use only scalar constants with the SAME semantics as runtime guards.

        An Int passed as Float is rounded at a boundary, and collection guards
        may snapshot/coerce members. Those raw source constants are not safe
        evidence for a requirement or assertion.
        """
        if value is NOT_CONST:
            return NOT_CONST
        if wanted == INT and type(value) is int:
            return value
        if wanted == BOOL and type(value) is bool:
            return value
        if wanted == TEXT and type(value) is str:
            return value
        if wanted == FLOAT and type(value) in (int, float):
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

    @staticmethod
    def _resolve_binding(binding: Binding, values: list[Value], target: str) -> Signature:
        """Only unambiguous matching overloads may be used for static typing."""
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
            return scope[ex.parts[0]].foreign
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

    def _core_word(self, word: str, args: list[Value]) -> Value:
        """A few words almost every program needs, typed generically, run by Python's builtins."""
        arity = {"join": 2}.get(word, 1)
        if len(args) != arity:
            raise BError("E_ARITY", f"{word} takes {arity} argument{'s' if arity > 1 else ''}, got {len(args)}")
        first = args[0]
        kind = first.type.name
        if word == "len":
            if kind not in ("List", "Dict") and first.type != TEXT:
                raise BError("E_TYPE", f"len needs a List, Dict or Text, got {first.type}")
            result = INT
        elif word == "sorted":
            if kind != "List" or not supports_ordering(first.type.args[0]):
                raise BError("E_TYPE", f"sorted needs a List of Int, Float or Text, got {first.type}")
            result = first.type
        elif word in ("keys", "values"):
            if kind != "Dict":
                raise BError("E_TYPE", f"{word} needs a Dict[Text, T], got {first.type}")
            result = Type("List", (TEXT,)) if word == "keys" else Type("List", (first.type.args[1],))
        elif word == "text":
            if first.type not in (INT, FLOAT, TEXT, BOOL):
                raise BError("E_TYPE", f"text needs an Int, Float, Text or Bool, got {first.type}")
            result = TEXT
        else:  # join
            if first.type != Type("List", (TEXT,)) or args[1].type != TEXT:
                raise BError("E_TYPE", "join needs a List[Text] and a Text separator")
            result = TEXT
        return self.val(result, "core", *(a.node for a in args), data=word)

    def _each(self, ex: Expr, scope: dict[str, Symbol]) -> Value:
        """[value for x in xs where c] and {key: value for k, v in d where c}."""
        shape, raw_key, raw_value, binders, source, raw_condition = ex.parts
        collection = self.infer(source, scope)
        kind = collection.type.name
        if kind == "List":
            if len(binders) != 1:
                raise BError("E_TYPE", "A list gives one name per item: for x in xs")
            types = [collection.type.args[0]]
        elif kind == "Dict":
            types = [TEXT, collection.type.args[1]][:len(binders)]
        elif collection.type == ANY:
            types = [ANY] * len(binders)
            self.warn("W_DYNAMIC_TYPE", "A collection from an untyped boundary is checked at runtime")
        else:
            raise BError("E_TYPE", f"for needs a List[T] or Dict[Text, T], got {collection.type}")
        if len(set(binders)) != len(binders):
            raise BError("E_NAME", "for needs two different names")
        elements = scope.copy()
        for name, typ in zip(binders, types):
            if name in elements or name.startswith("_b_") or name in {"true", "false", "none", "if", "not"}:
                raise BError("E_NAME", f"for cannot bind {name}: name is already in scope or reserved")
            elements[name] = Symbol(typ)
        operands = [collection.node]
        if raw_key is not None:
            key = self.infer(raw_key, elements)
            self._check_type(key, TEXT, "dictionary key")
            operands.append(key.node)
        value = self.infer(raw_value, elements)
        operands.append(value.node)
        if raw_condition is not None:
            condition = self.infer(raw_condition, elements)
            self._check_type(condition, BOOL, "where")
            operands.append(condition.node)
        result = Type("List", (value.type,)) if shape == "list" else Type("Dict", (TEXT, value.type))
        return self.val(result, "each", *operands,
                        data={"shape": shape, "binders": binders, "source": kind,
                              "condition": raw_condition is not None})

    def _summarize(self, ex: Expr, scope: dict[str, Symbol]) -> Value:
        binder, source, fields = ex.parts
        collection, elements = self._list_scope("summarize", source, scope, binder)
        operands = [collection.node]
        reductions = []
        labels = set()
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
                self._check_type(value, INT, f"summarize {label} value")
                value_index = len(operands)
                operands.append(value.node)
            reductions.append((label, reducer, value_index, guard_index, default))
        return self.val(Type("Dict", (TEXT, INT)), "summarize", *operands,
                        data={"binder": binder, "fields": tuple(reductions)})

    def infer(self, ex: Expr, scope: dict[str, Symbol] | None = None) -> Value:
        symbols = self.symbols if scope is None else scope
        kind, p = ex.kind, ex.parts
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
        if kind == "each":
            return self._each(ex, symbols)
        if kind == "contains":
            item, container = self.infer(p[0], symbols), self.infer(p[1], symbols)
            kind_ = container.type.name
            if kind_ == "List":
                element = container.type.args[0]
            elif kind_ == "Dict" or container.type == TEXT:
                element = TEXT
            else:
                raise BError("E_TYPE", f"in needs a List, Dict, Text or a group, got {container.type}")
            if not (assignable(item.type, element) or assignable(element, item.type)):
                raise BError("E_TYPE", f"Cannot look for {item.type} in {container.type}")
            return self.val(BOOL, "contains", item.node, container.node)
        if kind == "lookup" and self.infer(p[0], symbols).type.name == "List":
            sequence, index = self.infer(p[0], symbols), self.infer(p[1], symbols)
            self._check_type(index, INT, "list index")
            return self.val(option(sequence.type.args[0]), "index", sequence.node, index.node)
        if kind == "lookup":
            dictionary = self.infer(p[0], symbols)
            if dictionary.type.name != "Dict":
                raise BError("E_TYPE", f"Key lookup needs a Dict[Text, T], got {dictionary.type}")
            key = self.infer(p[1], symbols)
            self._check_type(key, TEXT, "dictionary lookup key")
            return self.val(option(dictionary.type.args[1]), "lookup", dictionary.node, key.node)
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
                    raise BError("E_TYPE", f"Incompatible coalesce values: {inner} and {right.type}")
                typ = Type("Option", (merged,))
            elif right.type == ANY and inner != ANY:
                self._check_type(right, inner, "?? fallback")
                typ = inner
            else:
                typ = unify(inner, right.type)
                if typ == ANY and inner != ANY and right.type != ANY:
                    raise BError("E_TYPE", f"Incompatible coalesce values: {inner} and {right.type}")
            left = self._widen(left, option(typ))
            right = self._widen(right, typ)
            const = right.constant if left.constant is None else left.constant
            if left.constant is NOT_CONST:
                const = NOT_CONST
            return self.val(typ, "coalesce", left.node, right.node, constant=const)
        if kind == "conditional":
            cv = self.infer(p[0], symbols)
            self._check_type(cv, BOOL, "if condition")
            yv, nv = self.infer(p[1], symbols), self.infer(p[2], symbols)
            typ = unify(yv.type, nv.type)
            if typ == ANY and yv.type != ANY and nv.type != ANY:
                raise BError("E_TYPE", f"if branches have incompatible types: {yv.type} versus {nv.type}")
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
            return self.val(sym.type, "name", data=name, constant=sym.constant)
        if kind == "list":
            items = [self.infer(i, symbols) for i in p]
            element_type = ANY
            if items:
                element_type = items[0].type
                for i in items[1:]:
                    element_type = unify(element_type, i.type)
            if element_type == ANY and all(i.type != ANY for i in items) and len(items) > 1:
                raise BError("E_TYPE", "List contains incompatible element types")
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
                        raise BError("E_TYPE", f"Dictionary values disagree: {value_type} versus {val.type}")
                    value_type = merged
            value_type = value_type or ANY
            flattened = [node for key, val in pairs
                         for node in (key.node, self._widen(val, value_type).node)]
            return self.val(Type("Dict", (TEXT, value_type)), "dict", *flattened)
        if kind == "record":
            fields = [(name, self.infer(value, symbols)) for name, value in p]
            typ = record_type([(name, value.type) for name, value in fields])
            return self.val(typ, "record", *(value.node for _, value in sorted(fields, key=lambda f: f[0])),
                            data=tuple(sorted(name for name, _ in fields)))
        if kind == "attr":
            base, name = p
            bv = self.infer(base, symbols)
            if bv.type.name == "Record":
                fields = record_fields(bv.type)
                if name not in fields:
                    raise BError("E_TYPE", f"No field {name} in {_record_label(bv.type)}; "
                                 f"fields: {', '.join(sorted(fields))}")
                return self.val(fields[name], "field", bv.node, data=name)
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
            if path and path.startswith("py:"):
                self.warn("W_UNCHECKED_FOREIGN", f"Unspecified Python symbol {path}; no static signature available")
            return self.val(ANY, "attr", bv.node, data=name, foreign=path)
        if kind == "invoke" and p[0].kind == "name" and p[0].parts[0] in CORE_WORDS \
                and p[0].parts[0] not in symbols:
            return self._core_word(p[0].parts[0], [self.infer(a, symbols) for a in p[1]])
        if kind == "invoke":
            target, raw_args = p
            tv = self.infer(target, symbols)
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
                    if ref.provenance not in ("curated-builtin", "verified-host-snapshot", "user-declaration"):
                        assumed = f"{ref.path} ({ref.provenance}): signature assumed, not behavior proved"
                        if assumed not in self.assumptions:
                            self.assumptions.append(assumed)
                result = self.val(sig.result, "call", *children, foreign=path)
                if precondition_proved:
                    result.node = replace(result.node, precondition_proved=True)
                if path:
                    result.node = self.guard(result.node, sig.result)
                return result
            if path and path.startswith("net:"):
                raise BError("E_FOREIGN", f"Unregistered .NET call {path}")
            if tv.type != ANY:
                raise BError("E_TYPE", f"Cannot call value of type {tv.type}")
            if not path or not path.startswith("py:"):
                self.warn("W_UNCHECKED_FOREIGN", f"Unspecified call {path or '<computed>'}; no static signature available")
            return self.val(ANY, "call", tv.node, *(v.node for v in values), foreign=path)
        if kind in OPS:
            lhs, rhs = self.infer(p[0], symbols), self.infer(p[1], symbols)
            typ = FLOAT if kind == "div" else unify(lhs.type, rhs.type)
            if kind == "add" and lhs.type == rhs.type == TEXT:
                typ = TEXT
            elif kind == "add" and lhs.type.name == rhs.type.name == "List":
                typ = unify(lhs.type, rhs.type)
                lhs, rhs = self._widen(lhs, typ), self._widen(rhs, typ)
            elif not (lhs.type in NUMERIC + (ANY,) and rhs.type in NUMERIC + (ANY,)):
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
                raise BError("E_TYPE", f"Cannot compare {lv.type} and {rv.type}")
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
            wanted = BOOL if kind == "not" else INT if operand.type == INT else FLOAT
            self._check_type(operand, wanted, kind)
            return self.val(BOOL if kind == "not" else operand.type, kind, operand.node,
                            constant=self._const_op(operator.not_ if kind == "not" else operator.neg, operand.constant))
        raise BError("E_INTERNAL", f"Unrecognized expression {kind}")

    def _contract(self, expr: Expr, scope: dict[str, Symbol], allowed: set[str], label: str) -> ExprIR:
        node = self.infer(expr, scope)
        self._check_type(node, BOOL, label)
        validate_predicate(node.node, allowed)
        return node.node

    def _pure_captures(self, node: ExprIR, locals_: set[str]) -> None:
        if node.op == "history_count":
            self._pure_captures(node.operands[0], locals_)
            self._pure_captures(node.operands[1], locals_ | {node.data["past"], node.data["current"]})
            return
        if node.op == "each":
            self._pure_captures(node.operands[0], locals_)
            for child in node.operands[1:]:
                self._pure_captures(child, locals_ | set(node.data["binders"]))
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
        if kind == "adopt":
            fullname, alias = p
            adopted = adopt_python(fullname, alias)
            # Reuse the *native* function checker; do not treat a Python source
            # annotation as a license to mark arbitrary external code pure.
            native = self.statement(adopted.statement)
            if native.effects or not native.declared_pure:
                raise BError("E_ADOPT", "Adopted code must be a pure B function")
            return replace(native, backend="py-source", target=(
                f"py:{fullname}@sha256:{adopted.sha256}"))
        if kind in ("foreign", "foreign_units"):
            path, params, result = p
            parts = path.split(".")
            if len(parts) < 2:
                raise BError("E_FOREIGN", "Foreign declaration requires an imported alias and a member")
            sym = self.symbols.get(parts[0])
            if not sym or sym.type != MODULE or not sym.foreign:
                raise BError("E_FOREIGN", f"{parts[0]} must be an imported foreign module")
            fullname = sym.foreign + "." + ".".join(parts[1:])
            sig = Signature(tuple(from_syntax(t) for t in params), from_syntax(result))
            existing = self.registry.lookup(fullname)
            if existing:
                # A unit annotation may restate a discovered signature in B's units. It
                # can only restate it: B never overrides what the relative's metadata says.
                same = (getattr(existing.binding, "params", None) == sig.params
                        and getattr(existing.binding, "result", None) == sig.result)
                if kind == "foreign_units" and same:
                    return StmtIR("foreign", target=fullname)
                raise BError("E_FOREIGN", f"A binding already exists for {fullname}"
                             + (" with a different signature" if kind == "foreign_units" else ""))
            if fullname.startswith("net:"):
                raise BError("E_FOREIGN", "Custom .NET declarations require a host adapter; only registered .NET bindings work")
            if any(t in (NONE, MODULE) for t in (*sig.params, sig.result)):
                raise BError("E_TYPE", "Foreign signatures cannot use internal None or Module types")
            if fullname.startswith("js:"):
                jsmeta.check_declaration(sym.foreign[3:], parts[1:], sig)
            self.registry.add(fullname, sig, "user-declaration")
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
            else:
                raise BError("E_IMPORT", f"Unknown backend {backend}")
            self._new(alias, Symbol(MODULE, foreign=f"{backend}:{path}"))
            return StmtIR("import", name=alias, backend=backend, target=path, effects=("foreign",))
        if kind == "let":
            name, annotation, expr = p
            value = self.infer(expr)
            wanted = from_syntax(annotation) if annotation is not None else value.type
            if wanted == NONE:
                raise BError("E_TYPE", "A variable cannot be annotated None")
            self._check_type(value, wanted, f"assignment to {name}")
            if wanted.name == "List" and expr.kind == "list":
                for element in expr.parts:
                    self._check_type(self.infer(element), wanted.args[0], f"element of {name}")
            alias = self._foreign_path(expr, self.symbols) if wanted == MODULE else None
            self._new(name, Symbol(wanted, constant=self._at_runtime_constant(value.constant, wanted),
                                   foreign=alias if alias and alias.startswith("js:") else None))
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
            types = [from_syntax(t) for _, t in parameters]
            result_type = from_syntax(result_annotation)
            signature = Signature(tuple(types), result_type)
            self._new(name, Symbol(Type("Function"), signature=signature, effects=None,
                                   parameter_names=tuple(names)))
            local = {**self.symbols, **{n: Symbol(t) for n, t in zip(names, types)}}
            pre = self._contract(raw_pre, local, set(names), "requires") if raw_pre else None
            if pre is not None:
                contract_restrict(pre, {n for n, t in zip(names, types) if t == INT})
                if contract_constant(pre, {}) is False:
                    raise BError("E_PRECONDITION_EMPTY", "Function requires false for every input")
            body = self.infer(expr, local)
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
                self.original_rules[name] = body.node
                body.node = extend_predicate(name, dict(zip(names, types)), cases, pre, post, body.node)
            if post is not None:
                proof = verify_post(pre, body.node, post, dict(zip(names, types)), result_type)
            return StmtIR("fn", name=name, typ=result_type, expr=self.guard(body.node, result_type),
                          params=tuple(zip(names, types)), effects=tuple(sorted(effects)),
                          requires=pre, ensures=post, verification=proof, declared_pure=declared_pure)
        if kind == "library_example":
            call, expected, tolerance, text = p
            actual, wanted = self.infer(call), self.infer(expected)
            operands = [actual.node, wanted.node]
            if tolerance is not None:
                margin = self.infer(tolerance)
                for value, label in ((actual, "result"), (wanted, "expected value"), (margin, "tolerance")):
                    if value.type not in NUMERIC + (ANY,):
                        raise BError("E_TYPE", f"{text}: 'within' needs a numeric {label}, got {value.type}")
                operands.append(margin.node)
            elif actual.type != ANY and not (assignable(wanted.type, actual.type) or assignable(actual.type, wanted.type)):
                raise BError("E_TYPE", f"{text}: the library returns {actual.type}, the example states {wanted.type}")
            text = text.partition("\t")[0]
            self.assumptions.append(f"{text}: checked when the program reaches it, not while type checking")
            effects = expression_effects(actual.node, self.symbols)
            return StmtIR("example_check", expr=ExprIR("example", BOOL, tuple(operands)), target=p[3],
                          effects=tuple(sorted(effects)))
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

    def _check_examples(self, program: ProgramIR, parsed) -> None:
        """Every current example is a checked fact about the final program."""
        from .learn import resolve_examples
        from .precedent import call_text, literal
        from .revision_witness import evaluate_scalar
        rows = {}
        for statement in parsed:
            if statement.kind == "example" and "." not in statement.parts[0]:
                rows.setdefault(statement.parts[0], []).append(statement)
        for name, statements in rows.items():
            for arguments, expected in resolve_examples(name, statements):
                known, actual = evaluate_scalar(program, name, arguments)
                if not known:
                    self.warn("W_EXAMPLE_UNCHECKED", f"Cannot evaluate example {call_text(name, arguments)} "
                              "before running")
                elif type(actual) is not type(expected) or actual != expected:
                    raise BError("E_EXAMPLE", f"example {call_text(name, arguments)} == {literal(expected)}, "
                                 f"but the program gives {literal(actual)}")
        for learned in self.learned.values():
            if not learned.determined:
                self.warn("W_EXAMPLES_OPEN", f"{learned.name} is not settled by its examples: "
                          f"{learned.question_text()} Run 'b ask' to answer.")

    def compile(self, source: str, *, conditional_guarantees: bool = True) -> Compiled:
        try:
            parsed = parse(source)
        except LarkError as exc:
            raise BError("E_SYNTAX", str(exc)) from exc
        from .types import RECORDS, record_type
        RECORDS.clear()
        declared = {}
        for statement in parsed:
            if statement.kind == "record":
                name, fields = statement.parts
                if name in declared or name in KNOWN or name in ("List", "Dict", "Option", "Record"):
                    raise BError("E_TYPE", f"Type {name} is already defined")
                declared[name] = fields

        def resolve(name, visiting=()):
            # Records are structural, so a record cannot contain itself.
            if name in RECORDS:
                return
            if name in visiting:
                raise BError("E_TYPE", f"Record {name} contains itself: " + " -> ".join((*visiting, name)))

            def names(node):
                yield node[0]
                for child in node[1]:
                    yield from names(child)

            for _, field_type in declared[name]:
                for used in names(field_type):
                    if used in declared:
                        resolve(used, (*visiting, name))
            RECORDS[name] = record_type([(n, from_syntax(t)) for n, t in declared[name]])

        for name in declared:
            resolve(name)
        from .learn import expand
        parsed, self.learned = expand(parsed)
        from .library_examples import to_checks
        from .units import BORROWED, check as check_units
        parsed = check_units(to_checks(parsed))
        for unit, provenance in sorted(BORROWED.items()):
            self.assumptions.append(f"unit {unit} from {provenance}: definition borrowed, not checked by B")
        self.additional_cases = additional_cases(parsed)
        statements = tuple(self.statement(s) for s in parsed if s.kind not in ("next", "also", "example", "domain", "group", "know", "record"))
        detected = tuple(sorted(set().union(*(statement_effects(s) for s in statements))))
        if self.permitted_effects is not None:
            denied = set(detected) - set(self.permitted_effects)
            if denied:
                raise BError("E_EFFECT", f"Program uses forbidden effects: {', '.join(sorted(denied))}")
        program = ProgramIR(statements, self.registry.export(self.used_foreign),
                            tuple(self.assumptions), permitted_effects=self.permitted_effects,
                            detected_effects=detected)
        if any(s.kind == "example" for s in parsed):
            self._check_examples(program, parsed)
        if self.additional_cases:
            from .preservation import validate_preservation
            validate_preservation(program, [s for s in parsed if s.kind == "also"])
            from .precedent import validate_likeness
            for code, message in validate_likeness(program, self.original_rules,
                                                   [s for s in parsed if s.kind == "also"]):
                self.warn(code, message)
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
