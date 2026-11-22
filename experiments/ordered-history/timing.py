"""Warm end-to-end calls, excluding compilation and input construction."""
from platform import python_version
from random import Random
from statistics import median
from timeit import Timer

from b_lang.runtime import guard

from check import as_rows, load_functions
from python_patterns import late_pairs, late_pairs_state, overlaps_any_index, overlaps_any_scan, overlaps_sorted


def bench(xs, descriptor, b_fn, python_functions):
    def checked(fn):
        return lambda: guard(fn(guard(xs, descriptor)), "Int")

    expected = python_functions[0][1](xs)
    calls = {"B": lambda: b_fn(xs)}
    for label, fn in python_functions:
        calls[label] = lambda fn=fn: fn(xs)
        calls[label + "+guards"] = checked(fn)
    for run in calls.values():
        assert run() == expected
    calls["input guard"] = lambda: guard(xs, descriptor)
    timers = {label: Timer(run) for label, run in calls.items()}
    iterations = {}
    measurements = {label: [] for label in timers}
    for label, timer in timers.items():
        n = 1
        while timer.timeit(n) < 0.010:
            n *= 2
        iterations[label] = n
    order = list(timers)
    for round_no in range(7):
        offset = round_no % len(order)
        for label in order[offset:] + order[:offset]:
            n = iterations[label]
            measurements[label].append(timers[label].timeit(n) * 1e6 / n)
    return {key: round(median(vals), 1) for key, vals in measurements.items()}


if __name__ == "__main__":
    print("CPython", python_version())
    f = load_functions()
    rng = Random(1700)
    xs = [rng.randrange(-10, 11) for _ in range(4096)]
    print("pulses", len(xs), bench(xs, "List[Int]", f["late_pairs"], [("pairwise", late_pairs), ("last bit", late_pairs_state)]))
    rows = as_rows((3*i, 3*i + rng.randrange(1, 9)) for i in range(1024))
    desc = "List[Dict[Text,Int]]"
    print("sorted", len(rows), bench(rows, desc, f["overlaps_sorted"], [("running max", overlaps_sorted)]))
    for n in (128, 512):
        rows = as_rows((2*i, 2*i+1) for i in reversed(range(n)))
        print("unordered, disjoint", n, bench(rows, desc, f["overlaps_any_order"],
              [("scan", overlaps_any_scan), ("index", overlaps_any_index)]))
