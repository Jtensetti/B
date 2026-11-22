"""Log exact brief, optional current-source and public-feedback packets for ongoing participants."""
import json
from pathlib import Path
import sys

from sequence import BRIEFS, apply_edit, evaluate


def main():
    stage, arm, action = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    before = Path("program.bee").read_text()
    root = Path(f".stage{stage}")
    root.mkdir(exist_ok=True)
    event = {"action": action}
    ok = True
    if action == "brief":
        out = BRIEFS[stage] + "\n"
    elif action == "source":
        out = before
    elif action == "submit":
        no = 1 + len(list(root.glob("attempt-*.json")))
        if no > 2:
            sys.exit("Submission limit reached")
        register, name = sys.argv[4:6]
        payload = Path(name).read_text()
        event.update(register=register, payload=payload)
        try:
            if arm == "ordinary" and register == "short":
                raise ValueError("Use b or full")
            result = apply_edit(before, register, payload)
            verdict = evaluate(result, stage, True)
            ok = verdict["accepted"]
            out = f"Public {'pass' if ok else 'fail'}: {verdict['passed']}/{verdict['total']}\n"
            if verdict["failures"]:
                out += "\n".join(verdict["failures"]) + "\n"
            if ok:
                (root / "accepted.bee").write_text(result)
        except Exception as error:
            ok, out = False, str(error) + "\n"
        (root / f"attempt-{no}.json").write_text(json.dumps({"register": register, "payload": payload, "feedback": out}))
    else:
        sys.exit("Choose brief, source or submit FORMAT payload.txt")
    event["response"] = out
    with (root / "events.jsonl").open("a") as stream:
        stream.write(json.dumps(event) + "\n")
    sys.stdout.write(out)
    return int(not ok)


if __name__ == "__main__":
    sys.exit(main())
