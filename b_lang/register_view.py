"""Read-only source views checked against the original program's typed BIR."""
from functools import cache
from importlib import resources
from pathlib import Path
import sys

from lark import Lark, Tree
from lark.exceptions import LarkError

from .compiler import compile_b
from .types import BError


@cache
def _positioned_parser():
    # Ordinary compilation needs no source spans. Obtain them only for this view.
    grammar = resources.files("b_lang").joinpath("syntax.lark").read_text()
    return Lark(grammar, parser="lalr", maybe_placeholders=True, propagate_positions=True)


def _text(source, tree):
    return source[tree.meta.start_pos:tree.meta.end_pos]


def _unwrap(tree):
    while tree.data in ("postfix", "grouped") and len(tree.children) == 1:
        tree = tree.children[0]
    return tree


def _outer_tables(tree):
    pending = [tree]
    while pending:
        item = pending.pop()
        if item.data == "case_table":
            yield item
        else:
            pending.extend(child for child in reversed(item.children) if isinstance(child, Tree))


def _expand(source, table):
    _, pivot, *rows, fallback = table.children
    parts = []
    for row in rows:
        op, threshold, value = row.children
        parts.append(f"if {pivot} {op} {_text(source, threshold)} then {_ordinary(source, value)} else ")
    parts.append(_ordinary(source, fallback))
    return "".join(parts)


def _ordinary(source, expr):
    top = _unwrap(expr)
    if top.data == "case_table":
        return _expand(source, top)
    parts = []
    start = expr.meta.start_pos
    for table in _outer_tables(expr):
        parts.extend((source[start:table.meta.start_pos], "(" + _expand(source, table) + ")"))
        start = table.meta.end_pos
    parts.append(source[start:expr.meta.end_pos])
    return "".join(parts)


def _literal(source, expr):
    item = _unwrap(expr)
    if item.data in ("number", "string", "true", "false", "none"):
        return _text(source, item)
    if item.data == "neg":
        number = _unwrap(item.children[0])
        if number.data == "number":
            return "-" + _text(source, number)
    return None


def _cases(source, expr):
    if _unwrap(expr).data == "case_table":
        return _text(source, expr)
    remainder = expr
    rows = []
    pivot = None
    while (current := _unwrap(remainder)).data == "conditional":
        test, value, fallback = current.children
        test = _unwrap(test)
        if test.data != "comparison":
            break
        left, op, right = test.children
        left = _unwrap(left)
        literal = _literal(source, right)
        if left.data != "identifier" or literal is None:
            break
        name = str(left.children[0])
        if pivot is not None and name != pivot:
            break
        pivot = name
        rows.append(f"  {op} {literal} => {_text(source, value)}")
        remainder = fallback
    if not rows:
        raise BError("E_REGISTER_VIEW", "A cases view needs an if chain comparing the same name on the left "
                     "to scalar literals. Use the ordinary register for this function.")
    # An unmatched tail can stay in ordinary B inside the fallback row.
    rows.append(f"  else => {_text(source, remainder)}")
    return f"cases {pivot} {{\n" + "\n".join(rows) + "\n}"


def function_view(source: str, function: str, register: str) -> str:
    """Return the selected function declaration after rechecking it in context."""
    if register not in ("ordinary", "cases"):
        raise BError("E_REGISTER_VIEW", f"Unknown register {register!r}")
    original = compile_b(source)
    tree = _positioned_parser().parse(source if source.endswith("\n") else source + "\n")
    fn = next((s for s in tree.children if s.data == "fn_stmt" and s.children[0] == function), None)
    if fn is None:
        raise BError("E_REGISTER_VIEW", f"No source function named {function!r}")
    expr = fn.children[-1]
    expression = _ordinary(source, expr) if register == "ordinary" else _cases(source, expr)
    declaration = source[fn.meta.start_pos:expr.meta.start_pos] + expression
    revised = source[:fn.meta.start_pos] + declaration + source[fn.meta.end_pos:]
    try:
        revised_ir = compile_b(revised).ir
    except BError as error:
        raise BError("E_REGISTER_VIEW", f"The rendered declaration could not be rechecked: {error}") from error
    if revised_ir != original.ir:
        raise BError("E_REGISTER_VIEW", "The requested rendering changed the program's typed BIR")
    return declaration


def add_command(sub):
    parser = sub.add_parser("view", help="Render a source function in another register, checking its typed BIR")
    parser.add_argument("file", type=Path)
    parser.add_argument("--function", required=True)
    parser.add_argument("--register", required=True, choices=("ordinary", "cases"))


def run(args, read_source):
    try:
        print(function_view(read_source(args.file), args.function, args.register))
    except (BError, OSError, ValueError, LarkError, RecursionError) as exc:
        print(f"B view: {exc}", file=sys.stderr)
        return 1
    return 0
