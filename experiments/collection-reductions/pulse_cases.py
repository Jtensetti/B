"""Pulse timing offsets in microseconds. Rows give n, net, early, lo and hi."""

from itertools import product

FIELDS = ("n", "net", "early", "lo", "hi")
BIG = 2**100

# Sampled from a real timer, with values rounded down to whole microseconds.
CAPTURE = [94, 89, 76, 94, 77, 76, 74, 74, 70, 81, 71, 78, 118, 73, 76, 81,
           89, 78, 82, 77, 78, 80, 78, 103, 85, 76, 82, 77, 77, 76, 91, 73]
EXAMPLES = (
    ("captured 2 ms host timer", CAPTURE, (32, 2604, 0, 70, 118)),
    ("empty recording", [], (0, 0, 0, 0, 0)),
    ("one early tick", [-7], (1, -7, 1, -7, -7)),
    ("all on time", [0, 0, 0], (3, 0, 0, 0, 0)),
    ("only early", [-8, -1, -8], (3, -17, 3, -8, -1)),
    ("only late", [90, 2, 35], (3, 127, 0, 2, 90)),
    ("mixed offsets", [-3, 0, 4, -3, 6, 1, -2, 0], (8, 3, 3, -3, 6)),
    ("large clock offsets", [BIG, -BIG, BIG], (3, BIG, 1, -BIG, BIG)),
    ("beyond machine sum", [BIG, BIG], (2, 2 * BIG, 0, BIG, BIG)),
    ("separated late ticks", [6, -3, 6, -3], (4, 6, 2, -3, 6)),
    ("consecutive late ticks", [-3, -3, 6, 6], (4, 6, 2, -3, 6)),
)


def cases():
    for name, values, row in EXAMPLES:
        yield name, values, dict(zip(FIELDS, row, strict=True))
    # Establish answers from frequencies on a short alphabet, independently
    # of the B reducer and of the order in which the source elements appear.
    for length in range(6):
        for values in product((-3, 0, 6), repeat=length):
            early = values.count(-3)
            on_time = values.count(0)
            late = values.count(6)
            present = [x for x, count in ((-3, early), (0, on_time), (6, late)) if count]
            yield "small clock alphabet", list(values), {
                "n": length, "net": 6 * late - 3 * early, "early": early,
                "lo": present[0] if present else 0, "hi": present[-1] if present else 0,
            }


def merge(left, right):
    if left["n"] == 0:
        return right
    if right["n"] == 0:
        return left
    return {
        "n": left["n"] + right["n"],
        "net": left["net"] + right["net"],
        "early": left["early"] + right["early"],
        "lo": min(left["lo"], right["lo"]),
        "hi": max(left["hi"], right["hi"]),
    }
