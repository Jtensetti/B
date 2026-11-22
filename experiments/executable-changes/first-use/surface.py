"""Derive a tiny callable interface for both booking fixtures; abort on ambiguity."""
import ast
from pathlib import Path

from b_lang.compiler import compile_b

FIXTURES = Path(__file__).resolve().parents[1]


def from_b(source):
    statements = compile_b(source).ir.statements
    return "\n".join(f"{fn.name}({', '.join(param for param, _ in fn.params)})"
                     for fn in statements if fn.op == 'fn')


def from_python(source):
    module = ast.parse(source)
    definitions = {}
    for stmt in module.body:
        if isinstance(stmt, ast.FunctionDef):
            definitions[stmt.name] = tuple(arg.arg for arg in stmt.args.args)
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.value, ast.Set):
            table = stmt.targets[0].id
            uses = {tuple(x.id for x in c.left.elts) for c in ast.walk(module)
                    if isinstance(c, ast.Compare) and len(c.ops) == 1 and isinstance(c.ops[0], ast.In)
                    and isinstance(c.comparators[0], ast.Name) and c.comparators[0].id == table
                    and isinstance(c.left, ast.Tuple) and all(isinstance(x, ast.Name) for x in c.left.elts)}
            if len(uses) != 1:
                raise ValueError(f'Could not infer unique tuple headings for {table}')
            definitions[table] = uses.pop()
        else:
            raise ValueError('Unsupported Python fixture')
    return "\n".join(f"{name}({', '.join(params)})" for name, params in definitions.items())


if __name__ == '__main__':
    b = from_b((FIXTURES / 'booking.bee').read_text())
    python = from_python((FIXTURES / 'booking.py').read_text())
    assert b == python
    print(b)
