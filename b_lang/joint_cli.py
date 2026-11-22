"""Run all requested pairwise checks and print the first counterexample from each."""
from .joint import check_joint
from .request_json import MAX_REQUEST_BYTES, decode
from .types import BError


def run_checks(program, paths):
    checks = []
    for path in paths:
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                raise BError("E_JOINT_LIMIT", f"Request exceeds {MAX_REQUEST_BYTES} bytes")
            report = check_joint(program, decode(raw, "E_JOINT_INPUT"))
        except (OSError, BError) as exc:
            report = {"status": "error", "code": getattr(exc, "code", "E_JOINT_INPUT"), "reason": str(exc)}
        checks.append({"request": str(path), **report})
    return checks


def describe(report):
    parts = [f"{report['request']} — {report['status']}"]
    if "relation" in report:
        parts.append(report["relation"])
    if report["status"] == "passed":
        parts.append(f"{report['checked_pairs']} selected pair(s) checked")
    elif "reason" in report:
        parts.append(report["reason"])
    for call in report.get("witness", {}).values():
        args = ", ".join(f"{k}={v}" for k, v in call["inputs"].items())
        label = f"{call['function']}({args})"
        if "result" in call:
            parts.append(f"{label} -> {call['result']}")
        elif "error" in call:
            parts.append(f"{label} raised {call['error']}")
        else:
            parts.append(label)
    comparison = report.get("failed_comparison")
    if comparison:
        parts.append(f"required {comparison['left_value']} {comparison['operator']} {comparison['right_value']}")
    return " | ".join(parts)
