"""Deterministic differential test: small native B expressions vs Python semantics.

This probes the implemented subset. It is not a proof of B's correctness or of
foreign library behavior, and it intentionally uses only safe generated inputs.
"""
import io
import random
from contextlib import redirect_stdout

from b_lang.compiler import compile_b


def expression(rng, depth):
    if depth == 0:
        number = rng.randrange(-40, 41)
        return str(number), str(number)
    operation = rng.choice(['plus', 'minus', 'times', 'branch'])
    if operation == 'branch':
        left = rng.randrange(-10, 11)
        right = rng.randrange(-10, 11)
        yes, pyes = expression(rng, depth - 1)
        no, pno = expression(rng, depth - 1)
        cond = f'{left} <= {right}'
        return (f'(if {cond} then {yes} else {no})',
                f'({pyes} if {cond} else {pno})')
    left, py_left = expression(rng, depth - 1)
    right, py_right = expression(rng, depth - 1)
    op = {'plus': '+', 'minus': '-', 'times': '*'}[operation]
    return f'({left} {op} {right})', f'({py_left} {op} {py_right})'


def test_300_deterministic_expressions_match_python():
    rng = random.Random(20261121)
    for _ in range(300):
        b_expr, py_expr = expression(rng, rng.randint(0, 4))
        checked = compile_b(f'let output: Int = {b_expr}\nprint output', strict=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            exec(checked.code, {'__name__': '__b_test__'})
        assert int(buf.getvalue().strip()) == eval(py_expr, {'__builtins__': {}}), b_expr
