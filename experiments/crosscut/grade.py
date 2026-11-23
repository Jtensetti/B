"""Count wrong outputs: python grade.py STEP WORKSPACE (step 0 is the inherited program).

Units graded: each of the 16 invoices (wrong if its currency differs, a VAT class is missing or extra,
or any amount is off by more than 0.02) and each of the 4 report fields (net_by_class counts as one).
"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import data, expected

step, workspace = int(sys.argv[1]), Path(sys.argv[2]).resolve()
run = ["b", "run", "main.bee"] if (workspace / "main.bee").exists() else [sys.executable, "main.py"]
done = subprocess.run(run, input=json.dumps(data()) + "\n", capture_output=True, text=True, cwd=workspace, timeout=120)
try:
    actual = json.loads([l for l in done.stdout.splitlines() if l.strip()][-1])
except Exception:
    actual = {}
want = expected(step)


def close(a, b):
    if isinstance(b, dict):
        return isinstance(a, dict) and set(a) == set(b) and all(close(a[k], b[k]) for k in b)
    if isinstance(b, str):
        return a == b
    return isinstance(a, (int, float)) and not isinstance(a, bool) and abs(a - b) <= 0.02


got_i, got_r = actual.get("invoices") or {}, actual.get("report") or {}
wrong = [k for k in want["invoices"] if not close(got_i.get(k), want["invoices"][k])]
wrong += [f"report.{k}" for k in want["report"] if not close(got_r.get(k), want["report"][k])]
print(json.dumps({"step": step, "wrong": len(wrong), "of": len(want["invoices"]) + len(want["report"]),
                  "examples": wrong[:6], **({"stderr": done.stderr[-300:]} if not actual else {})}))
