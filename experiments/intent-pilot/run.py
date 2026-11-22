"""Replay the fixed clarifications and score later B/Python source changes."""
import argparse
import json
import platform
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product as cross

from b_lang.clarification import compare
from b_lang.compiler import compile_b

import baseline as py
from cases import PRODUCTS, Product


CLAUSES = {
    "labels": {
        "fixed": "result == level + 2",
        "tighten": "result >= level + 1 and result <= level + 2",
        "loosen": "result >= level + 2 and result <= level + 3",
        "flexible": "result >= level + 1 and result <= level + 3",
    },
    "tabs": {
        "stay": "result == index",
        "home": "result == index or (keyboard == 1 and result == 0)",
        "end": "result == index or (keyboard == 0 and result == 3)",
        "both-edges": "result == index or (keyboard == 1 and result == 0) or (keyboard == 0 and result == 3)",
    },
}
DOMAIN = {"labels": "level >= 0 and level <= 4", "tabs": "index >= 0 and index <= 3 and keyboard >= 0 and keyboard <= 1"}
METHODS = ("B", "typed Python", "plain language", "passive")


def make_source(p, expression):
    return f"fn current({p.declarations}) -> Int pure requires {DOMAIN[p.name]} = {expression}"


def b_function(source, name):
    ns = {}
    prog = compile_b(source)
    exec(prog.code, ns)
    return ns[name]


@dataclass
class Evidence:
    product: Product
    program: object
    grid: dict
    edit_results: dict
    policies: dict


def prepare(p):
    ir = compile_b(make_source(p, p.default)).ir
    grid = {name: sorted({point[i] for point in p.calibration}) for i, name in enumerate(p.parameters)}
    assert set(cross(*grid.values())) == set(p.calibration)
    assert set(p.calibration).isdisjoint(p.later)
    predicates = {}
    for name, clause in CLAUSES[p.name].items():
        fn = b_function(f"fn permitted({p.declarations}, output: Int) -> Bool pure = "
                        + clause.replace("result", "output"), "permitted")
        predicates[name] = fn
        for point, value in cross(p.calibration + p.later, p.outputs):
            assert fn(*point, value) == py.permits(p.name, name, point, value)
    edits = {}
    for name, expr in p.edits.items():
        revised = b_function(make_source(p, expr), "current")
        for point in p.calibration:
            assert revised(*point) == py.edited(p.name, name, point) == p.defaults(point)
        edits[name] = [(point, revised(*point)) for point in p.later]
        for point, value in edits[name]:
            assert value in p.outputs and value == py.edited(p.name, name, point)
    return Evidence(p, ir, grid, edits, predicates)


def b_question(data, evidence):
    p = data.product
    def named(point):
        return dict(zip(p.parameters, point))
    report = compare(data.program, "current", CLAUSES[p.name], data.grid, list(p.outputs),
                     answers=[(named(point), out, answer) for point, out, answer in evidence])
    question = report["question"]
    key = None if question is None else (tuple(question["inputs"][n] for n in p.parameters), question["result"])
    return tuple(report["survivors"]), key


