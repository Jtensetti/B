def classify(start: int, end: int, spoken_until: int, effect_until: int, words: int, effect: bool) -> str:
    if end <= start:
        return "bad-time"
    if start < effect_until:
        return "overlap"
    spoken_overlap = min(end, spoken_until) - start
    if spoken_overlap > (0 if effect else 80):
        return "overlap"
    if effect:
        minimum = 750
    elif words in (1, 2):
        minimum = 550
    else:
        minimum = 1000
    return "brief" if end - start < minimum else "ok"
