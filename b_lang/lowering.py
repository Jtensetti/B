"""Lower checked BIR to Python AST, preserving B language operations.

This is the Python executable backend. An independent JavaScript/Node backend
(`lowering_js.py`) lowers the same checked BIR to verify backend independence.
"""
from __future__ import annotations
import ast
import keyword
from contextlib import contextmanager

from .history import order_comparison
from .ir import ExprIR, ProgramIR, StmtIR
from .types import BOOL, FLOAT, INT, NONE, TEXT, BError, is_dim_float


_BINARY = {
    "add": ast.Add, "sub": ast.Sub, "mul": ast.Mult, "div": ast.Div, "mod": ast.Mod,
}
_COMPARISONS = {
    "==": ast.Eq, "!=": ast.NotEq, "<": ast.Lt, ">": ast.Gt,
    "<=": ast.LtE, ">=": ast.GtE,
}
_SCALAR_OPS = {"literal", "name", "cmp", "and", "or", "not", "neg", "conditional", *_BINARY}
_INDEX_MIN_ROWS = 32

_BUILTIN_MAP = {
    "len": "_b_b_len",
    "abs": "_b_b_abs",
    "min": "_b_b_min",
    "max": "_b_b_max",
    "round_even": "_b_b_round_even",
    "round_away": "_b_b_round_away",
    "div_euclid": "_b_b_div_euclid",
    "rem_euclid": "_b_b_rem_euclid",
    "rem_trunc": "_b_b_rem_trunc",
    "scalar": "_b_b_scalar",
    "to_text": "_b_b_to_text",
    "to_float": "_b_b_to_float",
    "to_int": "_b_b_to_int",
    "stdin_text": "_b_b_stdin_text",
    "json_encode": "_b_b_json_encode",
    "str_contains": "_b_b_str_contains",
    "str_starts": "_b_b_str_starts",
    "str_ends": "_b_b_str_ends",
    "str_lower": "_b_b_str_lower",
    "str_upper": "_b_b_str_upper",
    "str_trim": "_b_b_str_trim",
    "str_split": "_b_b_str_split",
    "str_join": "_b_b_str_join",
    "str_replace": "_b_b_str_replace",
}


def _leaves(node: ExprIR, connective: str):
    if node.op == connective:
        for child in node.operands:
            yield from _leaves(child, connective)
    else:
        yield node


def _indexed_facts(test, params):
    if not params or test.op != "or" or any(t not in (BOOL, FLOAT, INT, TEXT) for _, t in params):
        return None
    rows = list(_leaves(test, "or"))
    if len(rows) < _INDEX_MIN_ROWS:
        return None
    keys = []
    for row in rows:
        terms = list(_leaves(row, "and"))
        if len(terms) != len(params):
            return None
        values = []
        for term, (name, typ) in zip(terms, params):
            if term.op != "cmp" or term.data != "==":
                return None
            left, right = term.operands
            if (left.op != "name" or left.data != name or left.typ != typ
                    or right.op != "literal" or right.typ != typ):
                return None
            values.append(right.data)
        keys.append(ast.Constant(values[0] if len(values) == 1 else tuple(values)))
    names = [_load(_python_name(name)) for name, _ in params]
    key = names[0] if len(names) == 1 else ast.Tuple(elts=names, ctx=ast.Load())
    return ast.Compare(left=key, ops=[ast.In()], comparators=[ast.Set(elts=keys)])


def _inert_scalar(e: ExprIR) -> bool:
    return (e.typ in (BOOL, FLOAT, INT, NONE, TEXT) and e.op in _SCALAR_OPS
            and all(_inert_scalar(child) for child in e.operands))


def _python_name(name: str) -> str:
    if keyword.iskeyword(name) or name in ("__debug__", "__builtins__"):
        return "_b_name_" + name
    return name


def _load(name: str) -> ast.Name:
    return ast.Name(id=name, ctx=ast.Load())


def _assign(name: str, value: ast.expr) -> ast.Assign:
    return ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())], value=value)


