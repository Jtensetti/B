"""Seven booking programs, one request: "children ride free on Sundays".

Each program already admits children free on Saturday through `free_entry`.
The request is written as the same declaration, `also free_entry(true, "sun")`.
The script records whether `b ask` settles the meaning from the Saturday case,
which question it asks otherwise, and whether each offered answer compiles and
gives the stated total. Run from the repository root:

    python experiments/precedent-questions/check.py
"""
from __future__ import annotations

import json
import sys

from b_lang.ask import answer, ask
from b_lang.compiler import compile_b
from b_lang.types import BError

RULE = 'fn free_entry(child: Bool, day: Text) -> Bool pure = child and day == "sat"\n'
TICKET = 'fn ticket(child: Bool, day: Text) -> Int pure = if free_entry(child, day) then 0 else 100\n'
REQUEST = 'also free_entry(true, "sun")\n'


def booking(fee: str, total: str = "ticket(child, day) + fee(child, day)", extra: str = "") -> str:
    return (RULE + TICKET + extra + f"fn fee(child: Bool, day: Text) -> Int pure = {fee}\n"
            + f"fn total(child: Bool, day: Text) -> Int pure = {total}\n")


VARIANTS = {
    "A repeated Saturday waiver": booking('if child and day == "sat" then 0 else 10'),
    "B flat booking fee": booking("10"),
    "C waiver calls the rule": booking("if free_entry(child, day) then 0 else 10"),
    "D waiver already covers the weekend": booking('if child and (day == "sat" or day == "sun") then 0 else 10'),
    "E Sunday surcharge": booking("10", "ticket(child, day) + fee(child, day) + surcharge(day)",
                                  'fn surcharge(day: Text) -> Int pure = if day == "sun" then 20 else 0\n'),
    "F Saturday souvenir": booking("10", extra='fn souvenir(child: Bool, day: Text) -> Text pure = '
                                              'if day == "sat" then "pin" else "none"\n'),
    "G rule never true before": booking("10").replace('child and day == "sat"', "false"),
}


def total(source: str, child: bool, day: str):
    names = {}
    exec(compile_b(source).code, names)
    return names["total"](child, day)


def study() -> list[dict]:
    rows = []
    for label, source in VARIANTS.items():
        program = source + REQUEST
        entry, = ask(program)["declarations"]
        row = {"variant": label, "status": entry["status"],
               "sunday_total_after_rule_only": total(program, True, "sun"),
               "saturday_total": total(program, True, "sat")}
        if entry["status"] == "question":
            row["question"] = entry["question"]
            row["answers"] = {}
            for option in entry["options"]:
                try:
                    texts = answer(ask(program), option["value"])
                    revised = texts["file"]
                    row["answers"][json.dumps(option["value"])] = {
                        "declaration": option["declaration"],
                        "repairs": [f"{r['function']}: {r['replace']} -> {r['with']}" for r in option["repairs"]],
                        "sunday_total": total(revised, True, "sun"),
                        "follow_up": ask(revised)["declarations"][0]["status"],
                    }
                except BError as exc:
                    row["answers"][json.dumps(option["value"])] = {"declaration": option["declaration"],
                                                                   "refused": exc.message}
        elif entry["status"] == "settled":
            row["recorded_as"] = entry["suggestion"]
            row["recorded_compiles_strict"] = bool(compile_b(program.replace(REQUEST, entry["suggestion"] + "\n"),
                                                             strict=True))
        rows.append(row)
    return rows


if __name__ == "__main__":
    json.dump(study(), sys.stdout, indent=2, ensure_ascii=False)
    print()
