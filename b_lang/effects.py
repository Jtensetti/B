"""Conservative static effect inventory for B 0.6.

This is not a runtime sandbox. `foreign` covers all behavior of an imported
Python or .NET module (including initialization); it is deliberately broad.
"""
from __future__ import annotations
from .ir import ExprIR, StmtIR
from .types import Type

ALLOWED = frozenset({"console", "foreign"})


def expression_effects(node: ExprIR, symbols: dict) -> frozenset[str]:
    effects: set[str] = set()
    if node.op == "call":
        if node.foreign_path:
            effects.add("foreign")
        elif node.operands and node.operands[0].op == "name":
            name = node.operands[0].data
            symbol = symbols.get(name)
            effects.update(symbol.effects if symbol and symbol.effects is not None else {"foreign"})
        else:
            effects.add("foreign")
    elif node.op == "attr" and node.foreign_path:
        # Python descriptors and module attribute lookup may execute code.
        effects.add("foreign")
    for c in node.operands:
        effects.update(expression_effects(c, symbols))
    return frozenset(effects)


def statement_effects(stmt: StmtIR) -> frozenset[str]:
    if stmt.op == "import":
        return frozenset({"foreign"})
    if stmt.op == "print":
        return frozenset({"console"})
    if stmt.op == "fn":
        # A declared function's latent effects are included in a program-level
        # permit declaration; otherwise unreachable unsafe functions could hide.
        return frozenset(stmt.effects)
    return frozenset(stmt.effects)
