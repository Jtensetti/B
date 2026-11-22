"""Lower checked BIR to Python AST, preserving B language operations.

This is the first executable backend. BIR is independent of the choice of
backend; a native/LLVM/WASM backend can be implemented against the same nodes
once its semantics and supported operations are specified.
"""
from __future__ import annotations
import ast
import keyword
from contextlib import contextmanager

from .ir import ExprIR, ProgramIR, StmtIR
from .types import BOOL, FLOAT, INT, NONE, TEXT, BError


_BINARY = {
    "add": ast.Add, "sub": ast.Sub, "mul": ast.Mult, "div": ast.Div, "mod": ast.Mod,
}
_COMPARISONS = {
    "==": ast.Eq, "!=": ast.NotEq, "<": ast.Lt, ">": ast.Gt,
    "<=": ast.LtE, ">=": ast.GtE,
}
_SCALAR_OPS = {"literal", "name", "cmp", "and", "or", "not", "neg", "conditional", *_BINARY}


def _inert_scalar(e: ExprIR) -> bool:
    """Exact scalar operations cannot call out and change the list during its traversal."""
    return (e.typ in (BOOL, FLOAT, INT, NONE, TEXT) and e.op in _SCALAR_OPS
            and all(_inert_scalar(child) for child in e.operands))


def _python_name(name: str) -> str:
    # The B grammar permits Python keywords. B reserves _b_ for the backend.
    if keyword.iskeyword(name) or name in ("__debug__", "__builtins__"):
        return "_b_name_" + name
    return name


def _load(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Load())


def _assign(name: str, value: ast.expr) -> ast.Assign:
    return ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())], value=value)


