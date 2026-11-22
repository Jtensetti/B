"""Two follow-up requests and independent complete tables fixed before either continuation."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from b_lang.compiler import compile_b
from b_lang.runtime import BContractError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from score import SIGNATURES

BRIEFS = {
    2: (
        "Extend the running dispatch revision. Slot 4 now needs bell value 11. Zone 1 now needs lamp "
        'value 17. Lane 3 gets label "under deck". Every load in compartment 3 now has weight 31, '
        "including at depot 2. Preserve all other results from the running revision and its public interfaces."
    ),
    3: (
        'Make another dispatch revision. Slot 0 needs bell value 12, zone 3 needs lamp value 21, and lane 4 '
        'must be labeled "bay #4". All compartments at depot 0 must now have weight 25, including '
        "compartment 3. Preserve every other result of the current revision and its public interfaces."
    ),
}

EXPECTED = {
    2: {
        "bell": (3, 4, 70, 6, 11, 8), "lamp": (0, 17, 4, 6, 8, 4),
        "label": ("late #2", "front", "rear", "under deck", "rear", "rear"),
        "weight": ((0, 1, 14, 3), (4, 5, 14, 7), (8, 9, 14, 11), (31, 31, 31, 31)),
    },
    3: {
        "bell": (12, 4, 70, 6, 11, 8), "lamp": (0, 17, 4, 21, 8, 4),
        "label": ("late #2", "front", "rear", "under deck", "bay #4", "rear"),
        "weight": ((25, 1, 14, 3), (25, 5, 14, 7), (25, 9, 14, 11), (25, 31, 31, 31)),
    },
}
PUBLIC = {
    2: {("bell", (4,)), ("lamp", (1,)), ("label", (3,)), ("weight", (3, 3))},
    3: {("bell", (0,)), ("lamp", (3,)), ("label", (4,)), ("weight", (0, 0))},
}


def apply_edit(before, register, payload):
    if register == "full":
        return payload
    if register not in ("short", "b"):
        raise ValueError("Use a previously available submission format")
    with TemporaryDirectory() as temp:
        path = Path(temp) / "state.bee"
        path.write_text(before + ("\n" + payload if register == "b" else ""))
        cmd = [sys.executable, "-m", "b_lang.cli", "next", str(path), "--apply", "--strict"]
        if register == "short":
            cmd.extend(["--from-short", "-"])
        process = subprocess.run(cmd, input=payload if register == "short" else "", capture_output=True, text=True)
        if process.returncode:
            raise ValueError(process.stderr.strip())
        return path.read_text()


def evaluate(program, stage, public):
    candidate = compile_b(program, strict=True)
    names = {f.name: (tuple(n for n, _ in f.params), str(f.typ)) for f in candidate.ir.statements
             if f.op == "fn" and f.declared_pure and all(str(t) == "Int" for _, t in f.params)}
    api = names == SIGNATURES["dispatch"] and candidate.handoff is None
    ns = {}
    exec(candidate.code, ns)
    cases = []
    for name in ("bell", "lamp", "label"):
        cases.extend((name, (k,), v) for k, v in enumerate(EXPECTED[stage][name]))
        cases.extend((name, (k,), None) for k in (-1, 6))
    cases.extend(("weight", (c, d), v) for c, line in enumerate(EXPECTED[stage]["weight"]) for d, v in enumerate(line))
    cases.extend(("weight", args, None) for args in ((-1, 1), (4, 1), (1, -1), (1, 4)))
    if public:
        cases = [row for row in cases if (row[0], row[1]) in PUBLIC[stage]]
    errors = []
    for name, args, expected in cases:
        try:
            actual = ns[name](*args)
            ok = type(actual) is type(expected) and actual == expected
        except BContractError:
            ok = expected is None
        except (KeyError, TypeError):
            ok = False
        if not ok:
            errors.append(f"{name}{args} should yield {expected!r}")
    return dict(accepted=api and not errors, passed=len(cases)-len(errors), total=len(cases), failures=errors)
