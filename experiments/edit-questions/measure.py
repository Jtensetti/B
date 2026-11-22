"""Compare policy identification with questions about one pending edit in fresh and shared sessions."""
import json
from pathlib import Path

from b_lang.clarification import compare
from b_lang.compiler import compile_b
from b_lang.edit_clarification import decide_edit


FIXTURES = Path(__file__).resolve().parents[2] / "examples/intent"


def drive(base, edit, request, permissions, answers, identify):
    def owner(rank, gap):
        return (gap == rank + 1 or (rank == 0 and gap == 2 and "compact" in permissions)
                or (rank == 2 and gap == 4 and "wide" in permissions))

    args = (request["function"], request["candidates"], request["axes"], request["outputs"], answers)
    start = len(answers)
    for _ in range(3):
        report = compare(base, *args) if identify else decide_edit(base, edit, *args)
        question = report["question"]
        if question is None:
            break
        inputs, result = question["inputs"], question["result"]
        answers.append((inputs, result, owner(inputs["rank"], result)))
    report = decide_edit(base, edit, *args)
    assert report["status"] in ("approve", "reject")
    return report["status"], len(answers) - start


def measure():
    interface = (FIXTURES / "layout.bee").read_text()
    base = compile_b(interface).ir
    request = json.loads((FIXTURES / "layout.json").read_text())
    edits = {
        "algebraic_refactor": (set(), "1 + rank"),
        "compact": ({"compact"}, "if rank == 0 then 2 else rank + 1"),
        "wide": ({"wide"}, "if rank == 2 then 4 else rank + 1"),
        "compact_and_wide": ({"compact", "wide"}, "if rank == 0 then 2 else if rank == 2 then 4 else rank + 1"),
    }
    compiled = {name: compile_b(interface.replace("= rank + 1\n", "= " + expression + "\n")).ir
                for name, (_, expression) in edits.items()}
    results = {}
    for mode, identify in (("identify_then_decide", True), ("decide_edit", False)):
        for session in ("fresh_per_edit", "reuse_answers"):
            questions = dict.fromkeys(edits, 0)
            correct = 0
            for permissions in [set(), {"compact"}, {"wide"}, {"compact", "wide"}]:
                answers = []
                for name, (needed, _) in edits.items():
                    history = [] if session == "fresh_per_edit" else answers
                    verdict, count = drive(base, compiled[name], request, permissions, history, identify)
                    correct += verdict == ("approve" if needed <= permissions else "reject")
                    questions[name] += count
            results[mode + "/" + session] = {"correct_of_16": correct, "questions": sum(questions.values()),
                                              "questions_by_edit": questions}
    return results


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
