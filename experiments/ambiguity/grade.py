"""Count wrong totals: python grade.py CHANGE WORKSPACE (change 0 is the build)."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle import bookings, expected

change, workspace = int(sys.argv[1]), Path(sys.argv[2]).resolve()
run = ["b", "run", "price.bee"] if (workspace / "price.bee").exists() else [sys.executable, "price.py"]
done = subprocess.run(run, input=json.dumps({"bookings": bookings()}) + "\n", capture_output=True, text=True,
                      cwd=workspace, timeout=120)
try:
    actual = json.loads([l for l in done.stdout.splitlines() if l.strip()][-1])["totals"]
except Exception:
    actual = {}
want = expected(change)
wrong = sorted(k for k in want if actual.get(k) != want[k])
print(json.dumps({"change": change, "wrong": len(wrong), "of": len(want), "examples": wrong[:6],
                  **({"stderr": done.stderr[-300:]} if not actual else {})}))
