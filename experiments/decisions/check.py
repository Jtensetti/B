"""How many decisions does it take to reach a hidden policy?

An owner knows a policy but has not written it down. B starts from two
examples and asks; the owner answers from the hidden policy. The comparison
gives a learner the same number of examples chosen at random, and also counts
how many random examples it takes before the derived rule is exactly right.
A second part changes the policy and counts the owner's lines and answers.

Run from the repository root:

    python experiments/decisions/check.py
"""
from __future__ import annotations

import itertools
import json
import random
import statistics
import sys

import b_lang.learn as learning
from b_lang.learn import learn, render
from b_lang.types import BError

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ROLES = ("guest", "staff", "admin")


def policy(name, params, result, domains, truth):
    axes = [(False, True) if t == "Bool" else domains[n] for n, t in params]
    return {"name": name, "params": params, "result": result, "domains": domains, "truth": truth,
            "inputs": list(itertools.product(*axes))}


POLICIES = [
    policy("weekend children", [("child", "Bool"), ("day", "Text")], "Int", {"day": DAYS},
           lambda c, d: 0 if c and d in ("sat", "sun") else 100),
    policy("age bands", [("age", "Int")], "Int", {"age": tuple(range(100))},
           lambda a: 50 if a < 12 else 70 if a >= 65 else 100),
    policy("shipping", [("express", "Bool"), ("weight", "Int")], "Int", {"weight": tuple(range(31))},
           lambda e, w: 90 if e else 60 if w >= 10 else 30),
    policy("dispatch", [("days", "Int")], "Text", {"days": tuple(range(-5, 16))},
           lambda d: "overdue" if d < 0 else "today" if d == 0 else "priority" if d <= 3 else "standard"),
    policy("access", [("role", "Text"), ("hour", "Int")], "Bool", {"role": ROLES, "hour": tuple(range(24))},
           lambda r, h: r == "admin" or (r == "staff" and 8 <= h < 18)),
    policy("per item (outside the rule language)", [("items", "Int")], "Int", {"items": tuple(range(1, 11))},
           lambda n: 10 * n),
]


def derive(p, rows):
    return learn("f", p["params"], p["result"], rows, {}, p["domains"])


def accuracy(p, rule):
    return sum(rule.apply(x) == p["truth"](*x) for x in p["inputs"]) / len(p["inputs"])


def ask_until_settled(p, rows, limit=80):
    rows = list(rows)
    asked = 0
    while True:
        found = derive(p, rows)
        if found.determined or asked >= limit:
            return found, rows, asked
        rows.append((found.question, p["truth"](*found.question)))
        asked += 1


def random_runs(p, count, trials=20):
    scores, exact = [], 0
    for seed in range(trials):
        chosen = random.Random(seed).sample(p["inputs"], min(count, len(p["inputs"])))
        try:
            rule = derive(p, [(x, p["truth"](*x)) for x in chosen]).rule
            score = accuracy(p, rule)
        except BError:
            score = 0.0
        scores.append(score)
        exact += score == 1.0
    return statistics.mean(scores), exact / trials


def random_until_exact(p, trials=10):
    needed = []
    for seed in range(trials):
        order = random.Random(seed).sample(p["inputs"], len(p["inputs"]))
        for n in sorted({*range(2, 21), *range(20, len(order) + 1, 5), len(order)}):
            try:
                if accuracy(p, derive(p, [(x, p["truth"](*x)) for x in order[:n]]).rule) == 1.0:
                    needed.append(n)
                    break
            except BError:
                pass
        else:
            needed.append(None)
    reached = [n for n in needed if n is not None]
    return {"median": statistics.median(reached) if reached else None,
            "reached": f"{len(reached)}/{trials}"}


def identification():
    rows = []
    for p in POLICIES:
        seeds = [(x, p["truth"](*x)) for x in (p["inputs"][0], p["inputs"][-1])]
        try:
            found, used, asked = ask_until_settled(p, seeds)
        except BError as exc:
            rows.append({"policy": p["name"], "domain": len(p["inputs"]), "b": f"refused: {exc.message}"})
            continue
        names = [n for n, _ in p["params"]]
        mean, exact = random_runs(p, len(used))
        variants = {}
        for label, setting in (("without_neighbor_questions", ("_COVERAGE", False)),
                               ("with_two_extra_tests", ("_SLACK", 2))):
            old = getattr(learning, setting[0])
            setattr(learning, setting[0], setting[1])
            try:
                other, _, other_asked = ask_until_settled(p, seeds)
                variants[label] = {"questions": other_asked, "accuracy": round(accuracy(p, other.rule), 3)}
            finally:
                setattr(learning, setting[0], old)
        rows.append({
            "policy": p["name"], "domain": len(p["inputs"]), "questions": asked,
            **variants,
            "b_accuracy": accuracy(p, found.rule), "rule": render(found.rule, names),
            "random_same_count_mean_accuracy": round(mean, 3), "random_same_count_exact": exact,
            "random_examples_until_exact": random_until_exact(p),
        })
    return rows


def changes():
    """Two requirement changes on settled programs. Count the owner's work."""
    report = []
    sat_only = POLICIES[0] | {"truth": lambda c, d: 0 if c and d == "sat" else 100}
    seeds = [((False, "mon"), 100), ((True, "sat"), 0)]
    found, rows, asked = ask_until_settled(sat_only, seeds)
    before = asked
    weekend = POLICIES[0]
    # The owner states the change. An earlier answer about Sunday is restated with was.
    restated = any(x == (True, "sun") for x, _ in rows)
    rows = [(x, v) for x, v in rows if x != (True, "sun")] + [((True, "sun"), 0)]
    found, rows, asked = ask_until_settled(weekend, rows)
    report.append({"change": "children free on Sundays too", "questions_to_build": before,
                   "owner_lines": 1, "uses_was": restated, "questions_after_change": asked,
                   "accuracy": accuracy(weekend, found.rule), "rule": render(found.rule, ["child", "day"])})

    bands = POLICIES[1]
    found, rows, asked = ask_until_settled(bands, [((30,), 100), ((5,), 50)])
    older = bands | {"truth": lambda a: 50 if a < 14 else 70 if a >= 65 else 100}
    stale = [(x, v) for x, v in rows if older["truth"](*x) != v]
    revised = [(x, older["truth"](*x)) for x, _ in rows] + [((13,), 50)]
    unique = list({x: (x, v) for x, v in revised}.values())
    found2, _, asked2 = ask_until_settled(older, unique)
    report.append({"change": "child rate up to and including 13", "questions_to_build": asked,
                   "owner_lines": len(stale) + (0 if any(x == (13,) for x, _ in rows) else 1),
                   "examples_restated_with_was": len(stale), "questions_after_change": asked2,
                   "accuracy": accuracy(older, found2.rule), "rule": render(found2.rule, ["age"])})
    return report


if __name__ == "__main__":
    json.dump({"identification": identification(), "changes": changes()}, sys.stdout, indent=2, ensure_ascii=False)
    print()
