"""Hidden fixtures and the owner's intended payslips after each step (0 = build, 1-5 = changes)."""
import calendar
import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "libs" / "payroll"))
from withholding import withholding  # noqa: E402  the task's own Python library

MONTH = "2026-03"
EMPLOYEES = [
    {"id": "e1", "hourly": 182.5, "table": 32, "contract": "2.9.4"},
    {"id": "e2", "hourly": 210.0, "table": 30, "contract": "3.0.0"},
    {"id": "e3", "hourly": 155.0, "table": 33, "contract": "3.1.0-rc.1"},
    {"id": "e4", "hourly": 240.0, "table": 31, "contract": "10.0.0"},
    {"id": "e5", "hourly": 199.0, "table": 34, "contract": "2.10.1"},
    {"id": "e6", "hourly": 520.0, "table": 32, "contract": "3.0.1"},
]
HOLIDAYS = ["2026-03-06", "2026-03-27"]
_SHIFTS = [
    # id, employee, date, hours, break
    ("s01", "e1", "2026-03-02", "8:00", "0:30"),
    ("s02", "e1", "2026-03-07", "6:10", None),
    ("s03", "e1", "2026-03-08", "4:15", "0:15"),
    ("s04", "e2", "2026-03-06", "7:45", "0:45"),
    ("s05", "e2", "2026-03-09", "9:05", "1:00"),
    ("s06", "e2", "2026-02-27", "8:00", None),
    ("s07", "e3", "2026-03-10", "7:30", "0:30"),
    ("s08", "e3", "2026-03-14", "7.5", None),
    ("s09", "e3", "2026-03-15", "10:00", "0:61"),
    ("s10", "e4", "2026-03-16", "12:00", "0:30"),
    ("s11", "e4", "2026-03-21", "11:59", None),
    ("s12", "e4", "2026-04-01", "8:00", None),
    ("s13", "e5", "2026-03-27", "6:20", "0:20"),
    ("s14", "e5", "2026-03-28", "3:00", "4:00"),
    ("s15", "e9", "2026-03-11", "8:00", None),
    ("s16", "e6", "2026-03-02", "10:00", None),
    ("s17", "e6", "2026-03-03", "10:00", "0:10"),
    ("s18", "e6", "2026-03-04", "10:00", None),
    ("s19", "e6", "2026-03-05", "10:00", None),
    ("s20", "e6", "2026-03-06", "10:00", None),
    ("s21", "e6", "2026-03-07", "9:59", None),
    ("s22", "e6", "2026-03-08", "8:00", None),
    ("s23", "e1", "2026-03-31", "0:07", None),
    ("s24", "e5", "2026-02-28", "abc", None),
    ("s25", "e2", "2026-03-12", "8:5", None),
]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MULT = {"Mon": 1.0, "Tue": 1.0, "Wed": 1.0, "Thu": 1.0, "Fri": 1.0, "Sat": 1.5, "Sun": 2.0}


def _shifts(step):
    rows = []
    for id, emp, day, hours, brk in _SHIFTS:
        if step < 4 and not day.startswith(MONTH):
            continue
        row = {"id": id, "employee": emp, "date": day, "hours": hours}
        if step >= 2 and brk is not None:
            row["break"] = brk
        rows.append(row)
    return rows


def data(step):
    out = {"month": MONTH, "employees": EMPLOYEES, "shifts": _shifts(step)}
    if step >= 3:
        out["holidays"] = HOLIDAYS
    return out


def _parse(text):
    parts = text.strip().split(":")
    if len(parts) != 2 or len(parts[1]) != 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if h < 0 or m < 0 or m > 59:
        return None
    return h + m / 60.0


def _round_up(hours):
    return max(0.0, math.ceil(hours * 4.0 - 4.0 / 3600.0)) / 4.0


def _semver_key(v):
    core, _, pre = v.partition("-")
    return tuple(int(x) for x in core.split(".")), pre


def _gets_raise(contract):
    nums, pre = _semver_key(contract)
    return not pre and nums >= (3, 0, 0)


def expected(step):
    emps = {e["id"]: e for e in EMPLOYEES}
    hours = {e: 0.0 for e in emps}
    pay = {e: 0.0 for e in emps}
    rejected = []
    for s in _shifts(step):
        if step >= 4 and not s["date"].startswith(MONTH):
            continue
        worked = _parse(s["hours"])
        if s["employee"] not in emps or worked is None:
            rejected.append(s["id"])
            continue
        if step >= 2 and "break" in s:
            brk = _parse(s["break"])
            if brk is None or brk > worked:
                rejected.append(s["id"])
                continue
            worked -= brk
        h = _round_up(worked)
        e = emps[s["employee"]]
        rate = e["hourly"] * (1.1 if step >= 1 and _gets_raise(e["contract"]) else 1.0)
        weekday = WEEKDAYS[date.fromisoformat(s["date"]).weekday()]
        mult = 2.0 if step >= 3 and s["date"] in HOLIDAYS else MULT[weekday]
        hours[e["id"]] += h
        pay[e["id"]] += h * rate * mult
    slips = {}
    for e in EMPLOYEES:
        gross = round(pay[e["id"]], 2)
        tax = withholding(gross, e["table"])
        slip = {"hours": hours[e["id"]], "gross": gross, "tax": tax, "net": round(gross - tax, 2)}
        if step >= 5:
            slip["pension"] = round(gross * 0.045, 2)
        slips[e["id"]] = slip
    return {"payslips": slips, "rejected": sorted(rejected)}


def grade(step, got):
    """Wrong units: one per employee payslip, plus one for the rejected list."""
    want = expected(step)
    slips = (got or {}).get("payslips") or {}
    wrong = []
    for emp, w in want["payslips"].items():
        g = slips.get(emp)
        ok = isinstance(g, dict) and set(g) >= set(w) and all(
            isinstance(g.get(k), (int, float)) and abs(g[k] - w[k]) <= (0.001 if k == "hours" else 0.02) for k in w)
        if not ok:
            wrong.append(emp)
    if sorted((got or {}).get("rejected") or []) != want["rejected"]:
        wrong.append("rejected")
    return wrong, len(want["payslips"]) + 1
