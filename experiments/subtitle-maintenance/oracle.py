"""Independent finite boundary grid. The candidate rules are executed by check.py."""
from itertools import product


def boundary_cases(revision):
    # Truth table for isolated durations, indexed by word class and effect kind.
    floors = {
        False: (1000, 550, 550, 1000),
        True: (750, 750, 750, 750),
    }
    # Ages relative to start. Negative and zero indicate absent/expired/abutting.
    ages = (-1200, -1, 0, 1, 79, 80, 81, 160)
    durations = (-1, 0, 1, 549, 550, 551, 749, 750, 751, 999, 1000, 1001)
    start = 1200
    for spoken_age, effect_age, duration, words, effect in product(ages, ages, durations, range(4), (False, True)):
        args = (start, start + duration, start + spoken_age, start + effect_age, words, effect)
        # Derive each independent violation; issue precedence is a separate fixed list.
        flags = {
            "bad-time": duration in (-1, 0),
            "overlap": effect_age > 0 or spoken_age > (0 if revision < 2 or effect else 80),
            "brief": duration < (1000 if revision == 0 else floors[effect][words]),
        }
        expected = next((key for key in ("bad-time", "overlap", "brief") if flags[key]), "ok")
        yield args, expected
