"""Score the submitted B and Python functions against independently constructed records."""
from itertools import product
from pathlib import Path
import runpy

from b_lang.compiler import compile_b


HERE = Path(__file__).resolve().parent


def reference(records, allowance):
    complete = [row["gross"] - row["tare"] for row in records if {"gross", "tare"} <= row.keys()]
    excess = [net - allowance for net in complete if net > allowance]
    return {"weighed": len(records), "incomplete": len(records) - len(complete),
            "over": len(excess), "extra": sum(excess)}


def cases():
    rows = [{}, {"tare": 0}, {"gross": 8}, {"tag": 3}, {"gross": -2, "tare": -4},
            {"gross": 0, "tare": 0, "tag": 9}, {"gross": 9, "tare": 5},
            {"gross": 2**100, "tare": -1}]
    for width in range(4):
        for sequence in product(rows, repeat=width):
            for allowance in (-3, 0, 2, 4):
                yield list(sequence), allowance


if __name__ == "__main__":
    compiled = compile_b((HERE / "ledger.bee").read_text(), strict=True)
    namespace = {}
    exec(compiled.code, namespace)
    engines = {"B": namespace["ledger"], "Python": runpy.run_path(str(HERE / "ledger.py"))["ledger"]}
    passed = dict.fromkeys(engines, 0)
    total = 0
    for records, allowance in cases():
        expected = reference(records, allowance)
        for label, ledger in engines.items():
            got = ledger(records, allowance)
            if got != expected or any(type(v) is not int for v in got.values()):
                raise AssertionError((label, records, allowance, got, expected))
            passed[label] += 1
        total += 1
    print(total, "cases per submission", passed)
