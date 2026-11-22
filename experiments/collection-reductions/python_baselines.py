"""Pulse summaries for an already valid list of ints."""


def library_summary(xs):
    return {
        "n": len(xs), "net": sum(xs), "early": sum(x < 0 for x in xs),
        "lo": min(xs, default=0), "hi": max(xs, default=0),
    }


def loop_summary(xs):
    if not xs:
        return {"n": 0, "net": 0, "early": 0, "lo": 0, "hi": 0}
    total = early = 0
    lo = hi = xs[0]
    for x in xs:
        total += x
        early += x < 0
        if x < lo:
            lo = x
        elif x > hi:
            hi = x
    return {"n": len(xs), "net": total, "early": early, "lo": lo, "hi": hi}
