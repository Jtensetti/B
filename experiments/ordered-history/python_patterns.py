"""Direct Python implementations on validated, nonempty half-open intervals."""
from bisect import bisect_left
from itertools import pairwise


def late_pairs(xs):
    return sum(p > 0 and q > 0 for p, q in pairwise(xs))


def late_pairs_state(xs):
    previously_late = False
    total = 0
    for x in xs:
        late = x > 0
        if late and previously_late:
            total += 1
        previously_late = late
    return total


def overlaps_sorted(cues):
    furthest = None
    total = 0
    for cue in cues:
        if furthest is not None and furthest > cue["start"]:
            total += 1
        end = cue["end"]
        if furthest is None or end > furthest:
            furthest = end
    return total


def overlaps_any_scan(cues):
    # Stop after the first earlier witness, matching the B quantifier.
    total = 0
    for i, q in enumerate(cues):
        start, end = q["start"], q["end"]
        for j in range(i):
            p = cues[j]
            if p["start"] < end and start < p["end"]:
                total += 1
                break
    return total


def overlaps_any_index(cues):
    # A binary indexed tree stores maximum end by ordered start coordinate.
    # Coordinates of all starts are known; only previous ends enter the tree.
    starts = sorted({cue["start"] for cue in cues})
    maxima = [None] * (len(starts) + 1)
    total = 0
    for cue in cues:
        start, end = cue["start"], cue["end"]
        i = bisect_left(starts, end)
        while i:
            best = maxima[i]
            if best is not None and best > start:
                total += 1
                break
            i -= i & -i
        i = bisect_left(starts, start) + 1
        while i < len(maxima):
            if maxima[i] is None or end > maxima[i]:
                maxima[i] = end
            i += i & -i
    return total
