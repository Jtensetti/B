"""Lower checked BIR to Python AST, preserving B language operations.

This is the first executable backend. BIR is independent of the choice of
backend; a native/LLVM/WASM backend can be implemented against the same nodes
once its semantics and supported operations are specified.
"""
from __future__ import annotations
import ast

from .ir import ExprIR, ProgramIR, StmtIR
from .types import BError


_BINARY = {
    "add": ast.Add, "sub": ast.Sub, "mul": ast.Mult, "div": ast.Div, "mod": ast.Mod,
}
_COMPARISONS = {
    "==": ast.Eq, "!=": ast.NotEq, "<": ast.Lt, ">": ast.Gt,
    "<=": ast.LtE, ">=": ast.GtE,
}


class PythonLowerer:
    def __init__(self):
        self._tmp = 0

    def expr(self, e: ExprIR) -> ast.expr:
        op, children, data = e.op, e.operands, e.data
        if op == "literal":
            return ast.Constant(data)
        if op == "name":
            return ast.Name(id=data, ctx=ast.Load())
        if op == "list":
            return ast.List(elts=[self.expr(x) for x in children], ctx=ast.Load())
        if op == "dict":
            if len(children) % 2:
                raise BError("E_INTERNAL", "Odd number of dictionary children in BIR")
            return ast.Dict(keys=[self.expr(x) for x in children[::2]], values=[self.expr(x) for x in children[1::2]])
        if op == "attr":
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
            if s.backend not in ("py", "net") or not s.target or not s.name:
                raise BError("E_INTERNAL", "Invalid import BIR")
            return ast.Assign(targets=[ast.Name(id=s.name, ctx=ast.Store())], value=ast.Call(
                func=ast.Name(id="_b_py" if s.backend == "py" else "_b_net", ctx=ast.Load()),
                args=[ast.Constant(s.target)], keywords=[]))
        if s.op == "foreign":
            return ast.Pass()
        if s.op == "let":
            return ast.Assign(targets=[ast.Name(id=s.name, ctx=ast.Store())], value=self.expr(s.expr))
        if s.op == "fn":
            names = [n for n, _ in s.params]
            args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in names],
                                 vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
            return ast.FunctionDef(name=s.name, args=args, body=[ast.Return(value=self.expr(s.expr))],
                                   decorator_list=[], returns=None, type_comment=None)
        if s.op == "print":
            return ast.Expr(value=ast.Call(func=ast.Name(id="print", ctx=ast.Load()),
                                           args=[self.expr(s.expr)], keywords=[]))
        if s.op == "assert":
            return ast.If(test=ast.UnaryOp(op=ast.Not(), operand=self.expr(s.expr)),
                body=[ast.Raise(exc=ast.Call(func=ast.Name(id="_b_assertion_error", ctx=ast.Load()),
                      args=[ast.Constant("B assertion failed")], keywords=[]), cause=None)], orelse=[])
        raise BError("E_INTERNAL", f"Unknown BIR statement: {s.op}")

    def lower(self, program: ProgramIR) -> ast.Module:
        body = [ast.ImportFrom(module="b_lang.runtime", names=[
            ast.alias(name="py_module", asname="_b_py"),
            ast.alias(name="net_module", asname="_b_net"),
            ast.alias(name="guard", asname="_b_guard"),
            ast.alias(name="BAssertionError", asname="_b_assertion_error"),
        ], level=0)]
        body.extend(self.statement(s) for s in program.statements)
        return ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