def run(data, scenario, world, method):
    p = data.product
    evidence = [(point, p.defaults(point), True) for point in p.calibration]
    if scenario == "documented":
        for point, value, _ in p.cards:
            evidence.append((point, value, p.owner(world, point, value)))
    elif scenario == "conflicting-omission":
        evidence.append((*p.undocumented_witness, True))
        assert p.owner(world, *p.undocumented_witness)
    budget = 1 if scenario == "one-answer" else 2
    asked = []
    while True:
        if method == "B":
            live, question = b_question(data, evidence)
        else:
            response = py.choose(p.name, p.alternatives, p.calibration, p.outputs, evidence)
            live, question = response.survivors, response.question
            if method == "plain language":
                question = py.fixed_card(p.name, live, ((pt, v) for pt, v, _ in p.cards))
            elif method == "passive":
                question = None
        if question is None or len(asked) == budget:
            break
        point, value = question
        answer = p.owner(world, point, value)
        item = {"point": list(point), "output": value, "answer": answer}
        if method == "plain language":
            item["wording"] = next(text for pt, out, text in p.cards if (pt, out) == (point, value))
        asked.append(item)
        evidence.append((point, value, answer))

    decisions = {}
    for revision, outputs in data.edit_results.items():
        truth = all(p.owner(world, point, value) for point, value in outputs)
        if method == "B":
            votes = {all(data.policies[name](*point, value) for point, value in outputs) for name in live}
        else:
            votes = {all(py.permits(p.name, name, point, py.edited(p.name, revision, point))
                         for point in p.later) for name in live}
        judgment = next(iter(votes)) if len(votes) == 1 else None
        outcome = ("deferred" if judgment is None else
                   ("correct-accept" if truth else "false-accept") if judgment else
                   ("false-block" if truth else "correct-block"))
        decisions[revision] = outcome
    return {"product": p.name, "scenario": scenario, "world": world, "method": method,
            "questions": asked, "survivors": sorted(live), "decisions": decisions}


def timings():
    """Time the same 24 selector queries, with compilation and behavioral scoring excluded."""
    snapshots = []
    for p in PRODUCTS:
        data = prepare(p)
        for world in p.alternatives:
            evidence = [(point, p.defaults(point), True) for point in p.calibration]
            for _ in range(3):
                snapshots.append((data, tuple(evidence)))
                response = py.choose(p.name, p.alternatives, p.calibration, p.outputs, evidence)
                if response.question is None:
                    break
                point, value = response.question
                evidence.append((point, value, p.owner(world, point, value)))

    times = {"B": [], "typed Python": []}
    for repeat in range(12):
        order = ("B", "typed Python") if repeat % 2 == 0 else ("typed Python", "B")
        for method in order:
            start = time.perf_counter_ns()
            for data, answers in snapshots:
                p = data.product
                if method == "B":
                    b_question(data, answers)
                else:
                    py.choose(p.name, p.alternatives, p.calibration, p.outputs, answers)
            if repeat > 0:
                times[method].append((time.perf_counter_ns() - start) / 1_000_000)
    return {"queries_per_batch": len(snapshots), "measured_batches": 11,
            "python": platform.python_version(), "median_ms_per_batch":
            {key: round(statistics.median(series), 3) for key, series in times.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", action="store_true", help="print individual questions and edit decisions")
    parser.add_argument("--timing", action="store_true", help="time matched selector calls on the included policies")
    args = parser.parse_args()
    if args.timing:
        print(json.dumps(timings(), indent=2))
        return
    trace = args.trace
    totals = defaultdict(Counter)
    for p in PRODUCTS:
        data = prepare(p)
        scenarios = ([("included", w) for w in p.alternatives] +
                     [("documented", p.alternatives[1]), ("one-answer", p.alternatives[1]),
                      ("silent-omission", "unlisted"), ("conflicting-omission", "unlisted")])
        for scenario, world in scenarios:
            records = [run(data, scenario, world, method) for method in METHODS]
            b, python = records[:2]
            # Test agreement of independently implemented selectors and runtimes.
            for key in ("questions", "survivors", "decisions"):
                if b[key] != python[key]:
                    raise AssertionError((p.name, scenario, world, key, b[key], python[key]))
            for row in records:
                counts = totals[(row["scenario"], row["method"])]
                counts.update(row["decisions"].values())
                counts["answers"] += len(row["questions"])
                counts["cases"] += 1
                counts["no-survivor"] += not row["survivors"]
                if trace:
                    print(json.dumps(row))
    if not trace:
        print(json.dumps([{"scenario": k[0], "method": k[1], **dict(v)} for k, v in totals.items()], indent=2))


if __name__ == "__main__":
    main()
