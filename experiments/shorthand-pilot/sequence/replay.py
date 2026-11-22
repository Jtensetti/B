"""Replay the two continuing contexts in order, preserving every accepted change."""
import hashlib
import json
from pathlib import Path
import sys

from sequence import BRIEFS, apply_edit, evaluate
from b_lang.shorthand import expand_shorthand
from b_lang.handoff import inspect_handoff
from submit import materialize
from tasks import COMMON, CARDS, TASKS

HERE = Path(__file__).resolve().parent
PILOT = HERE.parent


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def packets():
    first_runs = {r["id"]: r for r in json.loads((PILOT / "results.json").read_text())}
    rows = []
    for run in json.loads((HERE / "results.json").read_text()):
        arm = run["arm"]
        first = first_runs[run["id"]]["attempts"][0]
        payload = (PILOT / "submissions" / first["file"]).read_text()
        canonical = None
        if first["register"] == "short":
            pending, _ = inspect_handoff(expand_shorthand(TASKS["dispatch"]["source"], payload), strict=True)
            canonical = "\n".join(pending) + "\n"
        rows.append(dict(id=run["id"], stage=1, generated=[payload], feedback=[first["feedback"]],
                         guide=[COMMON + "\n" + CARDS[arm] + "\n"], brief=[TASKS["dispatch"]["brief"] + "\n"],
                         source=[TASKS["dispatch"]["source"]], canonical=canonical))
        before = materialize("dispatch", first["register"], payload)
        for stage in run["stages"]:
            index = stage["stage"]
            row = dict(id=run["id"], stage=index, generated=[], feedback=[], guide=[], brief=[], source=[], canonical=None)
            attempts = iter(stage["attempts"])
            accepted_source = None
            for event in stage["events"]:
                action = event["action"]
                if action == "brief":
                    response = BRIEFS[index] + "\n"
                    row["brief"].append(response)
                elif action == "source":
                    response = before
                    row["source"].append(response)
                else:
                    assert action == "submit"
                    rec = next(attempts)
                    text = (HERE / "submissions" / rec["file"]).read_text()
                    edited = apply_edit(before, rec["register"], text)
                    assert evaluate(edited, index, True) == rec["public"]
                    assert evaluate(edited, index, False) == rec["independent"]
                    if rec["public"]["accepted"]:
                        accepted_source = edited
                    if rec["register"] == "short":
                        expanded = expand_shorthand(before, text)
                        pending, _ = inspect_handoff(expanded, strict=True)
                        canonical = "\n".join(pending) + "\n"
                        assert evaluate(apply_edit(before, "b", canonical), index, False)["accepted"]
                        row["canonical"] = canonical
                    response = rec["feedback"]
                    row["generated"].append(text)
                    row["feedback"].append(response)
                assert digest(response) == event["sha256"] and len(response.encode()) == event["bytes"]
            assert next(attempts, None) is None and accepted_source is not None
            rows.append(row)
            before = accepted_source
    return rows


if __name__ == "__main__":
    result = packets()
    if "--packets" in sys.argv:
        print(json.dumps(result))
    else:
        for stage, expected_count in ((2, 38), (3, 32)):
            text = (HERE / "submissions" / f"elm-{stage}-1.txt").read_text()
            fresh = apply_edit(TASKS["dispatch"]["source"], "short", text)
            assert evaluate(fresh, stage, True)["accepted"]
            mistaken = evaluate(fresh, stage, False)
            assert not mistaken["accepted"] and mistaken["passed"] == expected_count
            print(f"Stage {stage} with history discarded: {expected_count}/44")
        for row in result:
            print(f'{row["id"]}, stage {row["stage"]}, {len(row["generated"])} submission(s)')
