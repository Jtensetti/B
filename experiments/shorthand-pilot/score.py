"""Independent expected results over the complete legal task grids and selected illegal calls."""
from b_lang.compiler import compile_b
from b_lang.runtime import BContractError


def observations(task):
    if task == "dispatch":
        expected = {
            "bell": (3, 4, 70, 6, 7, 8),
            "lamp": (0, 2, 4, 6, 8, 4),
            "label": ("late #2", "front", "rear", "rear", "rear", "rear"),
        }
        rows = [(name, (arg,), value) for name, values in expected.items() for arg, value in enumerate(values)]
        weights = ((0, 1, 14, 3), (4, 5, 14, 7), (8, 9, 14, 11), (12, 13, 14, 15))
        rows.extend(("weight", (c, d), val) for c, line in enumerate(weights) for d, val in enumerate(line))
        rows.extend((name, (arg,), None) for name in expected for arg in (-1, 6))
        rows.extend(("weight", args, None) for args in ((-1, 1), (4, 1), (1, -1), (1, 4)))
        return rows
    values = (
        (0, 1, 2, 3, 4, 5, 6, 7),
        (8, 9, 18, 17, 16, 15, 14, 15),
        (16, 17, 18, 17, 16, 15, 22, 23),
        (24, 25, 18, 17, 16, 15, 30, 31),
    )
    rows = [("readout", (s, t), val) for s, line in enumerate(values) for t, val in enumerate(line)]
    rows.extend(("readout", args, None) for args in ((-1, 4), (4, 4), (1, -1), (1, 8)))
    rows.extend(("marker", (s,), val) for s, val in enumerate(("service", "public", "public", "public")))
    rows.extend(("marker", (s,), None) for s in (-1, 4))
    return rows


SIGNATURES = {
    "dispatch": {"bell": (("slot",), "Int"), "lamp": (("zone",), "Int"),
                 "label": (("lane",), "Text"), "weight": (("compartment", "depot"), "Int")},
    "window": {"readout": (("station", "tick"), "Int"), "marker": (("station",), "Text")},
}
PUBLIC = {
    "dispatch": {("bell", (2,)), ("lamp", (1,)), ("label", (0,)), ("weight", (2, 2))},
    "window": {("readout", (0, 0)), ("readout", (1, 3)), ("marker", (2,))},
}


def score(source, task, public=False):
    program = compile_b(source, strict=True)
    signatures = {fn.name: (tuple(n for n, _ in fn.params), str(fn.typ)) for fn in program.ir.statements
                  if fn.op == "fn" and fn.declared_pure and all(str(t) == "Int" for _, t in fn.params)}
    namespace = {}
    exec(program.code, namespace)
    checks = observations(task)
    if public:
        checks = [row for row in checks if (row[0], row[1]) in PUBLIC[task]]
    mismatches = []
    for name, args, expected in checks:
        try:
            actual = namespace[name](*args)
            equal = type(actual) is type(expected) and actual == expected
        except BContractError:
            actual = "rejected"
            equal = expected is None
        except (KeyError, TypeError) as error:
            actual, equal = str(error), False
        if not equal:
            mismatches.append(f"{name}{args}: expected {expected!r}, got {actual!r}")
    api = signatures == SIGNATURES[task] and program.handoff is None
    return {"accepted": api and not mismatches, "passed": len(checks) - len(mismatches),
            "total": len(checks), "api": api, "mismatches": mismatches}
