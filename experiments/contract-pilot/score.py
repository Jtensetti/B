"""Score code and contracts independently against the frozen product policy."""
import argparse
import itertools
import json
from pathlib import Path

from b_lang.compiler import compile_b
from b_lang.contracts import constant
from b_lang.runtime import BContractError


def inputs(task):
    count = 2 if task == "ledger" else 1
    return itertools.product(range(7), repeat=count)


def legal(task, args, result):
    if task == "ledger":
        arrivals, departures = args
        return result == 1 + arrivals - departures
    rank, = args
    return 1 <= result <= 3 if rank <= 1 else 2 <= result <= 8


def expected_default(task, args):
    if task == "ledger":
        arrivals, departures = args
        return 1 + arrivals - departures
    rank, = args
    return rank + 1


def score(path, task, public=False):
    name = "balance" if task == "ledger" else "gap"
    program = compile_b(Path(path).read_text())
    ns = {}
    exec(program.code, ns)

    if public:
        cases = ((name, (2, 0), 3), ("footer", (-1,), -1)) if task == "ledger" else (
            (name, (0,), 1), ("footer", (-1,), -1))
        return {"public_passed": sum(type(v := ns[n](*args)) is int and v == expected
                                     for n, args, expected in cases), "public_cases": len(cases)}

    fn = next(s for s in program.ir.statements if s.op == "fn" and s.name == name)
    param_names = [n for n, _ in fn.params]
    correct = behavior_total = allowed = blocked_legal = disallowed = admitted_illegal = 0
    for args in inputs(task):
        behavior_total += 1
        try:
            value = ns[name](*args)
        except BContractError:
            pass
        else:
            correct += type(value) is int and value == expected_default(task, args)
        # The published input domains are exhaustively enumerated. Candidate outputs
        # include all legal values, adjacent illegal values and two distant sentinels.
        for candidate in [-1000, *range(-8, 17), 1000]:
            expected = legal(task, args, candidate)
            env = dict(zip(param_names, args)) | {"result": candidate}
            actual = True if fn.ensures is None else constant(fn.ensures, env)
            if actual is not True and actual is not False:
                raise ValueError("Scorer cannot interpret this candidate contract")
            if expected:
                allowed += 1
                blocked_legal += not actual
            else:
                disallowed += 1
                admitted_illegal += actual

    amin, amax = (-1, 0), (0, 7)
    invalid = (amin, amax, (7, 6), (6, -1)) if task == "ledger" else ((-1,), (7,))
    rejected_inputs = 0
    for args in invalid:
        try:
            ns[name](*args)
        except BContractError:
            rejected_inputs += 1
    same_footer = all(ns["footer"](page) == page * 3 + 2 for page in (-13, 0, 1, 8))
    return {"public_fn": name, "default_correct": correct, "valid_inputs": behavior_total,
            "invalid_rejected": rejected_inputs, "invalid_probes": len(invalid), "footer_ok": same_footer,
            "proved_post": bool(fn.verification and fn.verification.startswith("proved")),
            "legal_pairs": allowed, "blocked_legal": blocked_legal, "illegal_pairs": disallowed,
            "admitted_illegal": admitted_illegal}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=("ledger", "spacing"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    data = score(args.file, args.task, args.public)
    print(json.dumps(data, sort_keys=True))
    if args.public:
        raise SystemExit(data["public_passed"] != data["public_cases"])
