"""Compare one native revision to a Python set change, including protected observers."""

import argparse
from dataclasses import dataclass
from itertools import product
import json
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns

from b_lang.compiler import compile_b
import python_baseline


HERE = Path(__file__).resolve().parent
EXTENSIONS = {"B": ".bee", "Python": ".py", "typed Python": "_typed.py"}
BOOKINGS = tuple(product((False, True), ("mon", "fri", "sat", "sun"), (False, True)))
READINGS = tuple(product(("probe", "ref", "other"), ("setup", "sample", "idle"), (-3, 0, 7)))
# An already indexed project can supply this smaller card for either language.
# Include only the names, parameter order and literal conventions needed for the edit.
CARDS = {
    "booking": "free_entry(child, day) [sat, sun]\nseats(child, day, available)\nrecipient(child, day, gift)\n",
    "readings": "discard(sensor, phase) [probe, ref] [setup, sample]\nsamples(sensor, phase, previous)\n",
}


@dataclass
class Task:
    name: str
    request: str
    delta: dict
    cases: dict
    traces: object
    mutants: dict


def booking_observations():
    cases = {}
    for child, day, gift in BOOKINGS:
        # The accepted new policy charges all adults and children on weekdays.
        charge = 100 if not child or day in {"mon", "fri"} else 0
        cases["free_entry", (child, day)] = charge == 0
        cases["price", (child, day)] = charge
        cases["recipient", (child, day, gift)] = "buyer" if gift else "guest"
        for state in (-3, 0, 1, 4, 100, 200):
            cases["total", (child, day, state)] = state + charge
            cases["seats", (child, day, state)] = state - 1
    return cases


def booking_traces(program):
    for pair in product(BOOKINGS, repeat=2):
        money, left, recipients = 0, 2, []
        for child, day, gift in pair:
            money = program["total"](child, day, money)
            left = program["seats"](child, day, left)
            recipients.append(program["recipient"](child, day, gift))
        paying = sum(1 for child, day, _ in pair if not child or day in {"mon", "fri"})
        assert (money, left, recipients) == (
            100 * paying, 0, ["buyer" if gift else "guest" for _, _, gift in pair]
        ), pair
    return len(BOOKINGS) ** 2


def reading_observations():
    cases = {}
    for sensor, phase, value in READINGS:
        # During setup only the unrelated "other" sensor contributes.
        valid = phase != "setup" or sensor == "other"
        kept = value if valid else 0
        cases["discard", (sensor, phase)] = not valid
        cases["contribution", (sensor, phase, value)] = kept
        cases["channel", (sensor, phase)] = sensor
        for state in (-3, 0, 1, 7):
            cases["integrated", (sensor, phase, value, state)] = state + kept
            cases["samples", (sensor, phase, state)] = state + 1
    return cases


def reading_traces(program):
    for pair in product(READINGS, repeat=2):
        integrated, samples = 0, 0
        for sensor, phase, value in pair:
            integrated = program["integrated"](sensor, phase, value, integrated)
            samples = program["samples"](sensor, phase, samples)
        expected = sum(value for sensor, phase, value in pair if phase != "setup" or sensor == "other")
        assert (integrated, samples) == (expected, 2), pair
    return len(READINGS) ** 2


BOOKING = Task(
    "booking",
    "Also admit children free on Sunday. Keep seat allocation and receipt recipients unchanged.",
    {"B": 'also free_entry(true, "sun") keeping seats, recipient\n',
     "Python": 'also(free_entry, (True, "sun"), seats, recipient)\n'},
    booking_observations(), booking_traces,
    {
        "double seat": {
            "B": ('available - 1', 'if child and day == "sun" and available >= 2 then available - 2 else available - 1'),
            "Python": ('available - 1', 'available - 2 if child and day == "sun" and available >= 2 else available - 1')},
        "wrong recipient": {
            "B": ('if gift then "buyer" else "guest"', 'if child and day == "sun" then "guest" else if gift then "buyer" else "guest"'),
            "Python": ('"buyer" if gift else "guest"', '"guest" if child and day == "sun" else ("buyer" if gift else "guest")')},
        "stale cart total": {
            "B": ('previous + price(child, day)', 'previous + (if child and day == "sat" then 0 else 100)'),
            "Python": ('previous + price(child, day)', 'previous + (0 if child and day == "sat" else 100)')},
    },
)
READING = Task(
    "readings",
    'Also discard setup values from the reference sensor ("ref"). Keep counting every sample.',
    {"B": 'also discard("ref", "setup") keeping samples\n',
     "Python": 'also(discard, ("ref", "setup"), samples)\n'},
    reading_observations(), reading_traces,
    {
        "skip sample": {
            "B": ('previous + 1', 'if sensor == "ref" and phase == "setup" then previous else previous + 1'),
            "Python": ('previous + 1', 'previous if sensor == "ref" and phase == "setup" else previous + 1')},
        "wrong channel": {
            "B": ('Text pure = sensor\n', 'Text pure = if sensor == "ref" then "probe" else sensor\n'),
            "Python": ('return sensor\n', 'return "probe" if sensor == "ref" else sensor\n')},
    },
)


