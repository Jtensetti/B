"""Seeded comparison of adopted B kernels with their ordinary Python variants.

This is a regression test for a small supported expression subset, not a
formal proof of equivalence for arbitrary Python programs.
"""
from __future__ import annotations

import random
import math

from b_lang.compiler import compile_b
from b_examples import pure_kernels


def test_adopted_source_matches_python_on_2000_reproducible_cases():
    program = compile_b("""adopt py:b_examples.pure_kernels.square as square
adopt py:b_examples.pure_kernels.forward as forward
adopt py:b_examples.pure_kernels.clamp as clamp
adopt py:b_examples.pure_kernels.positive as positive
adopt py:b_examples.pure_kernels.ratio as ratio""", strict=True)
    ns = {}
    exec(program.code, ns, ns)
    rng = random.Random(7007)
    for _ in range(400):
        x = rng.uniform(-1000, 1000)
        a = rng.uniform(-250, 250)
        b = a + rng.uniform(0.001, 1000)
        n = rng.randrange(-10000, 10001)
        divider = rng.choice([-1., 1.]) * rng.uniform(.1, 100)
        assert math.isclose(ns["square"](x), pure_kernels.square(x), rel_tol=1e-13)
        assert ns["forward"](n) == pure_kernels.forward(n)
        assert ns["clamp"](x, a, b) == pure_kernels.clamp(x, a, b)
        assert ns["positive"](n) == pure_kernels.positive(n)
        assert ns["ratio"](x, divider) == pure_kernels.ratio(x, divider)
