"""Check frozen submissions, both readings of the ambiguous rule, and the file-level tool."""
from collections import Counter
import json
from pathlib import Path
from subprocess import run
from sys import executable
from tempfile import TemporaryDirectory

from check import findings, load_policy, read_cues
from oracle import boundary_cases
from protocol import PUBLIC

ROOT = Path(__file__).resolve().parent
EXPECTED = "16\tthird\toverlap\n20\tnested\toverlap\n24\treversed\tbad-time\n30\tbrief-effect\tbrief\n"


def shared_time_answer(args, expected):
    """Post-trial alternative meaning; duration controls only the speech-to-speech tolerance."""
    start, end, prior_speech_end, prior_effect_end, words, effect = args
    if (expected != "overlap" or effect or prior_effect_end > start
            or start >= min(end, prior_speech_end)):
        return expected
    if len(range(start, min(end, prior_speech_end))) > 80:
        return expected
    return "brief" if end - start < (550 if words in (1, 2) else 1000) else "ok"


def inspect_candidate(engine, revision, first):
    suffix = {"b": "bee", "python": "py"}[engine]
    location = ROOT / "first-submit" / f"rev{revision}.{suffix}" if first else None
    classify = load_policy(engine, revision, location)
    scores = Counter()
    for args, expected in boundary_cases(revision):
        output = classify(*args)
        scores["cases"] += 1
        scores["frozen"] += output == expected
        if revision == 2:
            scores["shared time"] += output == shared_time_answer(args, expected)
    if revision:
        assert all(classify(*args) == expected for args, expected in PUBLIC[revision])
    counts = dict(scores)
    assert counts["cases"] == 6144
    assert counts["frozen"] == (6120 if first else 6144), counts
    if revision == 2:
        assert counts["shared time"] == (6144 if first else 6120), counts
    print(engine, revision, "first submission" if first else "released", counts)


def cli(engine, path, *args):
    return run([executable, str(ROOT / "check.py"), str(path), "--engine", engine, *args],
               capture_output=True, text=True, check=False)


def integration(engine):
    for revision, want in [(0, "8\treply\toverlap\n12\tkey\tbrief\n" + EXPECTED),
                           (1, "8\treply\toverlap\n" + EXPECTED),
                           (2, EXPECTED)]:
        outcome = cli(engine, ROOT / "lecture.vtt", "--revision", str(revision))
        assert (outcome.returncode, outcome.stdout, outcome.stderr) == (1, want, ""), outcome
    classify = load_policy(engine, 2)
    # The long first cue survives an embedded/reversed cue, grouped by kind.
    stream = ("\ufeffWEBVTT\r\n\r\nNOTE skip these\r\nnotes\r\n\r\n"
              "a\r\n00:00:00.000 --> 00:00:02.000\r\n<i>Nu kör vi.</i>\r\n\r\n"
              "00:00.500 --> 00:00.499\r\n[invalid]\r\n\r\n"
              "00:01.500 --> 00:02.100\r\nHej\r\nigen.\r\n")
    assert [issue for _, issue in findings(read_cues(stream), classify)] == ["bad-time", "overlap"]
    with TemporaryDirectory() as temp:
        path = Path(temp) / "sample.vtt"
        path.write_text("WEBVTT\n\n00:00.000 --> 00:00.550\nHej!\n")
        clean = cli(engine, path)
        assert (clean.returncode, clean.stdout, clean.stderr) == (0, "", "")
        path.write_text("WEBVTT\n\n00:00.000 -> 00:00.550\nHej!\n")
        bad = cli(engine, path)
        assert (bad.returncode, bool(bad.stderr), bad.stdout) == (2, True, "")
    print(engine, "file input and status checks passed")


def clarification():
    command = [executable, "-m", "b_lang.cli", "clarify", str(ROOT / "overlap.bee"),
               str(ROOT / "overlap.json"), "--json"]
    def result(extra):
        response = run(command + extra, check=True, capture_output=True, text=True)
        return json.loads(response.stdout)
    question = result([])["question"]
    assert (question["inputs"], question["result"]) == ({"lead": 81, "duration": 1}, 0)
    for allowed, expected in [(True, "shared_time"), (False, "early_start")]:
        answer = {"inputs": question["inputs"], "result": question["result"], "allowed": allowed}
        decision = result(["--answer", json.dumps(answer)])
        assert decision["status"] == "selected" and decision["survivors"] == [expected]
    print("One concrete owner answer separates the two supplied speech timing policies.")


if __name__ == "__main__":
    clarification()
    for engine in ("b", "python"):
        for revision in range(3):
            inspect_candidate(engine, revision, False)
        inspect_candidate(engine, 2, True)
        integration(engine)