class PythonLowerer:
    def __init__(self):
        self._tmp = 0
        self._helpers: list[ast.FunctionDef] = []
        self._locals: set[str] = set()

    @contextmanager
    def _bind(self, names):
        surrounding = self._locals
        self._locals = surrounding.union(names)
        try:
            yield
        finally:
            self._locals = surrounding

    def _summarize(self, e: ExprIR) -> ast.Call:
        # Keep the traversal in its own helper so the call remains an expression
        # even inside a lazy branch. It receives the source and any captured locals.
        source = self.expr(e.operands[0])
        binder = _python_name(e.data["binder"])
        body: list[ast.stmt] = []
        if not all(_inert_scalar(child) for child in e.operands[1:]):
            # An opaque call can reach the same list via another name. Freeze its
            # membership before the first field, while retaining the items' identities.
            body.append(_assign("_b_source", ast.Subscript(value=_load("_b_source"), slice=ast.Slice(),
                                                          ctx=ast.Load())))
        loop_body: list[ast.stmt] = []
        keys: list[ast.expr] = []
        values: list[ast.expr] = []
        needs_size = False
        with self._bind([binder]):
            for i, (label, op, value_idx, guard_idx, default) in enumerate(e.data["fields"]):
                acc = f"_b_acc_{i}"
                keys.append(ast.Constant(label))
                if op == "count" and guard_idx is None:
                    needs_size = True
                    values.append(_load("_b_size"))
                    continue
                if op in ("count", "sum"):
                    body.append(_assign(acc, ast.Constant(0)))
                    term = ast.Constant(1) if op == "count" else self.expr(e.operands[value_idx])
                    update = [ast.AugAssign(target=ast.Name(id=acc, ctx=ast.Store()), op=ast.Add(), value=term)]
                    values.append(_load(acc))
                elif op in ("min", "max"):
                    body.append(_assign(acc, ast.Constant(None)))
                    empty = ast.Compare(left=_load(acc), ops=[ast.Is()], comparators=[ast.Constant(None)])
                    projection = self.expr(e.operands[value_idx])
                    if isinstance(projection, ast.Name) and projection.id == binder:
                        candidate = binder
                        update = []
                    else:
                        candidate = "_b_candidate"
                        update = [_assign(candidate, projection)]
                    comparison = ast.Compare(left=_load(candidate), ops=[ast.Lt() if op == "min" else ast.Gt()],
                                             comparators=[_load(acc)])
                    update.append(ast.If(test=ast.BoolOp(op=ast.Or(), values=[empty, comparison]),
                                         body=[_assign(acc, _load(candidate))], orelse=[]))
                    values.append(ast.IfExp(test=empty, body=ast.Constant(default), orelse=_load(acc)))
                else:
                    raise BError("E_INTERNAL", f"Unknown summary reducer: {op}")
                if guard_idx is None:
                    loop_body.extend(update)
                else:
                    loop_body.append(ast.If(test=self.expr(e.operands[guard_idx]), body=update, orelse=[]))
        if needs_size:
            body.append(_assign("_b_size", ast.Call(func=_load("_b_len"), args=[_load("_b_source")], keywords=[])))
        if loop_body:
            body.append(ast.For(target=ast.Name(id=binder, ctx=ast.Store()), iter=_load("_b_source"),
                                body=loop_body, orelse=[]))
        body.append(ast.Return(value=ast.Dict(keys=keys, values=values)))
        # A nested helper call already exposes its captures as ordinary loads.
        # Global names stay global, preserving B's usual point of lookup.
        reads = {n.id for stmt in loop_body for n in ast.walk(stmt)
                 if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        captures = sorted(self._locals.intersection(reads) - {binder})
        helper_name = f"_b_summary_{len(self._helpers)}"
        args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in ["_b_source", *captures]],
                             vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
        self._helpers.append(ast.FunctionDef(name=helper_name, args=args, body=body,
            decorator_list=[], returns=None, type_comment=None))
        return ast.Call(func=_load(helper_name), args=[source, *map(_load, captures)], keywords=[])

    def expr(self, e: ExprIR) -> ast.expr:
        op, children, data = e.op, e.operands, e.data
        if op == "literal":
            return ast.Constant(data)
        if op == "name":
            return ast.Name(id=_python_name(data), ctx=ast.Load())
        if op == "list":
            return ast.List(elts=[self.expr(x) for x in children], ctx=ast.Load())
        if op == "dict":
            if len(children) % 2:
                raise BError("E_INTERNAL", "Odd number of dictionary children in BIR")
            return ast.Dict(keys=[self.expr(x) for x in children[::2]], values=[self.expr(x) for x in children[1::2]])
        if op == "summarize":
            return self._summarize(e)
        if op == "lookup":
            dictionary, key = children
            get = ast.Attribute(value=self.expr(dictionary), attr="get", ctx=ast.Load())
            return ast.Call(func=get, args=[self.expr(key)], keywords=[])
        if op == "attr":
            if keyword.iskeyword(data):
                return ast.Call(func=ast.Name(id="_b_getattr", ctx=ast.Load()),
                                args=[self.expr(children[0]), ast.Constant(data)], keywords=[])
            return ast.Attribute(value=self.expr(children[0]), attr=data, ctx=ast.Load())
        if op == "call":
            return ast.Call(func=self.expr(children[0]), args=[self.expr(x) for x in children[1:]], keywords=[])
        if op == "guard":
            return ast.Call(func=ast.Name(id="_b_guard", ctx=ast.Load()),
                            args=[self.expr(children[0]), ast.Constant(str(e.typ))], keywords=[])
        if op == "conditional":
            return ast.IfExp(test=self.expr(children[0]), body=self.expr(children[1]), orelse=self.expr(children[2]))
        if op == "coalesce":
            # NamedExpr ensures that potentially impure foreign calls are evaluated ONCE.
            self._tmp += 1
            temp = f"_b_coalesce_{self._tmp}"
            test = ast.Compare(left=ast.NamedExpr(
                target=ast.Name(id=temp, ctx=ast.Store()), value=self.expr(children[0])),
                ops=[ast.IsNot()], comparators=[ast.Constant(None)])
            return ast.IfExp(test=test, body=ast.Name(id=temp, ctx=ast.Load()), orelse=self.expr(children[1]))
        if op in _BINARY:
            return ast.BinOp(left=self.expr(children[0]), op=_BINARY[op](), right=self.expr(children[1]))
        if op == "cmp":
            return ast.Compare(left=self.expr(children[0]), ops=[_COMPARISONS[data]()],
                               comparators=[self.expr(children[1])])
        if op in ("and", "or"):
            return ast.BoolOp(op=ast.And() if op == "and" else ast.Or(), values=[self.expr(x) for x in children])
        if op in ("not", "neg"):
            return ast.UnaryOp(op=ast.Not() if op == "not" else ast.USub(), operand=self.expr(children[0]))
        raise BError("E_INTERNAL", f"Unknown typed BIR operation: {op}")

    def statement(self, s: StmtIR) -> ast.stmt:
        if s.op == "import":
            if s.backend not in ("py", "net", "js") or not s.target or not s.name:
                raise BError("E_INTERNAL", "Invalid import BIR")
            adapter = {"py": "_b_py", "net": "_b_net", "js": "_b_js_module"}[s.backend]
            return ast.Assign(targets=[ast.Name(id=_python_name(s.name), ctx=ast.Store())], value=ast.Call(
                func=ast.Name(id=adapter, ctx=ast.Load()),
                args=[ast.Constant(s.target)], keywords=[]))
        if s.op in ("foreign", "permit"):
            return ast.Pass()
        if s.op == "let":
            return ast.Assign(targets=[ast.Name(id=_python_name(s.name), ctx=ast.Store())], value=self.expr(s.expr))
        if s.op == "fn":
            names = [_python_name(n) for n, _ in s.params]
            args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in names],
                                 vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
            body: list[ast.stmt] = []
            # B arguments are B values even if invoked from Python or via Any.
            for name, typ in s.params:
                name = _python_name(name)
                body.append(ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())],
                                       value=ast.Call(func=ast.Name(id="_b_guard", ctx=ast.Load()),
                                                      args=[ast.Name(id=name, ctx=ast.Load()), ast.Constant(str(typ))],
                                                      keywords=[])))
            if s.requires is not None:
                with self._bind(names):
                    precondition = self.expr(s.requires)
                body.append(ast.If(test=ast.UnaryOp(op=ast.Not(), operand=precondition),
                    body=[ast.Raise(exc=ast.Call(func=ast.Name(id="_b_contract_error", ctx=ast.Load()),
                                  args=[ast.Constant(f"Precondition of {s.name} failed")], keywords=[]),
                                    cause=None)], orelse=[]))
            with self._bind(names):
                body.append(_assign("_b_result", self.expr(s.expr)))
            if s.ensures is not None:
                # `result` is an expression-scope pseudo-variable, not a mutable B binding.
                with self._bind([*names, "result"]):
                    condition = self.expr(s.ensures)
                class ReplaceResult(ast.NodeTransformer):
                    def visit_Name(self, node):
                        if node.id == "result":
                            return ast.copy_location(ast.Name(id="_b_result", ctx=ast.Load()), node)
                        return node
                condition = ReplaceResult().visit(condition)
                body.append(ast.If(test=ast.UnaryOp(op=ast.Not(), operand=condition),
                    body=[ast.Raise(exc=ast.Call(func=ast.Name(id="_b_contract_error", ctx=ast.Load()),
                                  args=[ast.Constant(f"Postcondition of {s.name} failed")], keywords=[]),
                                    cause=None)], orelse=[]))
            body.append(ast.Return(value=ast.Name(id="_b_result", ctx=ast.Load())))
            return ast.FunctionDef(name=_python_name(s.name), args=args, body=body,
                                   decorator_list=[], returns=None, type_comment=None)
        if s.op == "print":
            return ast.Expr(value=ast.Call(func=ast.Name(id="_b_print", ctx=ast.Load()),
                                           args=[self.expr(s.expr)], keywords=[]))
        if s.op == "assert":
            return ast.If(test=ast.UnaryOp(op=ast.Not(), operand=self.expr(s.expr)),
                body=[ast.Raise(exc=ast.Call(func=ast.Name(id="_b_assertion_error", ctx=ast.Load()),
                      args=[ast.Constant("B assertion failed")], keywords=[]), cause=None)], orelse=[])
        raise BError("E_INTERNAL", f"Unknown BIR statement: {s.op}")

    def lower(self, program: ProgramIR) -> ast.Module:
        self._helpers.clear()
        builtins = ast.ImportFrom(module="builtins", names=[
            ast.alias(name="print", asname="_b_print"),
            ast.alias(name="getattr", asname="_b_getattr"),
            ast.alias(name="len", asname="_b_len"),
        ], level=0)
        body = [builtins, ast.ImportFrom(module="b_lang.runtime", names=[
            ast.alias(name="py_module", asname="_b_py"),
            ast.alias(name="net_module", asname="_b_net"),
            ast.alias(name="guard", asname="_b_guard"),
            ast.alias(name="BAssertionError", asname="_b_assertion_error"),
            ast.alias(name="BContractError", asname="_b_contract_error"),
        ], level=0)]
        if any(s.op == "import" and s.backend == "js" for s in program.statements):
            signatures = []
            for symbol in program.foreign_symbols:
                if symbol.backend == "js":
                    target, member = symbol.path[3:].rsplit(".", 1)
                    signature = symbol.binding
                    signatures.append((target, member, tuple(map(str, signature.params)), str(signature.result)))
            body.append(ast.Assign(targets=[ast.Name(id="_b_js_signatures", ctx=ast.Store())],
                                   value=ast.Constant(tuple(signatures))))
            setup = ast.parse(
                "from b_lang.jsruntime import NodeSession as _b_NodeSession\n"
                "_b_js_session = _b_NodeSession(globals().get('__file__'), _b_js_signatures)\n"
                "_b_js_module = _b_js_session.module"
            ).body
            body.extend(setup)
        statements = [self.statement(s) for s in program.statements]
        body.extend(self._helpers)
        body.extend(statements)
        return ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
