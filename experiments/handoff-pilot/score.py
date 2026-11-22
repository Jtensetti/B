"""Independent finite-domain test values and an identical public subset per arm."""
from b_lang.compiler import compile_b
from b_lang.runtime import BContractError


def cases(task):
    if task == "shade":
        values = (4, 4, 4, 6, 6, 6, 3, 9, 9, 9)
        return [((z,), shade) for z, shade in enumerate(values)] + [((-1,), None), ((10,), None)]
    values = ((10, 11, 12, 13, 14, 15), (1, 2, 3, 8, 5, 6), (2, 3, 4, 8, 6, 7))
    return [((c, p), val) for c, row in enumerate(values) for p, val in enumerate(row)] + [
        ((-1, 1), None), ((3, 1), None), ((1, -1), None), ((1, 6), None)
    ]


def score(source, task, public=False):
    checks = [(task, args, expected) for args, expected in cases(task)]
    if public:
        samples = {"shade": {(0,), (6,)}, "signal": {(0, 0), (1, 3)}}[task]
        checks = [c for c in checks if c[1] in samples]
    tags = [(0, 2)] if public else [(-5, -3), (0, 2), (4, 6)]
    checks += [("label", (i,), v) for i, v in tags]
    try:
        program = compile_b(source, strict=True)
        ns = {}
        exec(program.code, ns)
        functions = {s.name: s for s in program.ir.statements if s.op == "fn"}
        expected_api = {task: ("zone",) if task == "shade" else ("channel", "phase"), "label": ("index",)}
        api = all(
            name in functions and functions[name].declared_pure and str(functions[name].typ) == "Int"
            and tuple((k, str(t)) for k, t in functions[name].params) == tuple((k, "Int") for k in args)
            for name, args in expected_api.items()
        )
        pending = any(line.strip().startswith("next ") for line in source.splitlines())
        errors = []
        for name, args, expected in checks:
            try:
                actual = ns[name](*args)
                matches = type(actual) is int and actual == expected
            except BContractError:
                actual = "outside domain"
                matches = expected is None
            if not matches:
                errors.append({"function": name, "args": args, "expected": expected, "actual": actual})
        return {"accepted": api and not pending and not errors, "passed": len(checks) - len(errors),
                "total": len(checks), "api": api, "pending": pending, "failures": errors}
    except Exception as exc:
        return {"accepted": False, "passed": 0, "total": len(checks), "error": str(exc)}
