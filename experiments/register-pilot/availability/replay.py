"""Check the four later runs using the ordinary-language gate and unchanged scorer."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ordinary import ordinary_score
from score import score


ROOT = Path(__file__).resolve().parent


def replay():
    runs = json.loads((ROOT / "results.json").read_text())
    for run in runs:
        attempts = run["attempts"]
        accepted = None
        for index, attempt in enumerate(attempts, 1):
            source = ROOT / attempt["source"]
            assert len(source.read_bytes()) == attempt["source_bytes"], source
            public = ordinary_score(source, run["task"], public=True)
            independent = ordinary_score(source, run["task"])
            assert public["passed"] == attempt["public_passed"], source
            assert independent["accepted"] == attempt["independent_accepted"], source
            assert independent["passed"] == attempt["independent_passed"], source
            assert independent["cases"] == attempt["independent_cases"], source
            if independent["accepted"] and accepted is None:
                accepted = index
        assert accepted == run["first_accepted_submission"], run["run"]
        assert len(attempts) == run["submit_calls"], run["run"]
        print(f'{run["run"]}: {run["task"]}, first accepted submission {accepted}')

    table = ROOT.parent / "submissions" / "routing-1.bee"
    assert score(table, "routing", public=True)["accepted"]
    assert "error" in ordinary_score(table, "routing", public=True)
    with TemporaryDirectory() as temp:
        candidate = Path(temp) / "mentions-cases.bee"
        arithmetic = (ROOT.parent / "submissions" / "sampler-1.bee").read_text()
        candidate.write_text(arithmetic.replace("pulse", "cases"))
        assert ordinary_score(candidate, "sampler")["accepted"]
    print("Register gate rejects a valid decision table and accepts the same word as a name.")


if __name__ == "__main__":
    replay()
