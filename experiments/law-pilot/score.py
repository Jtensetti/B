"""Independent sequencer oracle. Run with a compatible B compiler on PYTHONPATH."""
import argparse
from pathlib import Path

from b_lang.compiler import compile_b
from b_lang.runtime import BContractError


def score(source: str, public: bool) -> tuple[int, list[str]]:
    program = compile_b(source)
    ns = {}
    exec(program.code, ns)
    if public:
        cases = [("event", 0, 0), ("event", 2, 105), ("preview", -1, 61),
                 ("footer", 2, 18)]
    else:
        cases = []
        for step in range(-12, 13):
            pitch = 0 if step == 0 else 2 * step + (1 if step > 0 else -1)
            event = 0 if not step else 100 + pitch if step > 0 else 200 - pitch
            cases.extend((("calibrated", step, pitch), ("event", step, event),
                          ("preview", step, 64 + pitch)))
        for value in (-100, -13, 13, 99):
            cases.extend((name, value, None) for name in ("calibrated", "event", "preview"))
        for value in (-23, -1, 0, 1, 18):
            cases.extend((("raise_event", value, 100 + value if value > 0 else None),
                          ("lower_event", value, 200 - value if value < 0 else None),
                          ("footer", value, 7 * value + 4)))

    failures = []
    for name, arg, expected in cases:
        try:
            actual = ns[name](arg)
        except BContractError:
            if expected is None:
                continue
        except Exception:
            pass
        else:
            if expected is not None and type(actual) is int and actual == expected:
                continue
        failures.append(f"{name}({arg}) expected {expected!r}")
    return len(cases), failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    total, failed = score(args.file.read_text(), args.public)
    print(f"{total - len(failed)}/{total} cases passed")
    if failed:
        print("\n".join(failed))
    raise SystemExit(bool(failed))
