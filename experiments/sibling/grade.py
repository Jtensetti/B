"""Grade one snapshot of a solver's workspace: python grade.py TASK STEP WORKSPACE.

The program is run the way its language is run, on the task's hidden input for that step. Each order is
one unit. A quote is wrong if it is missing, the order is wrongly listed as unknown, its delivery date or
currency differs, or its price is off by more than 0.02. An unknown order is wrong unless it is listed
as unknown and has no quote. A program that does not build or run scores every unit wrong.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def command(ws: Path):
    if (ws / "main.bee").exists():
        return ["b", "run", "main.bee"]
    if (ws / "main.py").exists():
        return [sys.executable, "main.py"]
    if (ws / "main.ts").exists():
        return ["node", "main.ts"]
    if (ws / "go.mod").exists() and (ws / "main.go").exists():
        return ["go", "run", "."]
    if (ws / "Cargo.toml").exists():
        return ["cargo", "run", "-q", "--release"]
    if list(ws.glob("app/*.csproj")):
        return ["dotnet", "run", "-c", "Release", "--project", str(next(ws.glob("app/*.csproj")))]
    raise SystemExit(f"no program found in {ws}")


def grade(task: str, step: int, ws: Path, language: str | None = None) -> dict:
    spec = importlib.util.spec_from_file_location("oracle", HERE / task / "oracle.py")
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    if hasattr(oracle, "TODAYS"):
        got_by_day, errors = {}, []
        for today in oracle.TODAYS:
            done = None
            try:
                from checks import RUN
                done = subprocess.run(RUN[language] if language else command(ws), input=json.dumps(oracle.data(step, today)) + "\n",
                                      capture_output=True, text=True, cwd=ws, timeout=600)
                done.check_returncode()
                got = json.loads([line for line in done.stdout.splitlines() if line.strip()][-1])
                if not isinstance(got, dict) or not isinstance(got.get("orders", {}), dict):
                    raise ValueError("expected an orders object")
                unknown = got.get("unknown", [])
                if not isinstance(unknown, list) or any(not isinstance(s, str) for s in unknown):
                    raise ValueError("expected unknown to be a list of SKUs")
                got_by_day[today] = got
            except Exception as exc:  # noqa: BLE001
                got_by_day[today] = None
                errors.append(f"{exc} {getattr(locals().get('done'), 'stderr', '')}"[-300:])
        wrong, units = oracle.grade(step, got_by_day)
        return {"task": task, "step": step, "wrong": len(wrong), "of": units, "examples": wrong[:6],
                **({"error": errors[0]} if errors else {})}
    feed = oracle.data(step)
    want = oracle.expected(step)
    try:
        done = subprocess.run(command(ws), input=json.dumps(feed) + "\n", capture_output=True, text=True,
                              cwd=ws, timeout=600)
        got = json.loads([l for l in done.stdout.splitlines() if l.strip()][-1])
        err = ""
    except Exception as exc:  # noqa: BLE001 - any failure to run counts against the program
        got, err = None, f"{exc} {getattr(locals().get('done'), 'stderr', '')}"[-300:]
    if hasattr(oracle, "grade"):
        wrong, units = oracle.grade(step, got)
        return {"task": task, "step": step, "wrong": len(wrong), "of": units, "examples": wrong[:6],
                **({"error": err} if got is None else {})}
    quotes = (got or {}).get("quotes") or {}
    unknown = set((got or {}).get("unknown") or [])
    wrong = []
    for o in feed["orders"]:
        k, w, g = o["id"], want["quotes"].get(o["id"]), quotes.get(o["id"])
        if got is None:
            ok = False
        elif w is None:
            ok = k in unknown and g is None
        else:
            ok = (isinstance(g, dict) and k not in unknown and g.get("delivery") == w["delivery"]
                  and g.get("currency", w.get("currency")) == w.get("currency")
                  and ("currency" not in w or "currency" in g)
                  and isinstance(g.get("price"), (int, float)) and abs(g["price"] - w["price"]) <= 0.02)
        if not ok:
            wrong.append(k)
    return {"task": task, "step": step, "wrong": len(wrong), "of": len(feed["orders"]), "examples": wrong[:6],
            **({"error": err} if got is None else {})}


if __name__ == "__main__":
    print(json.dumps(grade(sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]).resolve())))
