"""Time a new CLI process and repeated file reads with each policy loaded once."""
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

from check import findings, load_policy, read_cues

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "lecture.vtt"
ENGINES = ("b", "python")


def measure(samples=11, repeated_files=100):
    cold = {lang: [] for lang in ENGINES}
    warm = {lang: [] for lang in ENGINES}
    expected = None
    for round_index in range(samples + 1):
        order = ENGINES if round_index % 2 == 0 else reversed(ENGINES)
        for lang in order:
            start = perf_counter_ns()
            proc = subprocess.run(
                [sys.executable, str(HERE / "check.py"), str(SAMPLE), "--engine", lang],
                capture_output=True, check=False,
            )
            elapsed = perf_counter_ns() - start
            assert proc.returncode == 1 and not proc.stderr, proc.stderr
            if expected is None:
                expected = proc.stdout
            assert proc.stdout == expected
            if round_index:
                cold[lang].append(elapsed / 1_000_000)

    policies = {lang: load_policy(lang, 2) for lang in ENGINES}
    for round_index in range(samples + 1):
        order = ENGINES if round_index % 2 == 0 else reversed(ENGINES)
        for lang in order:
            start = perf_counter_ns()
            for _ in range(repeated_files):
                text = SAMPLE.read_text(encoding="utf-8")
                rows = list(findings(read_cues(text), policies[lang]))
            elapsed = perf_counter_ns() - start
            assert len(rows) == len(expected.splitlines())
            if round_index:
                warm[lang].append(elapsed / repeated_files / 1_000_000)
    return {lang: {"new_process_ms": round(median(cold[lang]), 3),
                   "loaded_policy_file_ms": round(median(warm[lang]), 3)} for lang in ENGINES}


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
