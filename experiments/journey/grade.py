"""Grade a solver's program against the hidden fixtures for one step.

    python grade.py STEP WORKSPACE

The workspace holds either resolve.bee (run with `b run`) or resolve.py.
Each fixture is fed on one line to standard input; inputs for steps 1 and 2
carry no pins. Output is compared as parsed JSON: object key order is
ignored, list order is not.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def command(workspace: Path) -> list[str]:
    if (workspace / "resolve.bee").exists():
        return ["b", "run", "resolve.bee"]
    if (workspace / "resolve.py").exists():
        return [sys.executable, "resolve.py"]
    raise SystemExit(f"no resolve.bee or resolve.py in {workspace}")


def grade(step: int, workspace: Path) -> dict:
    fixtures = Path(os.environ.get("JOURNEY_FIXTURES", HERE / "fixtures"))
    expected = json.loads((fixtures / "_expected.json").read_text())
    run = command(workspace)
    failures, passed = [], 0
    for name, by_step in sorted(expected.items()):
        data = json.loads((fixtures / name).read_text())
        if step < 3:
            data.pop("pins", None)
        try:
            done = subprocess.run(run, input=json.dumps(data) + "\n", capture_output=True, text=True,
                                  cwd=workspace, timeout=60)
            lines = [line for line in done.stdout.splitlines() if line.strip()]
            actual = json.loads(lines[-1]) if lines else None
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            actual, done = None, None
            failures.append({"fixture": name, "error": type(exc).__name__})
            continue
        if actual == by_step[str(step)]:
            passed += 1
        else:
            failures.append({"fixture": name, "expected": by_step[str(step)], "actual": actual,
                             "stderr": (done.stderr or "")[-300:]})
    return {"step": step, "passed": passed, "total": len(expected), "failures": failures}


if __name__ == "__main__":
    result = grade(int(sys.argv[1]), Path(sys.argv[2]).resolve())
    print(json.dumps({k: v for k, v in result.items() if k != "failures"}))
    if "-v" in sys.argv:
        print(json.dumps(result["failures"], indent=1)[:4000])
