"""Compare lowering of the same checked predicate against compiled and idiomatic Python."""
import json
import marshal
import platform
import random
from statistics import median
from time import perf_counter_ns
from unittest.mock import patch

from b_lang.compiler import compile_b
from b_lang.runtime import guard


def build(source):
    start = perf_counter_ns()
    compiled = compile_b(source, strict=True)
    names = {}
    exec(compiled.code, names)
    return names["eligible"], (perf_counter_ns() - start) / 1_000_000


def python_rules(rows):
    keys = frozenset(rows)

    def raw(slot, tag):
        return (slot, tag) in keys

    def guarded(slot, tag):
        slot = guard(slot, "Int")
        tag = guard(tag, "Text")
        return guard((slot, tag) in keys, "Bool")

    return raw, guarded


def trial(size):
    rng = random.Random(1729)
    rows = [(i, f"t{i % 5}") for i in range(size)]
    source = ('fn eligible(slot: Int, tag: Text) -> Bool pure = false\n'
              + '\n'.join(f'also eligible({i}, "{tag}")' for i, tag in rows))
    modes = list(range(4)) * 256
    rng.shuffle(modes)
    queries = []
    for mode in modes:
        slot, tag = rng.choice(rows)
        if mode == 2:
            slot += size
        elif mode == 3:
            tag = "other"
        queries.append((slot, tag))
    expected = [mode < 2 for mode in modes]

    elapsed = {"scan": [], "adaptive": []}
    functions = {}
    for run in range(5):
        order = ("adaptive", "scan") if run % 2 else ("scan", "adaptive")
        for label in order:
            if label == "scan":
                # Change code generation only. The parser, analyser, and BIR are identical.
                with patch("b_lang.lowering._INDEX_MIN_ROWS", size + 1):
                    fn, milliseconds = build(source)
            else:
                fn, milliseconds = build(source)
            elapsed[label].append(milliseconds)
            functions[label] = fn
    functions["python_set"], functions["python_guarded_set"] = python_rules(rows)
    for fn in functions.values():
        assert [fn(*pair) for pair in queries] == expected
    times = {key: [] for key in functions}
    order = list(times)
    for _ in range(9):
        rng.shuffle(order)
        for name in order:
            fn = functions[name]
            start = perf_counter_ns()
            for _ in range(4):
                for pair in queries:
                    fn(*pair)
            times[name].append((perf_counter_ns() - start) / (4 * len(queries)))
    return {
        "rows": size,
        "constant_index": any(isinstance(v, frozenset) for v in functions["adaptive"].__code__.co_consts),
        "ns_per_lookup": {k: round(median(v)) for k, v in times.items()},
        "compile_and_load_ms": {k: round(median(v), 2) for k, v in elapsed.items()},
        "serialized_function_bytes": {k: len(marshal.dumps(functions[k].__code__)) for k in elapsed},
    }


if __name__ == "__main__":
    compile_b("fn warm() -> Bool pure = false")
    measurements = [trial(size) for size in (1, 16, 32, 64, 256, 512)]
    print(json.dumps({"python": platform.python_version(), "machine": platform.machine(),
                      "results": measurements}, indent=2))
