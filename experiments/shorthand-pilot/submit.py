"""Apply a submission with the installed B tools and return the same public observations in each arm."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from score import score
from tasks import TASKS


def materialize(task, register, payload):
    if register == "full":
        return payload
    if register not in ("short", "b"):
        raise ValueError("Unknown submission format")
    with TemporaryDirectory() as work:
        source = Path(work) / "source.bee"
        source.write_text(TASKS[task]["source"] + (payload if register == "b" else ""))
        command = [sys.executable, "-m", "b_lang.cli", "next", str(source), "--apply", "--strict"]
        if register == "short":
            command.extend(["--from-short", "-"])
        status = subprocess.run(command, input=payload if register == "short" else "",
                                text=True, capture_output=True)
        if status.returncode:
            raise ValueError(status.stderr.strip() or status.stdout.strip())
        return source.read_text()


def assess(task, arm, register, payload, public):
    try:
        if arm == "ordinary" and register == "short":
            raise ValueError("Use b or full in this condition")
        return score(materialize(task, register, payload), task, public)
    except Exception as error:
        return {"accepted": False, "error": str(error)}


def main():
    task, arm, register, name = sys.argv[1:]
    state = Path(".attempts")
    state.mkdir(exist_ok=True)
    number = 1 + len(list(state.glob("*.json")))
    if number > 2:
        sys.exit("Submission limit reached")
    payload = Path(name).read_text()
    verdict = assess(task, arm, register, payload, public=True)
    out = (f"Public {'pass' if verdict['accepted'] else 'fail'}: {verdict['passed']}/{verdict['total']}"
           if "passed" in verdict else verdict["error"])
    if verdict.get("mismatches"):
        out += "\n" + "\n".join(verdict["mismatches"])
    if verdict.get("api") is False:
        out += "\nCheck function signatures, domains and pending instructions."
    out += "\n"
    (state / f"{number}.json").write_text(json.dumps(dict(register=register, payload=payload, feedback=out, public=verdict)))
    sys.stdout.write(out)
    return int(not verdict["accepted"])


if __name__ == "__main__":
    sys.exit(main())
