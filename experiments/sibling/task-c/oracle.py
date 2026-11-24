"""Hidden fixtures and the owner's intended orders after each step (0 = build, 1-5 = changes).

Every step is graded on two days: 2026-03-19 (ISO week 12) and 2026-11-26 (ISO week 48).
"""
import math
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "libs" / "weeks"))
import dates  # noqa: E402  the task's own Python library

TODAYS = ["2026-03-19", "2026-11-26"]
LEAD = {"Nordic Timber": 12, "Baltic Steel": 9, "Lumo Lighting": 5, "Fabrikk AS": 7, "Textil Partner": 14}
_ITEMS = [
    # sku, supplier, stock, pack, price
    ("oak-table", "Nordic Timber", 14, 2, 2490.0),
    ("steel-shelf", "Baltic Steel", 30, 10, 349.0),
    ("desk-lamp", "Lumo Lightning", 25, 6, 79.0),
    ("chair-seat", "Fabrikk AS", 0, 4, 120.0),
    ("curtain", "Textil Partner", 200, 20, 59.0),
    ("stool", "Fabrik AS", 8, 5, 35.0),
    ("rug", "Persian Imports", 4, 1, 1990.0),
    ("bookend", "Baltic Steel", 3, 12, 9.0),
    ("pine-bed", "nordic timber", 2, 1, 3990.0),
    ("cushion", "Textil Partner", 15, 8, 49.0),
    ("hook", "Lumo Lighting", 900, 50, 4.0),
    ("frame", "Baltic Stele", 12, 6, 89.0),
]


def _sales(today):
    t = date.fromisoformat(today)
    rows = []
    for i, (sku, *_rest) in enumerate(_ITEMS):
        for back in range(1, 36):
            day = t - timedelta(days=back)
            qty = (i * 7 + back * 3 + day.day) % (5 + i % 4)
            if qty and (back + i) % 3:
                rows.append({"sku": sku, "date": day.isoformat(), "qty": qty})
                if back % 5 == 0:
                    rows.append({"sku": sku, "date": day.isoformat(), "qty": 1})
    return rows


def data(step, today):
    items = []
    for sku, supplier, stock, pack, price in _ITEMS:
        row = {"sku": sku, "supplier": supplier, "stock": stock, "pack": pack}
        if step >= 5:
            row["price"] = price
        items.append(row)
    return {"today": today, "items": items, "sales": _sales(today)}


def _lev(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _percentile(values, p):
    v = sorted(values)
    rank = max(1, math.ceil((p / 100.0) * len(v)))
    return v[min(rank, len(v)) - 1]


def expected(step, today):
    t = date.fromisoformat(today)
    window = [(t - timedelta(days=back)).isoformat() for back in range(28, 0, -1)]
    feed = data(step, today)
    orders, unknown = {}, []
    for item in feed["items"]:
        supplier = item["supplier"]
        if step >= 4:
            best = min(sorted(LEAD), key=lambda s: _lev(supplier, s))
            supplier = best if _lev(supplier, best) <= 2 else None
        if supplier not in LEAD:
            unknown.append(item["sku"])
            continue
        series = [float(sum(s["qty"] for s in feed["sales"] if s["sku"] == item["sku"] and s["date"] == d)) for d in window]
        forecast = sum(series[-7:]) / 7 if step >= 2 else sum(series) / len(series)
        if step >= 1 and 48 <= dates.iso_week(today) <= 52:
            forecast *= 1.25
        lead = LEAD[supplier]
        need = forecast * (lead + 7) + _percentile(series, 90) - item["stock"]
        if need <= 0:
            continue
        q = math.ceil(need)
        qty = (q + item["pack"] - 1) // item["pack"] * item["pack"]
        if step >= 5 and qty * item["price"] < 500:
            continue
        arrive = dates.add_days(today, lead)
        if step >= 3:
            arrive = dates.to_weekday(arrive)
        orders[item["sku"]] = {"qty": qty, "arrive": arrive}
    return {"orders": orders, "unknown": sorted(unknown)}


def grade(step, got_by_day):
    """got_by_day maps each of TODAYS to the program's parsed output (or None). One unit per item and day."""
    wrong, units = [], 0
    for today in TODAYS:
        want, got = expected(step, today), got_by_day.get(today) or {}
        orders, unknown = got.get("orders") or {}, set(got.get("unknown") or [])
        for sku, *_ in _ITEMS:
            units += 1
            w, g = want["orders"].get(sku), orders.get(sku)
            if got_by_day.get(today) is None:
                ok = False
            elif sku in want["unknown"]:
                ok = sku in unknown and g is None
            elif w is None:
                ok = g is None and sku not in unknown
            else:
                ok = isinstance(g, dict) and g.get("qty") == w["qty"] and g.get("arrive") == w["arrive"] and sku not in unknown
            if not ok:
                wrong.append(f"{today[5:7]}:{sku}")
    return wrong, units
