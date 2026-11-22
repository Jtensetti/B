"""Check the loop emitted for one concrete B program against an inductive reference."""
import ast
from copy import deepcopy

from b_lang.compiler import compile_b


B_SOURCE = """fn pairs(xs: List[Bool]) -> Int pure ensures result >= 0 =
    count adjacent previous, current in xs where previous and current
"""

REFERENCE = """
def adjacent_pairs(flags):
    total = 0
    last = False
    for flag in flags:
        current = flag
        if last and current:
            total += 1
        last = current
    return total
"""


class RenameLocals(ast.NodeTransformer):
    """Canonical variable names for this single-scope function with no free names."""

    def __init__(self):
        self.names = {}

    def local(self, name):
        if name not in self.names:
            self.names[name] = f"v{len(self.names)}"
        return self.names[name]

    def visit_Name(self, node):
        node.id = self.local(node.id)
        return node

    def visit_arg(self, node):
        node.arg = self.local(node.arg)
        return node


def structure(function):
    node = deepcopy(function)
    node.name = "kernel"
    return ast.dump(RenameLocals().visit(node), include_attributes=False)


def validate(generated):
    functions = [fn for fn in ast.parse(generated).body if isinstance(fn, ast.FunctionDef)]
    kernel, = [fn for fn in functions if fn.name.startswith("_b_history_")]
    public, = [fn for fn in functions if fn.name == "pairs"]
    calls = [node for node in ast.walk(public) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == kernel.name]
    return len(calls) == 1 and structure(kernel) == structure(ast.parse(REFERENCE).body[0])


if __name__ == "__main__":
    actual = compile_b(B_SOURCE, strict=True).source
    if not validate(actual):
        raise SystemExit("The emitted loop needs a new equivalence argument.")
    # Negative controls: one counts twice, one incorrectly includes the first item.
    if validate(actual.replace("+= 1", "+= 2")) or validate(actual.replace("= False", "= True")):
        raise SystemExit("The structural check accepted an incorrect variant.")
    print("Boolean-pair kernel matches the inductive reference. Two incorrect variants rejected.")
