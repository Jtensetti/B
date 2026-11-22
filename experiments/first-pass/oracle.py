"""Independently score snapshots in submission order; no public-feedback implementation."""
import json
import sys
from itertools import product
from pathlib import Path

from b_lang.compiler import compile_b
from b_lang.runtime import BContractError


def expected(task):
    rows = []
    if task == "pagination":
        for compact in (0, 1):
            pen = compact
            for row in range(10):
                width = (2, 4)[row % 2] if compact else 4
                rows.extend([("start", (row, compact), pen), ("stop", (row, compact), pen + width)])
                pen += width
                if compact:
                    pen += {1: 1, 4: 2}.get(row, 0)
        for name in ("start", "stop"):
            rows.extend((name, args, None) for args in [(-1, 0), (10, 1), (0, -1), (0, 2)])
        rows.extend(("page_tag", (s,), 7*s + 2) for s in (-3, 0, 2))
    else:
        for total, requested, rush in product(range(9), range(9), (0, 1)):
            available = total - int(bool(rush and total >= 4))
            claim = requested + int(bool(rush and requested and available >= 3))
            # Exhaust legal assignments and choose the maximum grant allowed by policy.
            grants = [n for n in range(available+1) if n <= claim
                      and (not rush or available < 2 or available - n >= 1)]
            fast = max(grants)
            rows.extend([("fast", (total, requested, rush), fast),
                         ("slow", (total, requested, rush), available - fast)])
        for name in ("fast", "slow"):
            rows.extend((name, args, None) for args in [(-1,0,0), (9,0,1), (0,-1,0), (0,9,1),
                                                       (0,0,-1), (0,0,2)])
        rows.extend(("batch_tag", (s,), s*5 + 3) for s in (-3, 0, 2))
    return rows


def score(path, task):
    rows = expected(task)
    try:
        compiled = compile_b(Path(path).read_text())
        ns = {}
        exec(compiled.code, ns)
        signatures = {s.name: (tuple((n, str(t)) for n,t in s.params), str(s.typ))
                      for s in compiled.ir.statements if s.op == "fn"}
        prototype = ("row","compact") if task == "pagination" else ("total","quota","rush")
        targets = ("start","stop","page_tag") if task == "pagination" else ("fast","slow","batch_tag")
        api_ok = all(signatures.get(name) ==
                     (tuple((n, "Int") for n in (prototype if name in targets[:2] else ("sheet",))), "Int")
                     for name in targets)
    except Exception:
        return {"accepted":False, "api_ok":False, "passed":0, "cases":len(rows)}
    passed = 0
    for name, args, value in rows:
        try:
            observed = ns[name](*args)
        except BContractError:
            passed += value is None
        except Exception:
            pass
        else:
            passed += type(observed) is int and observed == value
    return {"accepted":api_ok and passed==len(rows), "api_ok":api_ok, "passed":passed, "cases":len(rows)}


if __name__ == "__main__":
    print(json.dumps(score(sys.argv[2],sys.argv[1])))