def syntax(language):
    return "B" if language == "B" else "Python"


def source(task, language):
    return (HERE / (task.name + EXTENSIONS[language])).read_text(encoding="utf-8")


def load(language, code):
    if syntax(language) == "Python":
        return python_baseline.load(code)
    namespace = {}
    exec(compile_b(code, strict=True).code, namespace)
    return namespace


def verdict(task, language, base, candidate):
    delta = task.delta[syntax(language)]
    if language == "B":
        from b_lang.revisions import check_revision
        return check_revision(base, candidate, delta=delta)["status"]
    return python_baseline.check(base, candidate, delta, task.cases)


def exercise(task, language):
    # Warm-process transaction, including opening the file, applying the edit,
    # checking the revision and independently compiling/loading and running it.
    start = perf_counter_ns()
    base = source(task, language)
    candidate = base + task.delta[syntax(language)]
    result = verdict(task, language, base, candidate)
    verified = perf_counter_ns()
    assert result == "proved", (task.name, language, result)
    program = load(language, candidate)
    for (name, args), expected in task.cases.items():
        actual = python_baseline.observe(program, name, args)
        assert type(expected) is type(actual) and actual == expected, (name, args, expected, actual)
    traces = task.traces(program)
    elapsed = perf_counter_ns() - start
    return (verified - start) / 1e6, elapsed / 1e6, traces


def substitution(code, old, new):
    assert code.count(old) == 1, old
    return code.replace(old, new)


def challenge(task, language):
    base = source(task, language)
    valid = base + task.delta[syntax(language)]
    outcomes = {"omitted edit": verdict(task, language, base, base)}
    for name, mutations in task.mutants.items():
        changed = substitution(valid, *mutations[syntax(language)])
        outcomes[name] = verdict(task, language, base, changed)
        # Mutants are valid syntax. Independently verify each changes a promised output.
        program = load(language, changed)
        assert any(python_baseline.observe(program, fn, args) != expected
                   for (fn, args), expected in task.cases.items()), name
    if task.name == "booking":
        # The original policy secretly tied seats to the price rule, through price().
        # The inherited coupling changes new Sunday seats even with a pristine candidate.
        replacements = {
            "B": ("available - 1", "if price(child, day) == 0 then available - 2 else available - 1"),
            "Python": ("available - 1", "available - 2 if price(child, day) == 0 else available - 1"),
        }
        coupled_base = substitution(base, *replacements[syntax(language)])
        coupled = coupled_base + task.delta[syntax(language)]
        outcomes["inherited seat coupling"] = verdict(task, language, coupled_base, coupled)
        # Without the explicit protection, pre-existing dependencies are allowed to propagate.
        unprotected = {"B": 'also free_entry(true, "sun")\n',
                       "Python": 'free_entry.add((True, "sun"))\n'}[syntax(language)]
        before = load(language, coupled_base)
        after = load(language, coupled_base + unprotected)
        assert (before["seats"](True, "sun", 3), after["seats"](True, "sun", 3)) == (2, 1)
    assert all(status in {"counterexample", "invalid"} for status in outcomes.values()), outcomes
    return outcomes


def token_ledger(path):
    # Each field is a separate message segment. A UI with different message
    # framing can change counts. A shared verdict spelling isolates semantic cost.
    texts = {}
    for task in (BOOKING, READING):
        for lang in EXTENSIONS:
            for field, value in (("spec", task.request), ("base", source(task, lang)), ("card", CARDS[task.name]),
                                 ("delta", task.delta[syntax(lang)]), ("verdict", "proved\n")):
                texts[f"{task.name}/{lang}/{field}"] = value
    texts["unguarded/B"] = 'also free_entry(true, "sun")\n'
    texts["unguarded/Python"] = 'free_entry.add((True, "sun"))\n'
    p = subprocess.run(
        ["node", str(HERE / "tokenize.mjs"), path], input=json.dumps(texts),
        text=True, capture_output=True, check=True,
    )
    return json.loads(p.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=9)
    parser.add_argument("--tokenizer", help="absolute path to a gpt-tokenizer ESM encoding")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    report = {}
    for task in (BOOKING, READING):
        samples = {lang: [] for lang in EXTENSIONS}
        for lang in EXTENSIONS:
            exercise(task, lang)
        for i in range(args.rounds):
            langs = list(EXTENSIONS)
            first = i % len(langs)
            langs = langs[first:] + langs[:first]
            for lang in langs:
                samples[lang].append(exercise(task, lang))
        for lang in EXTENSIONS:
            report[f"{task.name}/{lang}"] = {
                "observations": len(task.cases),
                "two_event_sequences": samples[lang][0][2],
                "edit_verify_ms_median": round(median(row[0] for row in samples[lang]), 3),
                "edit_verify_oracle_ms_median": round(median(row[1] for row in samples[lang]), 3),
                "challenges": challenge(task, lang),
            }
    if args.tokenizer:
        report["tokens"] = token_ledger(args.tokenizer)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
