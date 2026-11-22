"""Check the pulse-profile result and measure the native and Python implementations."""

import argparse
import json
import platform
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns
from timeit import Timer

from pulse_cases import CAPTURE, cases, merge
from python_baselines import library_summary, loop_summary

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "profile.bee"


def load_b():
    from b_lang.compiler import compile_b

    result = compile_b(SOURCE.read_text(encoding="utf-8"), strict=True)
    env = {}
    exec(result.code, env)
    return result, env


def checked_summary(xs):
    """Specialized Python equivalent of the typed input boundary on this task."""
    if type(xs) is not list:
        raise TypeError("expected list")
    snapshot = xs.copy()
    for x in snapshot:
        if type(x) is not int:
            raise TypeError("expected exact ints")
    return library_summary(snapshot)


def implementations():
    from b_lang.runtime import guard

    _, public = load_b()

    def same_guards(xs):
        snapshot = guard(xs, "List[Int]")
        return guard(library_summary(snapshot), "Dict[Text, Int]")

    # Resolve the one backend reduction helper used by this profile. The
    # public function additionally checks the input list and result dictionary.
    kernels = [fn for name, fn in public.items() if name.startswith("_b_summary_")]
    if len(kernels) != 1:
        raise ValueError("Expected one reduction helper; inspect backend before timing its kernel")
    return {
        "b_public": public["profile"],
        "python_checked_library": checked_summary,
        "python_same_b_guards": same_guards,
        "b_kernel": kernels[0],
        "python_library": library_summary,
        "python_loop": loop_summary,
    }


def check(engines):
    from b_lang.runtime import BBoundaryError

    rows = splits = 0
    for label, xs, expected in cases():
        for name, fn in engines.items():
            actual = fn(xs)
            if actual != expected or any(type(value) is not int for value in actual.values()):
                raise AssertionError((name, label, xs, actual, expected))
        # This property concerns the B operation. Recompute each split, including
        # empty ends, and compare with the independently known result.
        profile = engines["b_public"]
        for cut in range(len(xs) + 1):
            combined = merge(profile(xs[:cut]), profile(xs[cut:]))
            if combined != expected:
                raise AssertionError((label, xs, cut, combined, expected))
            splits += 1
        rows += 1
    for invalid in ((0, 1), [0, True], [1.0], [None]):
        for name in ("b_public", "python_checked_library", "python_same_b_guards"):
            try:
                engines[name](invalid)
            except (BBoundaryError, TypeError):
                continue
            raise AssertionError((name, "accepted invalid input", invalid))
    return {"valid_cases": rows, "b_split_checks": splits, "invalid_cases": 4}


def run_warm(engines, repetitions=7):
    import random

    rng = random.Random(1600)
    inputs = {"empty": [], "captured_32": CAPTURE,
              "mixed_10000": [rng.randrange(-250, 251) for _ in range(10_000)]}
    results = {}
    for label, xs in inputs.items():
        expected = library_summary(xs)
        for name, fn in engines.items():
            if fn(xs) != expected:
                raise AssertionError((name, label))
        timers = {name: Timer(lambda fn=fn: fn(xs)) for name, fn in engines.items()}
        # Target roughly 10 ms per sample, even for very short/empty lists.
        counts = {}
        for name, timer in timers.items():
            n = 1
            while timer.timeit(n) < 0.010:
                n *= 2
            counts[name] = n
        samples = {name: [] for name in timers}
        order = list(timers)
        for round_no in range(repetitions):
            for name in order[round_no % len(order):] + order[:round_no % len(order)]:
                elapsed = timers[name].timeit(counts[name])
                samples[name].append(elapsed * 1e6 / counts[name])
        results[label] = {name: round(median(samples[name]), 3) for name in timers}
    return results


def run_cold(repetitions=7):
    # Identical timer/driver/framework imports on both sides. The B arm also
    # reads and compiles the .bee source; Python imports its ordinary .py module.
    modes = ["b_public", "python_checked_library"]
    timings = {m: [] for m in modes}
    for i in range(repetitions + 1):
        for mode in modes if i % 2 == 0 else modes[::-1]:
            start = perf_counter_ns()
            proc = subprocess.run([sys.executable, __file__, "--once", mode],
                                  capture_output=True, text=True, check=True)
            elapsed = (perf_counter_ns() - start) / 1e6
            if json.loads(proc.stdout) != library_summary(CAPTURE):
                raise AssertionError((mode, proc.stdout))
            if i > 0:
                timings[mode].append(elapsed)
    return {mode: round(median(values), 3) for mode, values in timings.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing", action="store_true", help="also measure warm and cold calls")
    parser.add_argument("--once", choices=("b_public", "python_checked_library"),
                        help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.once:
        fn = load_b()[1]["profile"] if options.once == "b_public" else checked_summary
        print(json.dumps(fn(CAPTURE)))
    else:
        engines = implementations()
        report = {"interpreter": platform.python_implementation() + " " + platform.python_version(),
                  **check(engines)}
        if options.timing:
            report["warm_median_us"] = run_warm(engines)
            report["fresh_process_median_ms"] = run_cold()
        print(json.dumps(report, indent=2))
