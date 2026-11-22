"""Re-run every captured submission, including wrong edits that pass the public checks."""
import json
from pathlib import Path

from submit import assess

HERE = Path(__file__).resolve().parent


def replay():
    runs = json.loads((HERE / "results.json").read_text())
    for run in runs:
        first_pass = None
        for number, attempt in enumerate(run["attempts"], 1):
            payload = (HERE / "submissions" / attempt["file"]).read_text()
            for public, key in ((True, "public"), (False, "independent")):
                actual = assess(run["task"], run["arm"], attempt["register"], payload, public)
                assert actual == attempt[key], (run["id"], number, key, actual)
                if not public and actual["accepted"] and first_pass is None:
                    first_pass = number
        assert first_pass == run["first_accepted"], run["id"]
        print(f'{run["id"]}: {run["task"]}, {run["arm"]}, first acceptance {first_pass}')

    dispatch = (
        "next bell when slot == 2 => 70\nnext lamp when zone == 5 => 4\n"
        'next label when lane == 0 => "late #2"\nnext weight when compartment == 2 => 14\n'
    )
    window = "next readout when tick >= 2 and tick <= 5 => 20 - tick\n"
    for task, payload, expected_score in (("dispatch", dispatch, 39), ("window", window, 38)):
        assert assess(task, "ordinary", "b", payload, True)["accepted"]
        result = assess(task, "ordinary", "b", payload, False)
        assert not result["accepted"] and result["passed"] == expected_score, task
        print(f'{task}, deliberate omission: public pass, independent {result["passed"]}/{result["total"]}')
    partial = 'bell 2 70\nlamp 5 4\nlabel 0 "late #2"\nweight 2 14\n'
    unresolved = assess("dispatch", "optional", "short", partial, public=True)
    assert "error" in unresolved and not unresolved["accepted"], unresolved
    print("Compact row with two possible parameters is rejected.")


if __name__ == "__main__":
    replay()
