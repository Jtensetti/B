"""Measure the question cost for nine fixed output policies with a known optimal tree."""
from functools import cache
import json

from b_lang.clarification import compare
from b_lang.compiler import compile_b


# Each policy lists the integer results allowed for the sole input x = 0.
POLICIES = {
    "A": (2, 4),
    "B": (0, 1),
    "C": (0, 2),
    "D": (0, 1, 4),
    "E": (1,),
    "F": (0, 3, 4),
    "G": (0, 1, 2),
    "H": (0, 3),
    "I": (0, 1, 3),
}
QUESTIONS = tuple(range(5))


def split(survivors, question):
    allowed = frozenset(name for name in survivors if question in POLICIES[name])
    return allowed, survivors - allowed


@cache
def optimum(survivors):
    """Minimum possible worst-case remaining depth, trying every useful question."""
    if len(survivors) == 1:
        return 0
    costs = []
    for question in QUESTIONS:
        yes, no = split(survivors, question)
        if yes and no:
            costs.append(1 + max(optimum(yes), optimum(no)))
    return min(costs)


def interview(program, predicates, strategy):
    protocols = {}
    for name, allowed in POLICIES.items():
        answers = []
        questions = []
        while True:
            report = compare(program, "policy", predicates, {"x": [0]}, QUESTIONS,
                             answers=answers, strategy=strategy)
            if report["status"] == "selected":
                if report["survivors"] != [name]:
                    raise AssertionError((name, report["survivors"]))
                break
            question = report["question"]["result"]
            if question not in QUESTIONS or question in questions:
                raise AssertionError((name, question, questions))
            questions.append(question)
            answers.append(({"x": 0}, question, question in allowed))
        protocols[name] = questions
    return {"questions": protocols, "worst_case": max(map(len, protocols.values())),
            "finished_within_four": sum(len(qs) <= 4 for qs in protocols.values())}


def run():
    program = compile_b("fn policy(x: Int) -> Int = x").ir
    predicates = {name: " or ".join(f"result == {r}" for r in allowed)
                  for name, allowed in POLICIES.items()}
    survivors = frozenset(POLICIES)
    costs = {}
    for question in QUESTIONS:
        yes, no = split(survivors, question)
        costs[question] = {"yes": len(yes), "no": len(no),
                           "worst_with_optimal_followups": 1 + max(optimum(yes), optimum(no))}
    return {"policies": len(POLICIES),
            "production": {s: interview(program, predicates, s) for s in ("balanced", "minimax")},
            "optimal_max": optimum(survivors), "first_question_costs": costs}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
