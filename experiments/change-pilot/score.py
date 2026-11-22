"""Run the public smoke test or sealed behavioral oracle against a B/Python candidate."""
import argparse
import contextlib
import io
import runpy
from pathlib import Path


def evaluate(path: Path, public: bool) -> tuple[int, list[str]]:
    if path.suffix == ".bee":
        from b_lang.compiler import compile_b
        from b_lang.runtime import BContractError
        ns = {}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile_b(path.read_text()).code, ns)
        rejected = BContractError
    else:
        ns = runpy.run_path(str(path))
        rejected = (ValueError, AssertionError)

    cases = []

    def add(name, args, expected):
        cases.append((name, args, expected))

    if public:
        add("billable", (0,), 0)
        add("rate", (21, 2), 7.0)
        add("label", (2,), 1003)
        add("fee", (-1,), -1)
    else:
        for extra in (0, 1, 2, 6, 19, 50, 137):
            units = 0 if extra == 0 else extra + 1
            add("billable", (extra,), units)
            add("label", (extra,), 1000 + units)
            for total in (-105, -1, 0, 1, 8, 104):
                add("rate", (total, extra), total / units if units else 0.0)
                add("carry", (total, extra), total % units if units else total)
        for extra in (-1, -15):
            for name, args in (("billable", (extra,)), ("rate", (12, extra)),
                               ("carry", (-1, extra)), ("label", (extra,))):
                add(name, args, None)
        for net in (-105, 0, 8, 104):
            add("fee", (net,), net * 3 + 2)

    failures = []
    for name, args, expected in cases:
        try:
            actual = ns[name](*args)
        except rejected:
            if expected is None:
                continue
        except Exception:
            pass
        else:
            if expected is not None and type(actual) is type(expected) and actual == expected:
                continue
        failures.append(f"{name}{args} expected {expected!r}")
    return len(cases), failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    total, failures = evaluate(args.file, args.public)
    print(f"{total - len(failures)}/{total} cases passed")
    if failures:
        print("\n".join(failures))
    raise SystemExit(bool(failures))
