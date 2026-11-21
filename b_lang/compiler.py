"""B checker and compiler to Python AST. Foreign code is never considered proven."""
from __future__ import annotations
import ast
import importlib.util
import operator
from dataclasses import dataclass
from typing import Any
from lark.exceptions import LarkError
from .model import Expr, Stmt, parse
from .discovery import inspect_python
from .netmeta import net_bindings
from .types import (
    Type, BError, INT, FLOAT, BOOL, TEXT, NONE, ANY, MODULE,
    BINDINGS, ATTRIBUTES, Signature, assignable, from_syntax, unify, needs_dynamic_guard,
)

NOT_CONST = object()
NUMERIC = (INT, FLOAT)

@dataclass
class Value:
    type: Type
    node: ast.expr
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

@dataclass
class Symbol:
    type: Type
    foreign: str | None = None
    signature: Signature | None = None
    constant: Any = NOT_CONST

OPS = {
    "add": (ast.Add, operator.add), "sub": (ast.Sub, operator.sub),
    "mul": (ast.Mult, operator.mul), "div": (ast.Div, operator.truediv),
    "mod": (ast.Mod, operator.mod),
}
CMP = {
    "==": (ast.Eq, operator.eq), "!=": (ast.NotEq, operator.ne),
    "<": (ast.Lt, operator.lt), ">": (ast.Gt, operator.gt),
    "<=": (ast.LtE, operator.le), ">=": (ast.GtE, operator.ge),
}

