"""The solver's `next` command: snapshot the workspace for grading and print the next change.

Usage (by the trial driver, not the solver): python next.py STATE_DIR WORKSPACE
STATE_DIR holds steps/change<N>.md and the counter; snapshots go to STATE_DIR/snapshots/<workspace>/step<N>.
"""
import shutil
import sys
from pathlib import Path

state, ws = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
counter = state / "progress" / ws.name
counter.parent.mkdir(parents=True, exist_ok=True)
done = int(counter.read_text()) if counter.exists() else 0
target = state / "snapshots" / ws.name / f"step{done}"
if target.exists():
    shutil.rmtree(target)
shutil.copytree(ws, target, ignore=shutil.ignore_patterns("node_modules", "target", "bin", "obj", "__pycache__", ".git"))
counter.write_text(str(done + 1))
change = state / "steps" / f"change{done + 1}.md"
print(change.read_text() if change.exists() else "END. The trial is over. Reply DONE.")
