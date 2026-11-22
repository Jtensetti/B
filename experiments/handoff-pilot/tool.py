"""Interface presented to a solver in a prepared working directory."""
import json
from pathlib import Path
import subprocess
import sys

from score import score
from tasks import TASKS


def main():
    task, condition, action = sys.argv[1:4]
    path = Path("program.bee")
    state = Path(".records")
    state.mkdir(exist_ok=True)
    source = path.read_text()
    code = 0
    if action == "note" and condition == "prose":
        out = TASKS[task]["prose"] + "\n"
    elif action == "source":
        out = source
    elif action in ("note", "apply"):
        command = [sys.executable, "-m", "b_lang.cli", "next", str(path)]
        if action == "apply":
            command.append("--apply")
        process = subprocess.run(command, capture_output=True, text=True)
        out, code = process.stdout + process.stderr, process.returncode
    elif action == "submit":
        attempt = 1 + len(list(state.glob("*.bee")))
        if attempt > 3:
            sys.exit("Submission limit reached")
        (state / f"{attempt}.bee").write_text(source)
        verdict = score(source, task, public=True)
        out = json.dumps(verdict) + "\n"
        code = int(not verdict["accepted"])
    else:
        sys.exit("Use note, source, apply or submit")
    with (state / "events.jsonl").open("a") as events:
        events.write(json.dumps({"action": action, "visible_bytes": len(out.encode()), "status": code}) + "\n")
    sys.stdout.write(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
