"""Snapshot one finished step and reveal the next change. The controller owns state."""
import shutil
import sys
import tempfile
from pathlib import Path

END = "END. The trial is over. Reply DONE."


def advance(state: Path, ws: Path) -> str:
    root = state / "snapshots" / ws.name
    root.mkdir(parents=True, exist_ok=True)
    # Published snapshots are the counter, including after a controller restart.
    step = 0
    while (root / f"step{step}").exists():
        step += 1
    if step and not (state / "steps" / f"change{step}.md").is_file():
        return END
    with tempfile.TemporaryDirectory(dir=root) as staging:
        snapshot = Path(staging) / "workspace"
        shutil.copytree(ws, snapshot, symlinks=True,
                        ignore=shutil.ignore_patterns("node_modules", "target", "obj", "__pycache__", ".git"))
        snapshot.rename(root / f"step{step}")
    progress = state / "progress" / ws.name
    progress.parent.mkdir(parents=True, exist_ok=True)
    progress.write_text(str(step + 1))
    change = state / "steps" / f"change{step + 1}.md"
    return change.read_text() if change.exists() else END


if __name__ == "__main__":
    print(advance(Path(sys.argv[1]), Path(sys.argv[2]).resolve()))
