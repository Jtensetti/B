"""Grade a solver's release program against the hidden fixtures for one step.

    JOURNEY_FIXTURES=dir python grade.py STEP WORKSPACE [-v]

Inputs for steps 1-2 carry no today or stale_days, and steps 1-3 no watch. Numbers may differ by less than
0.001 (floating point noise); everything else must match exactly.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 0.001
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def grade(step: int, workspace: Path) -> dict:
    fixtures = Path(os.environ.get("JOURNEY_FIXTURES", HERE / "fixtures"))
    expected = json.loads((fixtures / "_expected.json").read_text())
    run = ["b", "run", "report.bee"] if (workspace / "report.bee").exists() else [sys.executable, "report.py"]
    passed, failures = 0, []
    for name, by_step in sorted(expected.items()):
        data = json.loads((fixtures / name).read_text())
        if step < 3:
            data.pop("today", None)
            data.pop("stale_days", None)
        if step < 4:
            data.pop("watch", None)
        try:
            done = subprocess.run(run, input=json.dumps(data) + "\n", capture_output=True, text=True,
                                  cwd=workspace, timeout=60)
            lines = [line for line in done.stdout.splitlines() if line.strip()]
            actual = json.loads(lines[-1]) if lines else None
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            failures.append({"fixture": name, "error": type(exc).__name__})
            continue
        if same(actual, by_step[str(step)]):
            passed += 1
        else:
            failures.append({"fixture": name, "expected": by_step[str(step)], "actual": actual,
                             "stderr": done.stderr[-300:]})
    return {"step": step, "passed": passed, "total": len(expected), "failures": failures}


if __name__ == "__main__":
    result = grade(int(sys.argv[1]), Path(sys.argv[2]).resolve())
    print(json.dumps({k: v for k, v in result.items() if k != "failures"}))
    if "-v" in sys.argv:
        print(json.dumps(result["failures"], indent=1)[:4000])