class Compiler:
    def __init__(self):
        self.symbols: dict[str, Symbol] = {}
        self.diagnostics: list[Diagnostic] = []
        self.foreign_bindings: dict[str, Signature] = {}
        self.assumptions: list[str] = []
        self.discovered: dict[str, Signature] = {}
        self.discovery_sources: dict[str, str] = {}
        self.net_registry = net_bindings()

    def warn(self, code: str, message: str):
        entry = Diagnostic("warning", code, message)
        if entry not in self.diagnostics: self.diagnostics.append(entry)

    def _check_type(self, value: Value, expected: Type, context: str):
        if not assignable(value.type, expected):
            raise BError("E_TYPE", f"{context}: expected {expected}, got {value.type}")
        if needs_dynamic_guard(value.type, expected):
            self.warn("W_DYNAMIC_TYPE", f"{context} comes from an untyped boundary; checked at runtime")
            value.node = self._guard(value.node, expected)

    def _new(self, name: str, symbol: Symbol):
        if name.startswith("_b_"):
            raise BError("E_NAME", "Names starting _b_ are reserved for the B runtime")
        if name in self.symbols: raise BError("E_NAME", f"Redefinition of {name}")
        self.symbols[name] = symbol

    def _const_op(self, fn, *args):
        if any(x is NOT_CONST for x in args): return NOT_CONST
        try: return fn(*args)
        except ZeroDivisionError: raise BError("E_DIV_ZERO", "Division by zero is guaranteed")
        except (ValueError, TypeError, OverflowError): return NOT_CONST

    def infer(self, ex: Expr, scope: dict[str, Symbol] | None = None) -> Value:
        symbols = self.symbols if scope is None else scope
        kind, p = ex.kind, ex.parts
        if kind == "conditional":
            cond, yes, no = p
            cv = self.infer(cond, symbols)
            self._check_type(cv, BOOL, "if condition")
            yv, nv = self.infer(yes, symbols), self.infer(no, symbols)
            typ = unify(yv.type, nv.type)
            if typ == ANY and yv.type != ANY and nv.type != ANY:
                raise BError("E_TYPE", f"if branches have incompatible types: {yv.type} versus {nv.type}")
            if needs_dynamic_guard(yv.type, typ):
                self._check_type(yv, typ, "if then branch")
            if needs_dynamic_guard(nv.type, typ):
                self._check_type(nv, typ, "if else branch")
            constant = NOT_CONST
            if type(cv.constant) is bool:
                constant = yv.constant if cv.constant else nv.constant
            return Value(typ, ast.IfExp(test=cv.node, body=yv.node, orelse=nv.node), constant)
        if kind == "literal":
            v = p[0]
            t = BOOL if type(v) is bool else INT if type(v) is int else FLOAT if type(v) is float else TEXT if type(v) is str else NONE
            return Value(t, ast.Constant(v), v)
        if kind == "name":
            name = p[0]
            if name not in symbols: raise BError("E_NAME", f"Unknown name {name}")
            sym = symbols[name]
            return Value(sym.type, ast.Name(id=name, ctx=ast.Load()), sym.constant)
        if kind == "list":
            items = [self.infer(i, symbols) for i in p]
            element_type = ANY
            if items:
                element_type = items[0].type
                for i in items[1:]: element_type = unify(element_type, i.type)
            const = [i.constant for i in items] if all(i.constant is not NOT_CONST for i in items) else NOT_CONST
            return Value(Type("List", (element_type,)), ast.List(elts=[i.node for i in items], ctx=ast.Load()), const)
        if kind == "attr":
            base, attr = p
            bv = self.infer(base, symbols)
            if bv.type != MODULE and bv.type != ANY:
                raise BError("E_TYPE", f"Cannot access attribute {attr} on {bv.type}")
            node = ast.Attribute(value=bv.node, attr=attr, ctx=ast.Load())
            path = self._foreign_path(ex, symbols)
            if path in ATTRIBUTES: return Value(ATTRIBUTES[path], self._guard(node, ATTRIBUTES[path]))
            if path in BINDINGS or path in self.foreign_bindings or path in self.discovered or path in self.net_registry: return Value(Type("Function"), node)
            if path and path.startswith("net:"):
                raise BError("E_FOREIGN", f"Unregistered .NET symbol {path}")
            if path and path.startswith("py:"):
                self.warn("W_UNCHECKED_FOREIGN", f"Unspecified Python symbol {path}; no static signature available")
            return Value(ANY, node)
        if kind == "invoke":
            target, raw_args = p
            tv = self.infer(target, symbols)
            values = [self.infer(a, symbols) for a in raw_args]
            path = self._foreign_path(target, symbols)
            sig = (self.foreign_bindings.get(path) or self.discovered.get(path) or self.net_registry.get(path) or BINDINGS.get(path)) if path else None
            if sig is None and target.kind == "name":
                sig = symbols[target.parts[0]].signature
            if sig:
                if not (sig.required <= len(values) <= len(sig.params)):
                    wanted = str(sig.required) if sig.required == len(sig.params) else f"{sig.required}–{len(sig.params)}"
                    raise BError("E_ARITY", f"{path or target.parts[0]} expects {wanted} arguments, got {len(values)}")
                for n, (value, expected) in enumerate(zip(values, sig.params), start=1):
                    self._check_type(value, expected, f"argument {n} to {path or target.parts[0]}")
                # Guard even statically typed calls at a foreign boundary: the imported
                # function has never been verified and may return an unexpected value.
                guarded_args = [self._guard(v.node, t) if path else v.node
                                for v, t in zip(values, sig.params)]
                if path in self.discovery_sources:
                    assumption = f"{path} ({self.discovery_sources[path]}): signature assumed, not behavior proved"
                    if assumption not in self.assumptions: self.assumptions.append(assumption)
                call = ast.Call(func=tv.node, args=guarded_args, keywords=[])
                return Value(sig.result, self._guard(call, sig.result) if path else call)
            if path and path.startswith("net:"):
                raise BError("E_FOREIGN", f"Unregistered .NET call {path}")
            if tv.type != ANY:
                raise BError("E_TYPE", f"Cannot call value of type {tv.type}")
            if not (path and path.startswith("py:")):
                self.warn("W_UNCHECKED_FOREIGN", f"Unspecified call {path or '<computed>'}; no static signature available")
            return Value(ANY, ast.Call(func=tv.node, args=[v.node for v in values], keywords=[]))
        if kind in OPS:
            lhs, rhs = self.infer(p[0], symbols), self.infer(p[1], symbols)
            typ = FLOAT if kind == "div" else unify(lhs.type, rhs.type)
            if kind == "add" and lhs.type == rhs.type == TEXT: typ = TEXT
            elif kind == "add" and lhs.type.name == rhs.type.name == "List": typ = unify(lhs.type, rhs.type)
            elif not (lhs.type in NUMERIC + (ANY,) and rhs.type in NUMERIC + (ANY,)):
                raise BError("E_TYPE", f"{kind} requires numbers, got {lhs.type} and {rhs.type}")
            if kind in ("div", "mod") and rhs.constant == 0:
                raise BError("E_DIV_ZERO", "Division by zero is guaranteed")
            return Value(typ, ast.BinOp(left=lhs.node, op=OPS[kind][0](), right=rhs.node), self._const_op(OPS[kind][1], lhs.constant, rhs.constant))
        if kind == "cmp":
            lhs, op, rhs = p
            lv, rv = self.infer(lhs, symbols), self.infer(rhs, symbols)
            if lv.type != ANY and rv.type != ANY and not (assignable(lv.type, rv.type) or assignable(rv.type, lv.type)):
                raise BError("E_TYPE", f"Cannot compare {lv.type} and {rv.type}")
            return Value(BOOL, ast.Compare(left=lv.node, ops=[CMP[op][0]()], comparators=[rv.node]), self._const_op(CMP[op][1], lv.constant, rv.constant))
        if kind in ("and", "or"):
            lv, rv = self.infer(p[0], symbols), self.infer(p[1], symbols)
            self._check_type(lv, BOOL, kind); self._check_type(rv, BOOL, kind)
            fn = (lambda a,b: a and b) if kind == "and" else (lambda a,b: a or b)
            return Value(BOOL, ast.BoolOp(op=ast.And() if kind == "and" else ast.Or(), values=[lv.node, rv.node]), self._const_op(fn, lv.constant, rv.constant))
        if kind in ("not", "neg"):
            val = self.infer(p[0], symbols)
            expected = BOOL if kind == "not" else FLOAT
            if kind == "neg" and val.type == INT: expected = INT
            self._check_type(val, expected, kind)
            return Value(BOOL if kind == "not" else val.type, ast.UnaryOp(op=ast.Not() if kind == "not" else ast.USub(), operand=val.node), self._const_op(operator.not_ if kind == "not" else operator.neg, val.constant))
        raise BError("E_INTERNAL", f"Unrecognized expression {kind}")

    def _foreign_path(self, ex: Expr, scope: dict[str, Symbol]) -> str | None:
        if ex.kind == "name": return scope[ex.parts[0]].foreign
        if ex.kind == "attr":
            base = self._foreign_path(ex.parts[0], scope)
            return f"{base}.{ex.parts[1]}" if base else None
        return None

    @staticmethod
    def _guard(node: ast.expr, typ: Type) -> ast.expr:
        return ast.Call(func=ast.Name(id="_b_guard", ctx=ast.Load()), args=[node, ast.Constant(str(typ))], keywords=[])

    def statement(self, s: Stmt) -> ast.stmt:
        kind, p = s.kind, s.parts
        if kind == "foreign":
            path, params, result = p
            parts = path.split(".")
            if len(parts) < 2:
                raise BError("E_FOREIGN", "Foreign declaration requires an imported alias and a member")
            alias = parts[0]
            sym = self.symbols.get(alias)
            if not sym or sym.type != MODULE or not sym.foreign:
                raise BError("E_FOREIGN", f"{alias} must be an imported foreign module")
            fullname = sym.foreign + "." + ".".join(parts[1:])
            if fullname in self.foreign_bindings or fullname in BINDINGS or fullname in self.discovered or fullname in self.net_registry:
                raise BError("E_FOREIGN", f"A binding already exists for {fullname}")
            if fullname.startswith("net:"):
                # Only explicit host allowlist methods can be called; a declaration
                # must not override the host's security boundary.
                raise BError("E_FOREIGN", "Custom .NET declarations require a host adapter; only built-in .NET bindings work")
            sig = Signature(tuple(from_syntax(t) for t in params), from_syntax(result))
            if any(t in (NONE, MODULE) for t in (*sig.params, sig.result)):
                raise BError("E_TYPE", "Foreign signatures cannot use internal None or Module types")
            self.foreign_bindings[fullname] = sig
            self.assumptions.append(f"{fullname}({', '.join(map(str, sig.params))}) -> {sig.result}")
            return ast.Pass()
        if kind == "use":
            backend, path, alias = p
            if backend == "py":
                try: found = importlib.util.find_spec(path)
                except (ImportError, ValueError, ModuleNotFoundError): found = None
                if found is None: raise BError("E_IMPORT", f"Python module {path} is not installed")
                discovered = inspect_python(path)
                for name, sig in discovered.signatures.items():
                    full = f"py:{path}.{name}"
                    if full not in BINDINGS:
                        self.discovered[full] = sig
                        self.discovery_sources[full] = discovered.source_kind
            elif backend == "net":
                if not any(k.startswith(f"net:{path}.") for k in self.net_registry):
                    raise BError("E_IMPORT", f"No registered .NET metadata for {path}")
            else: raise BError("E_IMPORT", f"Unknown backend {backend}")
            self._new(alias, Symbol(MODULE, foreign=f"{backend}:{path}"))
            return ast.Assign(targets=[ast.Name(id=alias, ctx=ast.Store())], value=ast.Call(
                func=ast.Name(id="_b_py" if backend == "py" else "_b_net", ctx=ast.Load()),
                args=[ast.Constant(path)], keywords=[]))
        if kind == "let":
            name, annotation, expr = p
            value = self.infer(expr)
            wanted = from_syntax(annotation) if annotation is not None else value.type
            if wanted == NONE: raise BError("E_TYPE", "A variable cannot be annotated None")
            self._check_type(value, wanted, f"assignment to {name}")
            if wanted.name == "List" and expr.kind == "list":
                for element in expr.parts:
                    self._check_type(self.infer(element), wanted.args[0], f"element of {name}")
            self._new(name, Symbol(wanted, constant=value.constant))
            node = self._guard(value.node, wanted) if annotation is not None else value.node
            return ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())], value=node)
        if kind == "fn":
            name, parameters, result_annotation, expr = p
            param_names = [name for name, _ in parameters]
            if len(param_names) != len(set(param_names)): raise BError("E_NAME", f"Duplicate parameter in {name}")
            if any(n in self.symbols or n.startswith("_b_") for n in param_names):
                raise BError("E_NAME", "Parameters cannot shadow existing names or runtime internals in v0.1")
            types = [from_syntax(t) for _, t in parameters]
            result_type = from_syntax(result_annotation)
            sig = Signature(tuple(types), result_type)
            self._new(name, Symbol(Type("Function"), signature=sig))
            local = {**self.symbols, **{n: Symbol(t) for n,t in zip(param_names, types)}}
            body = self.infer(expr, local)
            self._check_type(body, result_type, f"return of {name}")
            pyargs = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in param_names],
                vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
            return ast.FunctionDef(name=name, args=pyargs,
                body=[ast.Return(value=self._guard(body.node, result_type))],
                decorator_list=[], returns=None, type_comment=None)
        if kind == "print": return ast.Expr(value=ast.Call(func=ast.Name(id="print", ctx=ast.Load()), args=[self.infer(p[0]).node], keywords=[]))
        if kind == "assert":
            value = self.infer(p[0]); self._check_type(value, BOOL, "assert")
            if value.constant is False: raise BError("E_ASSERT", "Assertion is statically false")
            if value.constant is NOT_CONST: self.warn("W_RUNTIME_ASSERT", "Assertion can only be checked while executing")
            return ast.If(test=ast.UnaryOp(op=ast.Not(), operand=value.node),
                body=[ast.Raise(exc=ast.Call(func=ast.Name(id="_b_assertion_error", ctx=ast.Load()),
                    args=[ast.Constant("B assertion failed")], keywords=[]), cause=None)], orelse=[])
        raise BError("E_INTERNAL", f"Unrecognized statement {kind}")

    def compile(self, source: str) -> Compiled:
        try: statements = parse(source)
        except LarkError as ex: raise BError("E_SYNTAX", str(ex)) from ex
        body = [ast.ImportFrom(module="b_lang.runtime", names=[
            ast.alias(name="py_module", asname="_b_py"),
            ast.alias(name="net_module", asname="_b_net"),
            ast.alias(name="guard", asname="_b_guard"),
            ast.alias(name="BAssertionError", asname="_b_assertion_error"),
        ], level=0)]
        for statement in statements: body.append(self.statement(statement))
        module = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
        python_source = ast.unparse(module) + "\n"
        return Compiled(python_source, compile(module, "<B>", "exec"), self.diagnostics, self.assumptions)

def compile_b(source: str, strict: bool = False) -> Compiled:
    result = Compiler().compile(source)
    if strict and result.diagnostics:
        raise BError("E_STRICT", "Unresolved checks: " + "; ".join(d.code for d in result.diagnostics))
    return result
