"""B 0.5 compiler: parse -> typed BIR -> Python backend.

The checker never evaluates B source or foreign implementations. Foreign
signatures are assumptions, not proofs. The executable backend consumes typed
BIR rather than reconstructing B semantics directly from surface syntax.
"""
from __future__ import annotations

import ast
import importlib.util
import operator
from dataclasses import dataclass
from typing import Any

from lark.exceptions import LarkError

from .discovery import inspect_python
from .interop import ForeignCatalog
from .ir import ExprIR, ProgramIR, StmtIR
from .lowering import PythonLowerer
from .optimizer import optimize
from .model import Expr, Stmt, parse
from .netmeta import net_bindings
from .types import (
    Type, BError, INT, FLOAT, BOOL, TEXT, NONE, ANY, MODULE,
    ATTRIBUTES, Signature, Overloads, Binding, assignable,
    from_syntax, unify, needs_dynamic_guard,
)

NOT_CONST = object()
NUMERIC = (INT, FLOAT)
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


@dataclass
class Symbol:
    type: Type
    foreign: str | None = None
    signature: Binding | None = None
    constant: Any = NOT_CONST


class Compiler:
    def __init__(self):
        self.symbols: dict[str, Symbol] = {}
        self.diagnostics: list[Diagnostic] = []
        self.assumptions: list[str] = []
        self.registry = ForeignCatalog()
        self.registry.add_net_registry(net_bindings())
        self.used_foreign: set[str] = set()

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

    def infer(self, ex: Expr, scope: dict[str, Symbol] | None = None) -> Value:
        symbols = self.symbols if scope is None else scope
        kind, p = ex.kind, ex.parts
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
            const = [i.constant for i in items] if all(i.constant is not NOT_CONST for i in items) else NOT_CONST
            return self.val(Type("List", (element_type,)), "list", *(v.node for v in items), constant=const)
        if kind == "dict":
            flattened: list[ExprIR] = []
            value_type = None
            for key_expr, value_expr in p:
                key, val = self.infer(key_expr, symbols), self.infer(value_expr, symbols)
                self._check_type(key, TEXT, "dictionary key")
                flattened.extend((key.node, val.node))
                if value_type is None:
                    value_type = val.type
                else:
                    merged = unify(value_type, val.type)
                    if merged == ANY and value_type != ANY and val.type != ANY:
                        raise BError("E_TYPE", f"Dictionary values disagree: {value_type} versus {val.type}")
                    value_type = merged
            return self.val(Type("Dict", (TEXT, value_type or ANY)), "dict", *flattened)
        if kind == "attr":
            base, name = p
            bv = self.infer(base, symbols)
            if bv.type not in (MODULE, ANY):
                raise BError("E_TYPE", f"Cannot access attribute {name} on {bv.type}")
            path = self._foreign_path(ex, symbols)
            if path in ATTRIBUTES:
                ref = self.val(ATTRIBUTES[path], "attr", bv.node, data=name, foreign=path)
                ref.node = self.guard(ref.node, ATTRIBUTES[path])
                return ref
            if path and self.registry.lookup(path):
                return self.val(Type("Function"), "attr", bv.node, data=name, foreign=path)
            if path and path.startswith("net:"):
                raise BError("E_FOREIGN", f"Unregistered .NET symbol {path}")
            if path and path.startswith("py:"):
                self.warn("W_UNCHECKED_FOREIGN", f"Unspecified Python symbol {path}; no static signature available")
            return self.val(ANY, "attr", bv.node, data=name, foreign=path)
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
                children = [tv.node] + [self.guard(v.node, t) if path else v.node
                                       for v, t in zip(values, sig.params)]
                if ref is not None:
                    self.used_foreign.add(ref.path)
                    if ref.provenance not in ("curated-builtin", "verified-host-snapshot", "user-declaration"):
                        assumed = f"{ref.path} ({ref.provenance}): signature assumed, not behavior proved"
                        if assumed not in self.assumptions:
                            self.assumptions.append(assumed)
                result = self.val(sig.result, "call", *children, foreign=path)
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
            elif not (lhs.type in NUMERIC + (ANY,) and rhs.type in NUMERIC + (ANY,)):
                raise BError("E_TYPE", f"{kind} requires numbers, got {lhs.type} and {rhs.type}")
            if kind in ("div", "mod") and rhs.constant == 0:
                raise BError("E_DIV_ZERO", "Division by zero is guaranteed")
            return self.val(typ, kind, lhs.node, rhs.node,
                            constant=self._const_op(OPS[kind], lhs.constant, rhs.constant))
        if kind == "cmp":
            lhs, op, rhs = p
            lv, rv = self.infer(lhs, symbols), self.infer(rhs, symbols)
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

    def statement(self, stmt: Stmt) -> StmtIR:
        kind, p = stmt.kind, stmt.parts
        if kind == "foreign":
            path, params, result = p
            parts = path.split(".")
            if len(parts) < 2:
                raise BError("E_FOREIGN", "Foreign declaration requires an imported alias and a member")
            sym = self.symbols.get(parts[0])
            if not sym or sym.type != MODULE or not sym.foreign:
                raise BError("E_FOREIGN", f"{parts[0]} must be an imported foreign module")
            fullname = sym.foreign + "." + ".".join(parts[1:])
            if self.registry.lookup(fullname):
                raise BError("E_FOREIGN", f"A binding already exists for {fullname}")
            if fullname.startswith("net:"):
                raise BError("E_FOREIGN", "Custom .NET declarations require a host adapter; only registered .NET bindings work")
            sig = Signature(tuple(from_syntax(t) for t in params), from_syntax(result))
            if any(t in (NONE, MODULE) for t in (*sig.params, sig.result)):
                raise BError("E_TYPE", "Foreign signatures cannot use internal None or Module types")
            self.registry.add(fullname, sig, "user-declaration")
            self.assumptions.append(f"{fullname}({', '.join(map(str, sig.params))}) -> {sig.result}")
            return StmtIR("foreign", target=fullname)
        if kind == "use":
            backend, path, alias = p
            if backend == "py":
                try:
                    found = importlib.util.find_spec(path)
                except (ImportError, ValueError, ModuleNotFoundError):
                    found = None
                if found is None:
                    raise BError("E_IMPORT", f"Python module {path} is not installed")
                self.registry.add_python_module(path, inspect_python(path))
            elif backend == "net":
                if not any(k.startswith(f"net:{path}.") for k in self.registry.symbols):
                    raise BError("E_IMPORT", f"No registered .NET metadata for {path}")
            else:
                raise BError("E_IMPORT", f"Unknown backend {backend}")
            self._new(alias, Symbol(MODULE, foreign=f"{backend}:{path}"))
            return StmtIR("import", name=alias, backend=backend, target=path)
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
            self._new(name, Symbol(wanted, constant=value.constant))
            node = self.guard(value.node, wanted) if annotation is not None else value.node
            return StmtIR("let", name=name, typ=wanted, expr=node)
        if kind == "fn":
            name, parameters, result_annotation, expr = p
            names = [name for name, _ in parameters]
            if len(names) != len(set(names)):
                raise BError("E_NAME", f"Duplicate parameter in {name}")
            if any(n in self.symbols or n.startswith("_b_") for n in names):
                raise BError("E_NAME", "Parameters cannot shadow existing names or runtime internals")
            types = [from_syntax(t) for _, t in parameters]
            result_type = from_syntax(result_annotation)
            self._new(name, Symbol(Type("Function"), signature=Signature(tuple(types), result_type)))
            local = {**self.symbols, **{n: Symbol(t) for n, t in zip(names, types)}}
            body = self.infer(expr, local)
            self._check_type(body, result_type, f"return of {name}")
            return StmtIR("fn", name=name, typ=result_type, expr=self.guard(body.node, result_type),
                          params=tuple(zip(names, types)))
        if kind == "print":
            return StmtIR("print", expr=self.infer(p[0]).node)
        if kind == "assert":
            value = self.infer(p[0])
            self._check_type(value, BOOL, "assert")
            if value.constant is False:
                raise BError("E_ASSERT", "Assertion is statically false")
            if value.constant is NOT_CONST:
                self.warn("W_RUNTIME_ASSERT", "Assertion can only be checked while executing")
            return StmtIR("assert", expr=value.node)
        raise BError("E_INTERNAL", f"Unrecognized statement {kind}")

    def compile(self, source: str) -> Compiled:
        try:
            parsed = parse(source)
        except LarkError as exc:
            raise BError("E_SYNTAX", str(exc)) from exc
        statements = tuple(self.statement(s) for s in parsed)
        program = ProgramIR(statements, self.registry.export(self.used_foreign), tuple(self.assumptions))
        optimized = optimize(program)
        python_module = PythonLowerer().lower(optimized.program)
        return Compiled(ast.unparse(python_module) + "\n", compile(python_module, "<B>", "exec"),
                        self.diagnostics, self.assumptions, program, optimized.program, optimized.folds)


def compile_b(source: str, strict: bool = False) -> Compiled:
    result = Compiler().compile(source)
    if strict and result.diagnostics:
        raise BError("E_STRICT", "Unresolved checks: " + "; ".join(d.code for d in result.diagnostics))
    return result
