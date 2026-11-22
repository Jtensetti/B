"""Compare identifiable arithmetic conventions on a finite set of signed operands."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess

from b_lang.compiler import compile_b


def candidates(a: int, b: int) -> dict[str, int]:
    """Construct all three residues from a nonnegative magnitude and sign rules."""
    magnitude = abs(a) - abs(b) * (abs(a) // abs(b))
    truncated = -magnitude if a < 0 else magnitude
    floor = truncated + b if magnitude and (a < 0) != (b < 0) else truncated
    euclidean = truncated + abs(b) if truncated < 0 else truncated
    return {"floor": floor, "truncate": truncated, "euclidean": euclidean}


def csharp_outputs(cases: list[tuple[int, int]]) -> list[tuple[int, int]]:
    process = subprocess.run(
        ["dotnet", "run", "--file", str(Path(__file__).with_name("Remainder.cs").resolve())],
        input="".join(f"{a} {b}\n" for a, b in cases), text=True, capture_output=True,
        env={**os.environ, "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1"},
        check=True, timeout=120,
    )
    rows = [tuple(map(int, line.split())) for line in process.stdout.splitlines()]
    if len(rows) != len(cases) or any(len(row) != 2 for row in rows):
        raise ValueError("Unexpected output from C# probe")
    return rows


def discriminate(cases, observed):
    """Choose a probe that minimizes the largest surviving candidate group."""
    models = set(candidates(1, 1))
    probes = []
    while len(models) > 1:
        def worst_group(case):
            prediction = candidates(*case)
            outcomes = [prediction[model] for model in models]
            return max(outcomes.count(outcome) for outcome in outcomes)

        a, b = min(cases, key=lambda case: (worst_group(case), sum(map(abs, case)), case))
        if worst_group((a, b)) == len(models):
            break
        value = observed[(a, b)]
        probes.append([a, b, value])
        models = {rule for rule in models if candidates(a, b)[rule] == value}
    return {"queries": probes, "survivors": sorted(models)}


def main() -> None:
    cases = [(a, b) for a in range(-12, 13) for b in range(-6, 7) if b != 0]
    native = {}
    code = """
fn rem(a: Int, b: Int) -> Int pure requires b != 0 = a % b
fn sign(a: Int) -> Int pure = if a < 0 then -1 else (if a > 0 then 1 else 0)
"""
    exec(compile_b(code, strict=True).code, native)
    csharp = csharp_outputs(cases)
    observations = {
        "B": [(native["rem"](a, b), native["sign"](a)) for a, b in cases],
        "Python": [(a % b, (a > 0) - (a < 0)) for a, b in cases],
        "C#": csharp,
    }
    domains = {
        "positive only": [(a, b) for a, b in cases if a > 0 and b > 0],
        "positive plus two signed probes": [(a, b) for a, b in cases if a > 0 and b > 0]
                                           + [(-5, 4), (5, -4)],
        "signed grid": cases,
    }
    reports = {}
    for domain, samples in domains.items():
        sample_set = set(samples)
        rows = [(i, candidates(a, b)) for i, (a, b) in enumerate(cases) if (a, b) in sample_set]
        matches = {
            language: [rule for rule in ("floor", "truncate", "euclidean")
                       if all(results[i][0] == predictions[rule] for i, predictions in rows)]
            for language, results in observations.items()
        }
        reports[domain] = {
            "cases": len(rows),
            "remaining_remainder_models": matches,
            "same_remainder_B_and_Csharp": sum(observations["B"][i][0] == csharp[i][0] for i, _ in rows),
            "same_sign_all_three": sum(len({obs[i][1] for obs in observations.values()}) == 1 for i, _ in rows),
        }
    reports["automatically selected probes"] = {
        language: discriminate(cases, {case: row[0] for case, row in zip(cases, outputs, strict=True)})
        for language, outputs in observations.items()
    }
    # This operation uses a fourth, unlisted rule. Integers in the grid are
    # exactly representable in binary64. Compare the numerical remainder only.
    outside = {case: math.remainder(*case) for case in cases}
    identification = discriminate(cases, outside)
    probed = {(a, b) for a, b, _ in identification["queries"]}
    remaining = [case for case in cases if case not in probed]
    falsifications = {}
    for rule in identification["survivors"]:
        disagreements = [case for case in remaining if candidates(*case)[rule] != outside[case]]
        falsifications[rule] = {
            "held_out": len(remaining), "mismatches": len(disagreements),
            "first_mismatch": disagreements[0] if disagreements else None,
        }
    reports["unlisted rule (math.remainder)"] = {**identification, "validation": falsifications}
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
