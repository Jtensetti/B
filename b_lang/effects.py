"""Conservative static effect inventory for B.

This is not a runtime sandbox. `foreign` covers all behavior of an imported
Python, .NET, Node.js, Go or Rust module (including initialization); it is
deliberately broad.
"""
from __future__ import annotations
from .ir import ExprIR, StmtIR

ALLOWED = frozenset({"console", "foreign"})


def expression_effects(node: ExprIR, symbols: dict) -> frozenset[str]:
    effects: set[str] = set()
    if node.op == "builtin":
        if node.data == "stdin_text":
            effects.add("console")
    elif node.op == "call":
        if node.foreign_path:
            effects.add("foreign")
        elif node.operands and node.operands[0].op == "name":
            name = node.operands[0].data
            symbol = symbols.get(name)
            effects.update(symbol.effects if symbol and symbol.effects is not None else {"foreign"})
        else:
            effects.add("foreign")
    elif node.op == "attr" and node.foreign_path:
        effects.add("foreign")
    for c in node.operands:
        effects.update(expression_effects(c, symbols))
    return frozenset(effects)


def statement_effects(stmt: StmtIR) -> frozenset[str]:
    if stmt.op == "import":
        return frozenset({"foreign"})
    if stmt.op == "print":
        return frozenset({"console"}) | frozenset(stmt.effects)
    return frozenset(stmt.effects)
