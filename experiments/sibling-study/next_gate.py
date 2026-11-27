#!/usr/bin/env python3
"""Solver-facing `./next` gate for Study B.

Advances a run to its next stage (grading the finished stage on the hidden oracle via
`harness.py advance`) but prints NOTHING about hidden-oracle results, so solvers gain no
information beyond what `./submit` already gives them. It refuses to advance unless the
current stage is finished under the preregistered rule: public tests ACCEPTED, or all
3 `./submit` attempts used. This is purely an orchestration convenience; the budget,
grading and metrics are identical to orchestrator-driven advancement.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

STUDY_DIR = Path(__file__).resolve().parent


def main() -> int:
    run_id = sys.argv[1]
    state = json.loads((STUDY_DIR / "state" / f"{run_id}.json").read_text(encoding="utf-8"))
    if state["completed"]:
        print("RUN COMPLETE. All stages are finished. Stop working.")
        return 0
    stage = state["current_stage"]
    rec = state["stages"][str(stage)]
    if not (rec["public_passed"] or len(rec["attempts"]) >= 3):
        print(f"REFUSED: stage {stage} is not finished. Run ./submit until ACCEPTED "
              f"(attempts used: {len(rec['attempts'])}/3).")
        return 1
    proc = subprocess.run([sys.executable, str(STUDY_DIR / "harness.py"), "advance", run_id],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print("ERROR: could not advance; report this to the orchestrator.")
        return 2
    state = json.loads((STUDY_DIR / "state" / f"{run_id}.json").read_text(encoding="utf-8"))
    if state["completed"]:
        print("RUN COMPLETE. All stages are finished. Stop working.")
    else:
        print(f"Stage {state['current_stage']} is ready. Re-read STAGE.md and edit your existing source file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
