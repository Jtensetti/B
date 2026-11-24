"""Count wrong invoices: python grade.py STEP WORKSPACE (0 = build, 1-8 = changes).

The program runs once per month (February and March 2026). Each customer in the input is one unit
per month: wrong if an invoice is missing or should not be there, or its currency differs, or net,
vat or total is off by more than 0.02.
"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import MONTHS, data, expected

step, workspace = int(sys.argv[1]), Path(sys.argv[2]).resolve()
run = ["b", "run", "main.bee"] if (workspace / "main.bee").exists() else [sys.executable, "main.py"]
wrong, units, errors = [], 0, []
for month in MONTHS:
    feed = data(step, month)
    done = subprocess.run(run, input=json.dumps(feed) + "\n", capture_output=True, text=True,
                          cwd=workspace, timeout=120)
    try:
        got = json.loads([l for l in done.stdout.splitlines() if l.strip()][-1])["invoices"]
    except Exception:
        got = None
        errors.append(done.stderr[-200:])
    want = expected(step, month)["invoices"]
    for c in feed["customers"]:
        units += 1
        k, g, w = c["id"], (got or {}).get(c["id"]), want.get(c["id"])
        if got is None:
            ok = False
        elif w is None or g is None:
            ok = w is None and g is None
        else:
            ok = g.get("currency") == w["currency"] and all(
                isinstance(g.get(f), (int, float)) and abs(g[f] - w[f]) <= 0.02 for f in ("net", "vat", "total"))
        if not ok:
            wrong.append(f"{month[5:]}:{k}")
print(json.dumps({"step": step, "wrong": len(wrong), "of": units, "examples": wrong[:8],
                  **({"stderr": errors[0]} if errors else {})}))
