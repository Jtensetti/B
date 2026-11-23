"""Count wrong quotes: python grade.py CHANGE WORKSPACE (change 0 is the build).

A quote is wrong if it is missing, or differs from the owner's intent by more than 0.02 kr
(the library rounds before or after VAT depending on its version). An order listed as unknown
when it should be quoted, or the reverse, counts as wrong.
"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import CATALOG, orders, expected

change, workspace = int(sys.argv[1]), Path(sys.argv[2]).resolve()
run = ["b", "run", "quote.bee"] if (workspace / "quote.bee").exists() else [sys.executable, "quote.py"]
line = json.dumps({"orders": orders(), "catalog": CATALOG}) + "\n"
done = subprocess.run(run, input=line, capture_output=True, text=True, cwd=workspace, timeout=120)
try:
    actual = json.loads([l for l in done.stdout.splitlines() if l.strip()][-1])
except Exception:
    actual = {}
want = expected(change)
got_q, got_u = actual.get("quotes") or {}, set(actual.get("unknown") or [])
wrong = []
for o in orders():
    k = o["id"]
    if k in want["quotes"]:
        v = got_q.get(k)
        if not isinstance(v, (int, float)) or abs(v - want["quotes"][k]) > 0.02 or k in got_u:
            wrong.append(k)
    elif k not in got_u or k in got_q:
        wrong.append(k)
print(json.dumps({"change": change, "wrong": len(wrong), "of": len(orders()), "examples": wrong[:6],
                  **({"stderr": done.stderr[-300:]} if not actual else {})}))
