"""Apply each code-derived candidate to its own starter and score it against independent intent."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from score import score


def main():
    root = Path(__file__).resolve().parent
    for task, name in (("ledger", "balance"), ("spacing", "gap")):
        starter = root / task / "program.bee"
        command = [sys.executable, "-m", "b_lang.cli", "discover", str(starter), "--function", name, "--json"]
        report = json.loads(subprocess.check_output(command))
        clause = report["proposed_contract"]
        if not clause:
            raise ValueError(f"{task}: discovery returned no contract: {report}")
        source = starter.read_text().replace(" = ", f" {clause} = ", 1)
        with tempfile.TemporaryDirectory() as work:
            candidate = Path(work) / "candidate.bee"
            candidate.write_text(source)
            row = {"task": task, "candidate": clause, "observation_status": report["status"],
                   "discovery_verification": report["verification"]["status"],
                   **score(candidate, task)}
            print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
