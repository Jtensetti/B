"""Monthly payslips. Reads one JSON line on stdin, writes one JSON line on stdout.

The time-reporting, payroll-platform and HR rules live in other teams' libraries:
  libs/hours    (Go)      Parse H:MM durations
  libs/quarter  (Rust)    round hours up to the next quarter hour
  libs/Rules    (C#)      overtime multipliers per weekday and for public holidays
  libs/payroll  (Python)  withholding tax
  node_modules/semver (npm) contract version ranges
Go, Rust, C# and Node are reached through small bridge programs in bridge/, each run
once with a batch of inputs on stdin.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

HERE: Final[Path] = Path(__file__).resolve().parent
BRIDGE: Final[Path] = HERE / "bridge"
sys.path.insert(0, str(HERE / "libs" / "payroll"))

import withholding  # noqa: E402

WEEKDAYS: Final[tuple[str, ...]] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
HOLIDAY: Final[str] = "Holiday"
PENSION_RATE: Final[float] = 0.045  # employer-paid; does not change tax or net


def _bridge(cmd: list[str], cwd: Path, payload: list[Any]) -> list[Any]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    result: list[Any] = json.loads(proc.stdout)
    return result


def _parse_hours(texts: list[str]) -> list[dict[str, Any]]:
    if not texts:
        return []
    return _bridge(["go", "run", "."], BRIDGE / "go", list(texts))


def _round_up(hours: list[float]) -> list[float]:
    if not hours:
        return []
    return _bridge(
        ["cargo", "run", "-q", "--manifest-path", str(BRIDGE / "rust" / "Cargo.toml")],
        BRIDGE / "rust",
        list(hours),
    )


def _multipliers(days: list[str]) -> dict[str, float]:
    if not days:
        return {}
    results = _bridge(
        ["dotnet", "run", "--project", str(BRIDGE / "dotnet"), "-v", "q"],
        BRIDGE / "dotnet",
        list(days),
    )
    out: dict[str, float] = {}
    for day, res in zip(days, results):
        out[day] = float(res["value"])
    return out


RAISE_RANGE: Final[str] = ">=3.0.0"
RAISE_FACTOR: Final[float] = 1.10


def _raised(contracts: list[str]) -> list[bool]:
    if not contracts:
        return []
    results = _bridge(
        ["node", "satisfies.js"],
        BRIDGE / "node",
        [[version, RAISE_RANGE] for version in contracts],
    )
    return [bool(r) for r in results]


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.read())
    employees: list[dict[str, Any]] = data["employees"]
    month = str(data["month"])
    # Shifts from other months are ignored: neither paid nor rejected.
    shifts: list[dict[str, Any]] = [
        s for s in data["shifts"] if str(s["date"])[:7] == month
    ]
    known: dict[str, dict[str, Any]] = {str(e["id"]): e for e in employees}
    raised = _raised([str(e["contract"]) for e in employees])
    rates: dict[str, float] = {}
    for emp, up in zip(employees, raised):
        rate = float(emp["hourly"])
        rates[str(emp["id"])] = rate * RAISE_FACTOR if up else rate

    # A shift may carry a "break"; worked time is hours minus break.
    with_break = [s for s in shifts if "break" in s]
    parsed = _parse_hours(
        [str(s["hours"]) for s in shifts] + [str(s["break"]) for s in with_break]
    )
    parsed_hours = parsed[: len(shifts)]
    parsed_breaks = dict(
        (str(s["id"]), res) for s, res in zip(with_break, parsed[len(shifts) :])
    )

    accepted: list[tuple[dict[str, Any], float]] = []
    rejected: list[str] = []
    for shift, res in zip(shifts, parsed_hours):
        if str(shift["employee"]) not in known or "value" not in res:
            rejected.append(str(shift["id"]))
            continue
        worked = float(res["value"])
        if "break" in shift:
            brk = parsed_breaks[str(shift["id"])]
            if "value" not in brk or float(brk["value"]) > worked:
                rejected.append(str(shift["id"]))
                continue
            worked -= float(brk["value"])
        accepted.append((shift, worked))

    rounded = _round_up([hours for _, hours in accepted])
    holidays: set[str] = {str(d) for d in data.get("holidays", [])}
    days = [
        HOLIDAY if str(shift["date"]) in holidays
        else WEEKDAYS[_weekday_index(str(shift["date"]))]
        for shift, _ in accepted
    ]
    multipliers = _multipliers(sorted(set(days)))

    hours_total: dict[str, float] = {}
    pay_total: dict[str, float] = {}
    for (shift, _), hours, day in zip(accepted, rounded, days):
        emp_id = str(shift["employee"])
        rate = rates[emp_id]
        hours_total[emp_id] = hours_total.get(emp_id, 0.0) + hours
        pay_total[emp_id] = pay_total.get(emp_id, 0.0) + hours * rate * multipliers[day]

    payslips: dict[str, dict[str, float | int]] = {}
    for emp in employees:
        emp_id = str(emp["id"])
        gross = round(pay_total.get(emp_id, 0.0), 2)
        tax = withholding.withholding(gross, int(emp["table"]))
        payslips[emp_id] = {
            "hours": hours_total.get(emp_id, 0.0),
            "gross": gross,
            "tax": tax,
            "net": round(gross - tax, 2),
            "pension": round(gross * PENSION_RATE, 2),
        }

    print(json.dumps({"payslips": payslips, "rejected": sorted(rejected)}))


def _weekday_index(iso_date: str) -> int:
    import datetime

    return datetime.date.fromisoformat(iso_date).weekday()


if __name__ == "__main__":
    main()
