"""Monthly payslips for a staffing company.

Reads one JSON line on stdin and writes one JSON line on stdout.

Time parsing (Go), quarter rounding (Rust), overtime multipliers (C#) and contract
version ranges (npm semver) come from the libraries under libs/ and node_modules/
through small driver programs under bridge/. Tax withholding is imported from
libs/payroll.
"""

import datetime
import json
import os
import subprocess
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, "bridge")
sys.path.insert(0, os.path.join(HERE, "libs", "payroll"))

from withholding import withholding  # noqa: E402

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def run_tool(args: list[str], cwd: str, stdin_text: str) -> str:
    proc = subprocess.run(
        args, cwd=cwd, input=stdin_text, capture_output=True, text=True, check=True
    )
    return proc.stdout


def parse_hours(texts: list[str]) -> list[float | None]:
    """hours.Parse for each text; None where it returns an error."""
    out = run_tool(
        ["go", "run", "."], os.path.join(BRIDGE, "hours"), json.dumps(texts)
    )
    raw: list[Any] = json.loads(out)
    return [float(x) if isinstance(x, (int, float)) else None for x in raw]


def round_up_quarters(hours: list[float]) -> list[float]:
    """quarter.round_up for each value."""
    if not hours:
        return []
    manifest = os.path.join(BRIDGE, "quarter", "Cargo.toml")
    out = run_tool(
        ["cargo", "run", "-q", "--manifest-path", manifest],
        HERE,
        "".join(f"{h!r}\n" for h in hours),
    )
    return [float(tok) for tok in out.split()]


PENSION_RATE = 0.045  # paid by the employer; does not change tax or net
HOLIDAY_KEY = "@holiday"


def overtime_multipliers(keys: list[str]) -> list[float]:
    """Overtime.Multiplier for each weekday, Overtime.Holiday() for HOLIDAY_KEY."""
    if not keys:
        return []
    project = os.path.join(BRIDGE, "rules")
    out = run_tool(
        ["dotnet", "run", "--project", project, "-v", "q"],
        HERE,
        "".join(f"{k}\n" for k in keys),
    )
    tokens = out.split()
    if len(tokens) != len(keys) or "ERR" in tokens:
        raise RuntimeError(f"Overtime.Multiplier failed: {out!r}")
    return [float(tok) for tok in tokens]


PREMIUM_CONTRACT_RANGE = ">=3.0.0"
PREMIUM_FACTOR = 1.1


def premium_contracts(versions: list[str]) -> list[bool]:
    """semver.satisfies(version, ">=3.0.0") for each contract version."""
    if not versions:
        return []
    script = os.path.join(BRIDGE, "semver", "satisfies.js")
    out = run_tool(
        ["node", script, PREMIUM_CONTRACT_RANGE], HERE, json.dumps(versions)
    )
    raw: list[Any] = json.loads(out)
    return [x is True for x in raw]


def weekday_of(text: str) -> str | None:
    try:
        return WEEKDAYS[datetime.date.fromisoformat(text).weekday()]
    except (TypeError, ValueError):
        return None


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.readline())
    employees: dict[str, dict[str, Any]] = {e["id"]: e for e in data["employees"]}
    shifts: list[dict[str, Any]] = data["shifts"]

    # A shift's worked time is its hours minus its optional break (default 0:00).
    texts = [str(s["hours"]) for s in shifts] + [
        str(s.get("break", "0:00")) for s in shifts
    ]
    parsed_all = parse_hours(texts)
    parsed_hours = parsed_all[: len(shifts)]
    parsed_breaks = parsed_all[len(shifts) :]

    holidays = set(str(d) for d in data.get("holidays", []))

    rejected: list[str] = []
    valid: list[tuple[dict[str, Any], str]] = []  # (shift, pay key)
    valid_hours: list[float] = []
    month = str(data["month"])
    for shift, hours, brk in zip(shifts, parsed_hours, parsed_breaks):
        if str(shift["date"])[:7] != month:
            continue  # other months are neither paid nor rejected
        weekday = weekday_of(str(shift["date"]))
        if (
            shift["employee"] not in employees
            or hours is None
            or brk is None
            or brk > hours
            or weekday is None
        ):
            rejected.append(str(shift["id"]))
        else:
            key = HOLIDAY_KEY if str(shift["date"]) in holidays else weekday
            valid.append((shift, key))
            valid_hours.append(hours - brk)

    rounded = round_up_quarters(valid_hours)
    unique_keys = sorted({key for _, key in valid})
    multiplier = dict(zip(unique_keys, overtime_multipliers(unique_keys)))

    emp_ids = list(employees)
    premium = dict(
        zip(emp_ids, premium_contracts([str(employees[e]["contract"]) for e in emp_ids]))
    )

    hours_by: dict[str, float] = {eid: 0.0 for eid in employees}
    pay_by: dict[str, float] = {eid: 0.0 for eid in employees}
    for (shift, key), hours in zip(valid, rounded):
        eid = shift["employee"]
        rate = float(employees[eid]["hourly"])
        if premium[eid]:
            rate *= PREMIUM_FACTOR
        hours_by[eid] += hours
        pay_by[eid] += hours * rate * multiplier[key]

    payslips: dict[str, dict[str, float]] = {}
    for eid, emp in employees.items():
        gross = round(pay_by[eid], 2)
        tax = withholding(gross, int(emp["table"]))
        payslips[eid] = {
            "hours": hours_by[eid],
            "gross": gross,
            "tax": tax,
            "net": round(gross - tax, 2),
            "pension": round(gross * PENSION_RATE, 2),
        }

    print(json.dumps({"payslips": payslips, "rejected": sorted(rejected)}))


if __name__ == "__main__":
    main()
