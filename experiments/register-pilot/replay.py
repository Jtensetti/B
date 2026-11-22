"""Recheck the run records, paired starters, and two hidden-score controls."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from b_lang.compiler import compile_b
from score import score


PILOT = Path(__file__).resolve().parent


def replay():
    for task in ("routing", "sampler"):
        programs = [compile_b((PILOT / task / f"{starter}.bee").read_text())
                    for starter in ("conditional", "table")]
        assert programs[0].ir.to_dict() == programs[1].ir.to_dict(), task

    for run in json.loads((PILOT / "results.json").read_text()):
        accepted = None
        for index, attempt in enumerate(run["attempts"], 1):
            source = PILOT / "submissions" / attempt["source"]
            public = score(source, run["task"], public=True)
            independent = score(source, run["task"])
            assert len(source.read_bytes()) == attempt["source_bytes"], source
            assert public["passed"] == attempt["public_passed"], source
            assert independent["passed"] == attempt["independent_passed"], source
            assert independent["cases"] == attempt["independent_cases"], source
            assert independent["accepted"] == attempt["independent_accepted"], source
            if independent["accepted"] and accepted is None:
                accepted = index
        assert len(run["attempts"]) == run["submit_calls"], run["run"]
        assert accepted == run["first_accepted_submission"], run["run"]
        print(f'{run["run"]}: {run["task"]}, first accepted submission {accepted}')

    controls = [
        ("routing", "== 31 => 7;", "", 43),
        ("sampler", "gain - 1", "(gain - 1) % 2", 61),
    ]
    with TemporaryDirectory() as temp:
        candidate = Path(temp) / "control.bee"
        for task, original, replacement, expected_passes in controls:
            correct = (PILOT / "submissions" / f"{task}-1.bee").read_text()
            assert correct.count(original) == 1, original
            candidate.write_text(correct.replace(original, replacement))
            assert score(candidate, task, public=True)["accepted"], task
            full = score(candidate, task)
            assert not full["accepted"] and full["passed"] == expected_passes, task
            print(f'{task} omission: public pass, independent {full["passed"]}/{full["cases"]}')


if __name__ == "__main__":
    replay()
