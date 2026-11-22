"""Rescore submitted B programs and independently exercise literal materialization."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from score import score
from tasks import TASKS


def replay():
    directory = Path(__file__).resolve().parent
    for run in json.loads((directory / "results.json").read_text()):
        first_accepted = None
        for number, attempt in enumerate(run["attempts"], 1):
            source = (directory / "submissions" / attempt["file"]).read_text()
            for public, key in ((True, "public"), (False, "independent")):
                outcome = score(source, run["task"], public)
                assert [outcome["passed"], outcome["total"], outcome["accepted"]] == attempt[key], run["id"]
            if outcome["accepted"] and first_accepted is None:
                first_accepted = number
        assert first_accepted == run["first_accepted"], run["id"]
        print(f'{run["id"]}: first accepted submission {first_accepted}')
    with TemporaryDirectory() as temp:
        for task, fixture in TASKS.items():
            path = Path(temp) / "example.bee"
            path.write_text(fixture["starter"] + fixture["directive"] + "\n")
            cmd = [sys.executable, "-m", "b_lang.cli", "next", str(path)]
            assert subprocess.check_output(cmd, text=True).strip() == fixture["directive"]
            subprocess.run([*cmd, "--apply"], check=True)
            output = path.read_text()
            assert not subprocess.check_output(cmd, text=True)
            assert score(output, task, public=True)["accepted"]
            result = score(output, task)
            expected_failures = [] if task == "shade" else [
                {"function": "signal", "args": (0, 3), "expected": 13, "actual": 8}
            ]
            assert result["failures"] == expected_failures
            assert result["accepted"] == (task == "shade")
            print(f'{task} as written: {result["passed"]}/{result["total"]}')


if __name__ == "__main__":
    replay()