class _FillNames(ast.NodeTransformer):
    def __init__(self, replacements: dict[str, ast.expr]):
        self.replacements = replacements

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            return self.replacements.get(node.id, node)
        return node


class PythonLowerer:
    def __init__(self):
        self._tmp = 0
        self._helpers: list[ast.FunctionDef] = []
        self._locals: set[str] = set()
        self._used_builtins: set[str] = set()
        self._has_records = False
        self._used_record_with = False
        self._used_from_json = False

    @contextmanager
    def _bind(self, names):
        surrounding = self._locals
        self._locals = surrounding.union(names)
        try:
            yield
        finally:
            self._locals = surrounding

    def _guard_call(self, value_expr: ast.expr, typ_str: str) -> ast.Call:
        args = [value_expr, ast.Constant(typ_str)]
        if self._has_records:
            args.append(_load("_b_records"))
        return ast.Call(func=_load("_b_guard"), args=args, keywords=[])

    def _summarize(self, e: ExprIR) -> ast.Call:
        source = self.expr(e.operands[0])
        binder = _python_name(e.data["binder"])
        body: list[ast.stmt] = []
        if not all(_inert_scalar(child) for child in e.operands[1:]):
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
                    init_zero = 0.0 if (op == "sum" and (e.operands[value_idx].typ == FLOAT or is_dim_float(e.operands[value_idx].typ))) else 0
                    body.append(_assign(acc, ast.Constant(init_zero)))
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
        return self._collection_call("summary", source, body, {binder})

    def _collection_call(self, kind: str, source: ast.expr, body: list[ast.stmt], binders: set[str]) -> ast.Call:
        reads = {n.id for stmt in body for n in ast.walk(stmt)
                 if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        captures = sorted(self._locals.intersection(reads) - binders)
        helper_name = f"_b_{kind}_{len(self._helpers)}"
        args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in ["_b_source", *captures]],
                             vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
        self._helpers.append(ast.FunctionDef(name=helper_name, args=args, body=body,
            decorator_list=[], returns=None, type_comment=None))
        return ast.Call(func=_load(helper_name), args=[source, *map(_load, captures)], keywords=[])

    def _history_count(self, e: ExprIR) -> ast.Call:
        source, predicate = e.operands
        source_expr = self.expr(source)
        past = _python_name(e.data["past"])
        current = _python_name(e.data["current"])
        plan = e.data["plan"]

        def on_item(term: ExprIR, past_name: str) -> ast.expr:
            return _FillNames({past: _load(past_name), current: _load("_b_item")}).visit(self.expr(term))

        slots = {}
        if plan in ("previous-test", "prefix-min", "prefix-max"):
            side = e.data["past_side"]
            paired = predicate if plan == "previous-test" else order_comparison(predicate)
            if paired is None:
                raise BError("E_INTERNAL", "An extrema history plan requires an ordered comparison")
            previous_test = on_item(paired.operands[side], "_b_item")
            current_test = on_item(paired.operands[1 - side], "_b_item")
            if plan == "previous-test":
                same_test = ast.dump(previous_test) == ast.dump(current_test)
                slots = {"CURRENT": current_test, "PAST": _load("_b_now") if same_test else previous_test}
                template = """
_b_previous = False
for _b_item in _b_source:
    _b_now = CURRENT
    if _b_previous and _b_now:
        _b_hits += 1
    _b_previous = PAST
"""
            else:
                compare = _COMPARISONS[e.data["comparison"]]
                improve = ast.Lt if plan == "prefix-min" else ast.Gt
                slots = {"PAST": previous_test,
                         "MATCH": ast.Compare(left=_load("_b_best"), ops=[compare()], comparators=[current_test]),
                         "IMPROVES": ast.Compare(left=_load("_b_candidate"), ops=[improve()],
                                                 comparators=[_load("_b_best")])}
                template = """
_b_best = None
for _b_item in _b_source:
    if _b_best is not None and MATCH:
        _b_hits += 1
    _b_candidate = PAST
    if _b_best is None or IMPROVES:
        _b_best = _b_candidate
"""
        elif plan == "previous-item":
            slots["MATCH"] = on_item(predicate, "_b_past")
            template = """
_b_seen = False
for _b_item in _b_source:
    if _b_seen and MATCH:
        _b_hits += 1
    _b_past = _b_item
    _b_seen = True
"""
        elif plan == "prefix-search":
            slots["MATCH"] = on_item(predicate, "_b_past")
            template = """
for _b_pos, _b_item in _b_enumerate(_b_source):
    for _b_index in _b_range(_b_pos):
        _b_past = _b_source[_b_index]
        if MATCH:
            _b_hits += 1
            break
"""
        else:
            raise BError("E_INTERNAL", f"Unknown history plan: {plan}")
        loop = _FillNames(slots).visit(ast.parse(template)).body
        body = [_assign("_b_hits", ast.Constant(0)), *loop, ast.Return(value=_load("_b_hits"))]
        return self._collection_call("history", source_expr, body, {past, current})

    def expr(self, e: ExprIR, *, rule_params=()) -> ast.expr:
        op, children, data = e.op, e.operands, e.data
        if op == "literal":
            return ast.Constant(data)
        if op == "name":
            return ast.Name(id=_python_name(data), ctx=ast.Load())
        if op == "let_expr":
            binder = _python_name(data)
            val_expr = self.expr(children[0])
            with self._bind([binder]):
                body_expr = self.expr(children[1])
            lam = ast.Lambda(
                args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=binder)],
                                   vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[]),
                body=body_expr,
            )
            return ast.Call(func=lam, args=[val_expr], keywords=[])
        if op == "list_comp":
            binder = _python_name(data)
            source_expr = self.expr(children[0])
            with self._bind([binder]):
                elt_expr = self.expr(children[1])
                ifs = [self.expr(children[2])] if len(children) == 3 else []
            return ast.ListComp(
                elt=elt_expr,
                generators=[ast.comprehension(target=ast.Name(id=binder, ctx=ast.Store()),
                                              iter=source_expr, ifs=ifs, is_async=0)],
            )
        if op == "record_make":
            keys = [ast.Constant(fname) for fname in data["fields"]]
            vals = [self.expr(child) for child in children]
            return ast.Dict(keys=keys, values=vals)
        if op == "record_field":
            return ast.Subscript(value=self.expr(children[0]), slice=ast.Constant(data), ctx=ast.Load())
        if op == "record_with":
            self._used_record_with = True
            base = self.expr(children[0])
            updates = ast.Dict(keys=[ast.Constant(k) for k in data],
                               values=[self.expr(c) for c in children[1:]])
            return ast.Call(func=_load("_b_record_with"), args=[base, updates], keywords=[])
        if op == "builtin":
            self._used_builtins.add(data)
            return ast.Call(func=_load(_BUILTIN_MAP[data]),
                            args=[self.expr(c) for c in children], keywords=[])
        if op == "builtin_from_json":
            self._used_from_json = True
            args = [self.expr(children[0]), ast.Constant(data)]
            if self._has_records:
                args.append(_load("_b_records"))
            return ast.Call(func=_load("_b_from_json"), args=args, keywords=[])
        if op == "list":
            return ast.List(elts=[self.expr(x) for x in children], ctx=ast.Load())
        if op == "dict":
            if len(children) % 2:
                raise BError("E_INTERNAL", "Odd number of dictionary children in BIR")
            return ast.Dict(keys=[self.expr(x) for x in children[::2]], values=[self.expr(x) for x in children[1::2]])
        if op == "history_count":
            return self._history_count(e)
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
            return self._guard_call(self.expr(children[0], rule_params=rule_params), str(e.typ))
        if op == "conditional":
            test = None
            if rule_params and children[1].op == "literal" and children[1].data is True:
                test = _indexed_facts(children[0], rule_params)
            return ast.IfExp(test=test or self.expr(children[0]), body=self.expr(children[1]),
                             orelse=self.expr(children[2]))
        if op == "coalesce":
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
            if s.backend not in ("py", "net", "js", "go", "rs") or not s.target or not s.name:
                raise BError("E_INTERNAL", "Invalid import BIR")
            adapter = {
                "py": "_b_py", "net": "_b_net", "js": "_b_js_module",
                "go": "_b_go", "rs": "_b_rs",
            }[s.backend]
            return ast.Assign(targets=[ast.Name(id=_python_name(s.name), ctx=ast.Store())], value=ast.Call(
                func=ast.Name(id=adapter, ctx=ast.Load()),
                args=[ast.Constant(s.target)], keywords=[]))
        if s.op in ("foreign", "permit", "unit", "currency", "record", "probe", "expect"):
            return ast.Pass()
        if s.op == "let":
            return ast.Assign(targets=[ast.Name(id=_python_name(s.name), ctx=ast.Store())], value=self.expr(s.expr))
        if s.op == "fn":
            names = [_python_name(n) for n, _ in s.params]
            args = ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in names],
                                 vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
            body: list[ast.stmt] = []
            for name, typ in s.params:
                name = _python_name(name)
                body.append(ast.Assign(targets=[ast.Name(id=name, ctx=ast.Store())],
                                       value=self._guard_call(ast.Name(id=name, ctx=ast.Load()), str(typ))))
            if s.requires is not None:
                with self._bind(names):
                    precondition = self.expr(s.requires)
                body.append(ast.If(test=ast.UnaryOp(op=ast.Not(), operand=precondition),
                    body=[ast.Raise(exc=ast.Call(func=ast.Name(id="_b_contract_error", ctx=ast.Load()),
                                  args=[ast.Constant(f"Precondition of {s.name} failed")], keywords=[]),
                                    cause=None)], orelse=[]))
            with self._bind(names):
                params = s.params if s.declared_pure and s.typ == BOOL else ()
                body.append(_assign("_b_result", self.expr(s.expr, rule_params=params)))
            if s.ensures is not None:
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
        self._used_builtins.clear()
        self._has_records = bool(program.records)
        self._used_record_with = False
        self._used_from_json = False

        statements = [self.statement(s) for s in program.statements]

        builtins = ast.ImportFrom(module="builtins", names=[
            ast.alias(name="print", asname="_b_print"),
            ast.alias(name="getattr", asname="_b_getattr"),
            ast.alias(name="len", asname="_b_len"),
            ast.alias(name="enumerate", asname="_b_enumerate"),
            ast.alias(name="range", asname="_b_range"),
        ], level=0)
        rt_names = [
            ast.alias(name="py_module", asname="_b_py"),
            ast.alias(name="net_module", asname="_b_net"),
            ast.alias(name="guard", asname="_b_guard"),
            ast.alias(name="BAssertionError", asname="_b_assertion_error"),
            ast.alias(name="BContractError", asname="_b_contract_error"),
        ]
        if any(s.op == "import" and s.backend == "go" for s in program.statements):
            rt_names.append(ast.alias(name="go_module", asname="_b_go"))
        if any(s.op == "import" and s.backend == "rs" for s in program.statements):
            rt_names.append(ast.alias(name="rs_module", asname="_b_rs"))
        for bname in sorted(self._used_builtins):
            rt_names.append(ast.alias(name=f"b_{bname}", asname=_BUILTIN_MAP[bname]))
        if self._used_record_with:
            rt_names.append(ast.alias(name="b_record_with", asname="_b_record_with"))
        if self._used_from_json:
            rt_names.append(ast.alias(name="b_from_json", asname="_b_from_json"))

        body: list[ast.stmt] = [builtins, ast.ImportFrom(module="b_lang.runtime", names=rt_names, level=0)]
        if self._has_records:
            rec_keys = [ast.Constant(r.name) for r in program.records]
            rec_vals = [ast.Constant(tuple((n, str(t)) for n, t in r.fields)) for r in program.records]
            body.append(ast.Assign(targets=[ast.Name(id="_b_records", ctx=ast.Store())],
                                   value=ast.Dict(keys=rec_keys, values=rec_vals)))
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
        body.extend(self._helpers)
        body.extend(statements)
        return ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
