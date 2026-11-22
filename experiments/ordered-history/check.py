"""Compare four B history expressions with direct observations of the requested events."""
from itertools import groupby, product
from pathlib import Path
import runpy

from b_lang.compiler import compile_b
from python_patterns import late_pairs, late_pairs_state, overlaps_any_index, overlaps_any_scan, overlaps_sorted


HERE = Path(__file__).resolve().parent


def load_functions():
    compiled = compile_b((HERE / "patterns.bee").read_text(encoding="utf-8"), strict=True)
    functions = {}
    exec(compiled.code, functions)
    return functions


def pulse_oracle(xs):
    # A block of r positive ticks contributes r-1 adjacent pairs.
    return sum(len(list(run)) - 1 for positive, run in groupby(xs, key=lambda x: x > 0) if positive)


def interval_oracle(cues, *, neighbors=False):
    # Intersect actual half-open intervals. Count positions, including only the
    # first witnessed intersection for a given position.
    matches = 0
    for i, current in enumerate(cues):
        start = i - 1 if neighbors and i > 0 else 0
        for j in range(start, i):
            prior = cues[j]
            width = min(current["end"], prior["end"]) - max(current["start"], prior["start"])
            if width > 0:
                matches += 1
                break
    return matches


def as_rows(pairs):
    return [{"start": start, "end": end} for start, end in pairs]


def check_fixture(functions):
    root = HERE.parent / "subtitle-maintenance"
    reader = runpy.run_path(str(root / "check.py"))["read_cues"]
    cues = list(reader((root / "lecture.vtt").read_text(encoding="utf-8")))
    invalid = [cue.name for cue in cues if cue.end <= cue.start]
    valid = as_rows((cue.start, cue.end) for cue in cues if cue.end > cue.start)
    assert functions["overlap_count"](as_rows((cue.start, cue.end) for cue in cues)) is None
    assert invalid == ["reversed"]
    assert len(valid) == 7
    assert functions["overlaps_sorted"](valid) == functions["overlaps_any_order"](valid) == interval_oracle(valid) == 3
    return {"valid_cues": len(valid), "overlap_positions": 3, "invalid_duration_ids": invalid}


def check():
    fn = load_functions()
    words = 0
    for size in range(9):
        for xs in product((0, 1), repeat=size):
            assert fn["late_pairs"](list(xs)) == late_pairs(xs) == late_pairs_state(xs) == pulse_oracle(xs)
            words += 1
    assert fn["late_pairs"]([-7, 2**100, 3, 1, -2]) == 2
    alphabet = [(start, end) for start in range(3) for end in range(start + 1, 4)]
    total = sorted_cases = 0
    for size in range(5):
        for seq in product(alphabet, repeat=size):
            cues = as_rows(seq)
            expected = interval_oracle(cues)
            assert fn["overlap_count"](cues) == expected
            assert fn["overlaps_any_order"](cues) == overlaps_any_index(cues) == overlaps_any_scan(cues) == expected
            total += 1
            if all(a[0] <= b[0] for a, b in zip(seq, seq[1:])):
                assert fn["overlaps_sorted"](cues) == overlaps_sorted(cues) == expected
                assert fn["overlaps_neighbors"](cues) == interval_oracle(cues, neighbors=True)
                sorted_cases += 1
    nested = as_rows([(0, 100), (10, 20), (30, 40)])
    assert fn["overlaps_neighbors"](nested) == 1
    assert fn["overlaps_sorted"](nested) == fn["overlaps_any_order"](nested) == 2
    unsorted = as_rows([(10, 11), (0, 1)])
    assert fn["overlaps_sorted"](unsorted) == 1
    assert fn["overlaps_any_order"](unsorted) == interval_oracle(unsorted) == 0
    for record in ({}, {"start": 0}, {"end": 1}, {"start": 4, "end": 4}, {"start": 4, "end": 3}):
        assert fn["overlap_count"]([record]) is None
    assert fn["overlap_count"](as_rows([(-10, 0), (-3, 1)])) == 1
    return {"binary_pulse_words": words, "interval_sequences": total, "sorted_subset": sorted_cases,
            "vtt_fixture": check_fixture(fn)}


if __name__ == "__main__":
    print(check())
