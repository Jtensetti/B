"""Frozen product briefs, baseline policies and public examples for the editing trial."""
PARAMS = ("start", "end", "spoken_until", "effect_until", "words", "effect")
COMMON = """Maintain a lecture subtitle timing checker. Keep classify(start, end, spoken_until,
effect_until, words, effect) -> text. The first five parameters are integers, effect is boolean.
All times are integer milliseconds. The two *_until values give the maximum end
of all preceding positive-duration cues of that kind, or zero if none. Words is
a nonnegative count. The reporter emits only one issue in this priority order:
end <= start means "bad-time"; prohibited overlap means "overlap"; a positive
duration below the applicable floor means "brief"; otherwise "ok". A cue that
starts exactly at another's end does not overlap. Times and counts are nonnegative."""
REQUEST = {
    1: """Change the duration floor. A spoken cue of exactly one or two words needs
550 ms. Other spoken cues, including empty ones, still need 1000 ms. A sound
effect of any length needs 750 ms. Keep all prior overlap and ordering rules.""",
    2: """The live-caption editor now permits up to and including 80 ms of overlap
between spoken cues. Any overlap involving a sound cue still counts, even when a
longer spoken cue is also active. Keep duration rules and issue priority.""",
}
BASE = {
    "bee": 'fn classify(start: Int, end: Int, spoken_until: Int, effect_until: Int, words: Int, effect: Bool) -> Text pure = if end <= start then "bad-time" else if start < spoken_until or start < effect_until then "overlap" else if end - start < 1000 then "brief" else "ok"\n',
    "py": '''def classify(start: int, end: int, spoken_until: int, effect_until: int, words: int, effect: bool) -> str:
    if end <= start:
        return "bad-time"
    if start < max(spoken_until, effect_until):
        return "overlap"
    return "brief" if end - start < 1000 else "ok"
''',
}
PUBLIC = {
    1: [((0, 550, 0, 0, 1, False), "ok"), ((0, 740, 0, 0, 1, True), "brief"),
        ((900, 1900, 901, 0, 4, False), "overlap")],
    2: [((1000, 1800, 1050, 0, 2, False), "ok"), ((1000, 1400, 0, 1001, 1, False), "overlap"),
        ((2000, 2500, 0, 0, 1, False), "brief")],
}
