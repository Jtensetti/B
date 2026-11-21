"""Bounded differential check of claimed interval proofs against execution.

Deterministic smoke testing is not itself a proof. The proof algorithm must
remain sound independently of this limited regression suite.
"""
from __future__ import annotations

import random

from b_lang.compiler import compile_b
from b_lang.types import BError


def test_proven_integer_contracts_survive_enumerated_inputs():
    rng = random.Random(20261121)
    proved = 0
    runtime_only = 0
    disproven = 0
    for _ in range(240):
        lo = rng.randrange(-12, 12)
        hi = rng.randrange(lo, 18)
        offset = rng.randrange(-8, 9)
        threshold = rng.randrange(-12, 18)
        source = (f'fn f(x: Int) -> Int pure requires x >= {lo} and x <= {hi} '
                  f'ensures result >= {threshold} = x + {offset}')
        try:
            program = compile_b(source)
        except BError as error:
            assert error.code == 'E_POSTCONDITION'
            assert all(x + offset < threshold for x in range(lo, hi+1))
            disproven += 1
            continue
        declared = program.ir.statements[0].verification
        if declared == 'runtime-check':
            runtime_only += 1
            continue
        assert declared == 'proved-interval'
        ns = {}
        exec(program.code, ns, ns)
        for x in range(lo, hi+1):
            assert ns['f'](x) == x + offset
            assert x + offset >= threshold
        proved += 1
    assert proved >= 50 and runtime_only + disproven >= 50
