"""Matched starter, product brief and two encodings of each handoff."""

TASKS = {
    "shade": {
        "starter": (
            "fn shade(zone: Int) -> Int pure requires zone >= 0 and zone <= 9 = "
            "if zone <= 2 then 4 else if zone <= 6 then 6 else 9\n"
            "fn label(index: Int) -> Int pure = index + 2\n"
        ),
        "brief": "Apply the approved palette handoff. Preserve all other shades, the functions' interfaces and their input domains.",
        "prose": "In shade, when zone equals 6, return 3.",
        "directive": "next shade when zone == 6 => 3",
    },
    "signal": {
        "starter": (
            "fn signal(channel: Int, phase: Int) -> Int pure requires channel >= 0 and channel <= 2 "
            "and phase >= 0 and phase <= 5 = if channel == 0 then 10 + phase else channel + phase\n"
            "fn label(index: Int) -> Int pure = index + 2\n"
        ),
        "brief": (
            "Apply the outstanding signal handoff to the current display. Channel 0 is now reserved for "
            "diagnostics: its existing output must be preserved at every phase because a separate monitor reads it. "
            "The other channels are public. Preserve all unaffected behavior, interfaces and input domains."
        ),
        "prose": "In signal, when phase equals 3, return 8.",
        "directive": "next signal when phase == 3 => 8",
    },
}
