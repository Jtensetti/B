"""Check proof/behavior agreement on two independent fixed programs and their edits."""
import json
from dataclasses import dataclass
from typing import Callable

from b_lang.compiler import compile_b
from b_lang.runtime import BContractError


@dataclass(frozen=True)
class Case:
    domain: str
    producer: str
    consumers: str
    law: str
    correct: str
    broken: str
    benign: str
    inputs: range
    expected: Callable[[int], int | float]


CASES = (
    Case(
        "microscopy",
        "fn samples(frames: Int) -> Int pure requires frames >= 0 ensures result >= 0",
        "fn readout(frames: Int) -> Float pure requires frames >= 0 = if frames > 0 then 60 / samples(frames) else 0.0",
        "(frames <= 0 or result > 0)",
        "if frames > 0 then frames + 2 else 0",
        "if frames == 1 then 0 else if frames > 0 then frames + 2 else 0",
        "if frames == 0 then 0 else 2 + frames",
        range(0, 8), lambda n: 60 / (n + 2) if n else 0.0,
    ),
    Case(
        "print-layout",
        "fn margin(edge: Int) -> Int pure ensures result <= 8",
        "fn inset(width: Int) -> Int pure requires width <= 3 = 50 + width\n"
        "fn readout(edge: Int) -> Int pure = if edge < 0 then inset(margin(edge)) else 80",
        "(edge >= 0 or result <= 3)",
        "if edge < 0 then 3 else 8",
        "if edge == -1 then 4 else if edge < 0 then 3 else 8",
        "if edge >= 0 then 8 else 3",
        range(-4, 5), lambda n: 53 if n < 0 else 80,
    ),
)


def compare(case: Case, variant: str, body: str, declare_law: bool, use_laws: bool) -> dict:
    spec = f"{case.producer} and {case.law}" if declare_law else case.producer
    program = compile_b(f"{spec} = {body}\n{case.consumers}", conditional_guarantees=use_laws)
    ns = {}
    exec(program.code, ns)
    failures = []
    for arg in case.inputs:
        try:
            result = ns["readout"](arg)
        except (BContractError, ZeroDivisionError):
            failures.append(arg)
        else:
            if type(result) is not type(case.expected(arg)) or result != case.expected(arg):
                failures.append(arg)
    relevant = [o for o in program.analysis.obligations if o.caller == "readout"
                and (o.kind == "nonzero" or o.target == "inset")]
    if len(relevant) != 1:
        raise AssertionError(f"Expected one consumer obligation, got {relevant}")
    return {"domain": case.domain, "variant": variant, "conditional_guarantees": use_laws,
            "consumer_status": relevant[0].status, "total_cases": len(case.inputs),
            "failing_inputs": failures}


def main() -> None:
    for case in CASES:
        for variant, body, declared in (
            ("original", case.correct, True),
            ("equivalent-edit", case.benign, True),
            ("withdrawn-law", case.correct, False),
            ("defect", case.broken, True),
        ):
            for enabled in (False, True):
                print(json.dumps(compare(case, variant, body, declared, enabled)))


if __name__ == "__main__":
    main()
