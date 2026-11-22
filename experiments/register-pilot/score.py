"""Independent finite-domain acceptance and a smaller, identical public check."""
import json
from pathlib import Path
import sys

from b_lang.compiler import compile_b
from b_lang.runtime import BContractError

# The intended row decisions are enumerated independently of branch order.
LANES = {
    9: (-3, -1), 8: (-2,), 1: range(5), 4: (5,),
    2: (*range(6, 11), 18), 7: (*range(11, 16), 31),
    3: (16, 17, 19, 20, 21, 22), 5: range(23, 31), 6: range(32, 36),
}
# One whole cycle for each gain. Each cycle repeats at frames 8 and 16.
PULSES = {
    1: (0, 7, 12, 15, 16, 15, 12, 7),
    2: (24, 30, 32, 30, 24, 14, 0, 14),
    3: (48, 45, 36, 21, 0, 21, 36, 45),
}
PUBLIC = {
    "routing": [("lane", (-2,), 8), ("lane", (12,), 7), ("lane", (30,), 5), ("tag", (1,), 4)],
    "sampler": [("sample", (0, 1), 0), ("sample", (8, 2), 24), ("sample", (7, 1), 7), ("tag", (1,), 3)],
}


def full_cases(task):
    if task == "routing":
        rows = [("lane", (code,), lane) for lane, codes in LANES.items() for code in codes]
        rows.extend(("lane", (c,), None) for c in (-4, 36))
        rows.extend(("tag", (b,), v) for b, v in [(-4, -11), (0, 1), (6, 19)])
        return rows
    rows = [("sample", (frame, gain), cycle[frame % 8])
            for gain, cycle in PULSES.items() for frame in range(24)]
    rows.extend(("sample", pair, None) for pair in [(-1, 2), (24, 2), (1, 0), (1, 4)])
    rows.extend(("tag", (f,), v) for f, v in [(-4, -7), (0, 1), (6, 13)])
    return rows


def score(path, task, public=False):
    rows = PUBLIC[task] if public else full_cases(task)
    try:
        compiled = compile_b(Path(path).read_text())
        namespace = {}
        exec(compiled.code, namespace)
    except Exception as exc:
        return {"accepted": False, "passed": 0, "cases": len(rows), "error": str(exc)}
    expected_names = ({"lane": ("code",), "tag": ("batch",)} if task == "routing"
                      else {"sample": ("frame", "gain"), "tag": ("frame",)})
    functions = {f.name: f for f in compiled.ir.statements if f.op == "fn"}
    api_ok = all(name in functions and str(functions[name].typ) == "Int"
                 and functions[name].declared_pure
                 and functions[name].params == tuple((arg, functions[name].typ) for arg in args)
                 for name, args in expected_names.items())
    passed, failures = 0, []
    for name, args, expected in rows:
        try:
            value = namespace[name](*args)
        except BContractError:
            ok = expected is None
            value = "contract failure"
        except Exception as exc:
            ok = False
            value = type(exc).__name__
        else:
            ok = type(value) is int and value == expected
        passed += int(ok)
        if public and not ok:
            failures.append({"function": name, "args": args, "expected": expected, "observed": value})
    result = {"accepted": api_ok and passed == len(rows), "api": api_ok, "passed": passed, "cases": len(rows)}
    if public:
        result["failures"] = failures
    return result


if __name__ == "__main__":
    print(json.dumps(score(sys.argv[2], sys.argv[1], "--public" in sys.argv[3:])))
