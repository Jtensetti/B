"""Monthly payslips for a staffing company.

Reads one line of JSON on stdin and writes one line of JSON on stdout.

The helpers below mirror the libraries in libs/ (hours, quarter, Rules). Those are
written in Go, Rust and C#, so their behaviour is re-implemented here from their
source. Withholding is imported from libs/payroll directly.
"""

from __future__ import annotations

import datetime
import json
import math
import re
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent / "libs" / "payroll"))
from withholding import withholding  # type: ignore[import-not-found]

INT64_MIN: Final = -(2**63)
INT64_MAX: Final = 2**63 - 1
_INT_RE: Final = re.compile(r"[+-]?[0-9]+")
_DATE_RE: Final = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_WEEKDAYS: Final = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MULTIPLIERS: Final = {
    "Mon": 1.0,
    "Tue": 1.0,
    "Wed": 1.0,
    "Thu": 1.0,
    "Fri": 1.0,
    "Sat": 1.5,
    "Sun": 2.0,
}


def _atoi(text: str) -> int:
    """Mirror of Go strconv.Atoi for base 10: optional sign, digits, int64 range."""
    if _INT_RE.fullmatch(text) is None:
        raise ValueError(f"not an integer: {text!r}")
    value = int(text)
    if value < INT64_MIN or value > INT64_MAX:
        raise ValueError(f"out of range: {text!r}")
    return value


def parse_hours(text: Any) -> float:
    """Mirror of libs/hours Parse: H:MM to hours. Raises ValueError on bad input."""
    if not isinstance(text, str):
        raise ValueError("hours must be a string")
    parts = text.strip().split(":")
    if len(parts) != 2 or len(parts[1]) != 2:
        raise ValueError(f"expected H:MM, got {text}")
    h = _atoi(parts[0])
    if h < 0:
        raise ValueError(f"bad hours in {text}")
    m = _atoi(parts[1])
    if m < 0 or m > 59:
        raise ValueError(f"bad minutes in {text}")
    return float(h) + float(m) / 60.0


def round_up(hours: float) -> float:
    """Mirror of libs/quarter round_up: up to the next quarter hour, with 1 s tolerance."""
    quarters = hours * 4.0
    tolerance = 4.0 / 3600.0
    return float(max(math.ceil(quarters - tolerance), 0)) / 4.0


def weekday_of(date_text: Any) -> str:
    """Weekday name ("Mon".."Sun") of a YYYY-MM-DD date. Raises ValueError if invalid."""
    if not isinstance(date_text, str):
        raise ValueError("date must be a string")
    match = _DATE_RE.fullmatch(date_text)
    if match is None:
        raise ValueError(f"bad date {date_text!r}")
    day = datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return _WEEKDAYS[day.weekday()]


def multiplier(weekday: str) -> float:
    """Mirror of libs/Rules Overtime.Multiplier for weekday names."""
    return _MULTIPLIERS[weekday]


def holiday_multiplier() -> float:
    """Mirror of libs/Rules Overtime.Holiday."""
    return 2.0


SENIOR_RANGE: Final = ">=3.0.0"
SENIOR_BONUS: Final = 1.1
_SEMVER_JS: Final = (
    "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
    "const s = require(input.path);"
    "process.stdout.write(JSON.stringify(input.versions.map("
    "v => typeof v === 'string' && s.satisfies(v, input.range))));"
)


def satisfies_batch(versions: list[Any], range_text: str) -> list[bool]:
    """Ask npm's semver (node_modules/semver) whether each version satisfies the range."""
    request = json.dumps(
        {
            "path": str(Path(__file__).resolve().parent / "node_modules" / "semver"),
            "range": range_text,
            "versions": versions,
        }
    )
    proc = subprocess.run(
        ["node", "-e", _SEMVER_JS],
        input=request,
        capture_output=True,
        text=True,
        check=True,
    )
    return [bool(x) for x in json.loads(proc.stdout)]


PENSION_RATE: Final = Decimal("0.045")


def pension(gross: float) -> float:
    """Employer pension: 4.5 % of gross, rounded half-up to 2 decimals (money, so Decimal)."""
    amount = Decimal(repr(gross)) * PENSION_RATE
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute(data: dict[str, Any]) -> dict[str, Any]:
    employees: list[dict[str, Any]] = data["employees"]
    senior = satisfies_batch([emp["contract"] for emp in employees], SENIOR_RANGE)

    rates: dict[str, tuple[float, int]] = {}
    hours_total: dict[str, float] = {}
    pay_total: dict[str, float] = {}
    for emp, is_senior in zip(employees, senior):
        emp_id = str(emp["id"])
        hourly = float(emp["hourly"])
        if is_senior:
            hourly *= SENIOR_BONUS
        rates[emp_id] = (hourly, int(emp["table"]))
        hours_total[emp_id] = 0.0
        pay_total[emp_id] = 0.0

    holidays = {str(d) for d in (data.get("holidays") or [])}
    rejected: list[str] = []
    month = str(data["month"])
    for shift in data["shifts"]:
        shift_id = str(shift["id"])
        emp_id = str(shift["employee"])
        if not str(shift["date"]).startswith(month + "-"):
            continue  # other months are ignored, not rejected
        if emp_id not in rates:
            rejected.append(shift_id)
            continue
        try:
            parsed = parse_hours(shift["hours"])
            if shift.get("break") is not None:
                brk = parse_hours(shift["break"])
                if brk > parsed:
                    raise ValueError(f"break longer than shift in {shift_id}")
                parsed = parsed - brk
            weekday = weekday_of(shift["date"])
        except ValueError:
            rejected.append(shift_id)
            continue
        hours = round_up(parsed)
        rate, _ = rates[emp_id]
        hours_total[emp_id] += hours
        factor = holiday_multiplier() if shift["date"] in holidays else multiplier(weekday)
        pay_total[emp_id] += hours * rate * factor

    payslips: dict[str, dict[str, Any]] = {}
    for emp_id, (_, table) in rates.items():
        gross = round(pay_total[emp_id], 2)
        tax = int(withholding(gross, table))
        net = round(gross - tax, 2)
        payslips[emp_id] = {
            "hours": hours_total[emp_id],
            "gross": gross,
            "tax": tax,
            "net": net,
            "pension": pension(gross),
        }

    return {"payslips": payslips, "rejected": sorted(rejected)}


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.readline())
    sys.stdout.write(json.dumps(compute(data)) + "\n")


if __name__ == "__main__":
    main()
