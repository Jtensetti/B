"""Check the same-input observables protected by a native `also ... keeping`.

Absence of a dependency on the extended predicate suffices for preservation.
Work on typed, unoptimized BIR so dead branches and opaque operations cannot
silently enlarge the current proof fragment.
"""
from collections import deque
from collections.abc import Iterable

from .ir import ExprIR, ProgramIR, StmtIR
from .model import Stmt
from .types import BOOL, FLOAT, INT, NONE, TEXT, BError


_SCALARS = {BOOL, INT, FLOAT, TEXT, NONE}
_SCALAR_OPS = {"literal", "name", "call", "guard", "cmp", "conditional", "not",
               "and", "or", "neg", "add", "sub", "mul", "div", "mod"}


def function_dependencies(definition: StmtIR) -> list[str]:
    """Return references of a checked native scalar definition, rejecting opaque operations."""
    if (definition.op not in {"fn", "let"} or definition.backend or definition.effects
            or definition.typ not in _SCALARS or any(t not in _SCALARS for _, t in definition.params)
            or (definition.op == "fn" and not definition.declared_pure)):
        raise BError("E_KEEPING", f"Cannot establish keeping through {definition.name}: "
                     "expected a native pure scalar function or immutable scalar binding")

    names = {n for n, _ in definition.params}
    dependencies = {}

    def visit(node: ExprIR, locals_: set[str]):
        if node.foreign_path or node.op not in _SCALAR_OPS or node.typ not in _SCALARS:
            raise BError("E_KEEPING", f"Cannot establish keeping through {definition.name}: "
                         f"unsupported operation {node.op} ({node.typ})")
        operands = node.operands
        if node.op == "call":
            callee, *operands = operands
            if callee.op != "name" or callee.typ.name != "Function" or callee.foreign_path:
                raise BError("E_KEEPING", f"Cannot establish keeping through indirect call in {definition.name}")
            dependencies[callee.data] = None
        elif node.op == "name" and node.data not in locals_:
            dependencies[node.data] = None
        for child in operands:
            visit(child, locals_)

    visit(definition.expr, names)
    if definition.requires is not None:
        visit(definition.requires, names)
    if definition.ensures is not None:
        visit(definition.ensures, names | {"result"})
    return list(dependencies)


def validate_preservation(program: ProgramIR, declarations: Iterable[Stmt]) -> None:
    """Reject a protected observable with a known or uninspectable dependency."""
    definitions = {s.name: s for s in program.statements if s.name is not None}
    edges = {}
    checked = set()
    for declaration in declarations:
        target, _, protected = declaration.parts[:3]
        if len(set(protected)) != len(protected):
            raise BError("E_KEEPING", f"Duplicate function in keeping clause for {target}")
        for observable in protected:
            if (target, observable) in checked:
                continue
            if observable not in definitions or definitions[observable].op != "fn":
                raise BError("E_KEEPING", f"Unknown protected function {observable}")
            parents = {observable: None}
            pending = deque([observable])
            while pending:
                name = pending.popleft()
                if name == target:
                    path = [name]
                    while parents[path[-1]] is not None:
                        path.append(parents[path[-1]])
                    raise BError("E_KEEPING", f"Cannot keep {observable} independent of {target}: "
                                 + " -> ".join(reversed(path)))
                if name not in edges:
                    if name not in definitions:
                        raise BError("E_KEEPING", f"Unknown transitive binding {name} in keeping {observable}")
                    edges[name] = function_dependencies(definitions[name])
                for dependency in edges[name]:
                    if dependency not in parents:
                        parents[dependency] = name
                        pending.append(dependency)
            checked.add((target, observable))
