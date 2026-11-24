"""Grade every snapshot of a trial and measure each solver's work.

Usage: python grade_all.py TASK RUN_DIR AGENTS_JSON TASKS_DIR
RUN_DIR holds state/snapshots/<solver>/step<N>; AGENTS_JSON maps solver -> agent id; TASKS_DIR holds
<agent id>.output transcripts. Writes results.json next to AGENTS_JSON and prints a summary table.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grade import grade  # noqa: E402
from checks import CHECK, check
from transcripts import measure

task, run_dir, agents_file, tasks_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
agents = json.loads(agents_file.read_text())


def output_tokens(agent: str) -> int:
    total = 0
    for line in (tasks_dir / f"{agent}.output").read_text().splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "assistant":
            total += ((d.get("message") or {}).get("usage") or {}).get("output_tokens", 0)
    return total


if task == "task-c":
    if set(agents) != {f"{lang}{n}" for lang in CHECK for n in range(1, 4)} or len(set(agents.values())) != 18:
        raise SystemExit("C requires all 18 distinct transcripts")
    for solver, agent in agents.items():
        snaps = run_dir / "state" / "snapshots" / solver
        if {p.name for p in snaps.glob("step*")} != {f"step{n}" for n in range(6)}:
            raise SystemExit(f"{solver}: expected six snapshots")
        measure(tasks_dir / f"{agent}.output")

results = {}
for solver, agent in sorted(agents.items()):
    steps = {}
    snaps = run_dir / "state" / "snapshots" / solver
    cargo_target = Path(tempfile.gettempdir()) / f"bgrade-target-{task}-{solver}"
    os.environ["CARGO_TARGET_DIR"] = str(cargo_target)
    for snap in sorted(snaps.glob("step*"), key=lambda p: int(p.name[4:])):
        work = Path(tempfile.mkdtemp(prefix=f"bgrade-{solver}-"))
        ws = work / solver
        shutil.copytree(snap, ws)
        # Fresh timestamps: copied sources keep their old mtimes, and cargo then reuses the previous step's
        # build from the shared target directory. Touching every file forces each step to be rebuilt.
        for f in ws.rglob("*"):
            if f.is_file():
                os.utime(f)
        if (run_dir / solver / "node_modules").exists():
            shutil.copytree(run_dir / solver / "node_modules", ws / "node_modules")
        # The stepper skipped every directory named bin, meant for C# build output. A solver that built
        # its own bridge binaries into <workspace>/bin gets them back from the live workspace.
        if task != "task-c" and (run_dir / solver / "bin").is_dir() and not (ws / "bin").exists():
            shutil.copytree(run_dir / solver / "bin", ws / "bin")
        step = int(snap.name[4:])
        if task == "task-c":
            language = solver[:-1]
            # Keep per-snapshot static output alongside the registered runtime score.
            # A separate copy prevents compiler artifacts from influencing the hidden-fixture run.
            static_ws = work / "check"
            shutil.copytree(ws, static_ws, symlinks=True)
            os.environ["CARGO_TARGET_DIR"] = str(work / "static-target")
            static = check(language, static_ws)
            os.environ["CARGO_TARGET_DIR"] = str(work / "runtime-target")
            steps[step] = {**grade(task, step, ws, language), "static_check": static}
        else:
            steps[step] = grade(task, step, ws)
        shutil.rmtree(work, ignore_errors=True)
    results[solver] = {"steps": steps, "wrong": sum(s["wrong"] for s in steps.values()),
                       "units": sum(s["of"] for s in steps.values()), "output_tokens": output_tokens(agent)}
    if task == "task-c":
        results[solver].update(measure(tasks_dir / f"{agent}.output"))
        if results[solver]["units"] != 144:
            raise SystemExit(f"{solver}: expected 144 units")
    print(solver, results[solver]["wrong"], "/", results[solver]["units"], "tokens", results[solver]["output_tokens"],
          {k: v["wrong"] for k, v in steps.items()}, flush=True)
(agents_file.parent / "results.json").write_text(json.dumps(results, indent=1))
