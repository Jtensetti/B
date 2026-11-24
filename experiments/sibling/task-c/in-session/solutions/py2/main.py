"""Reorder suggestions for the furniture warehouse.

Reads one line of JSON on stdin and writes one line of JSON on stdout.
The Go, Rust and C# helpers are mirrored here from their sources under libs/;
the calendar helpers are imported from libs/weeks.
"""

import json
import math
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs", "weeks"))

from dates import add_days, iso_week, to_weekday  # noqa: E402

WINDOW_DAYS = 28
SAFETY_PERCENTILE = 90.0
EXTRA_DAYS = 7
TRAILING_WINDOW = 7
MAX_SUPPLIER_DISTANCE = 2
MIN_ORDER_VALUE = 500.0
SEASON_WEEKS = range(48, 53)
SEASON_FACTOR = 1.25

# Mirrors libs/leadtime/leadtime.go (Days).
LEAD_DAYS: dict[str, int] = {
    "Nordic Timber": 12,
    "Baltic Steel": 9,
    "Lumo Lighting": 5,
    "Fabrikk AS": 7,
    "Textil Partner": 14,
}


def lead_days(supplier: str) -> int | None:
    """Delivery time in days, or None for an unknown supplier."""
    return LEAD_DAYS.get(supplier)


def levenshtein(a: str, b: str) -> int:
    """Edit distance with unit costs. Same values as node_modules/fastest-levenshtein distance."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[len(b)]


def resolve_supplier(name: str) -> str | None:
    """The known supplier closest to name (at most 2 edits; ties go alphabetically first), or None."""
    best: str | None = None
    best_distance = MAX_SUPPLIER_DISTANCE + 1
    for known in sorted(LEAD_DAYS):
        dist = levenshtein(name, known)
        if dist < best_distance:
            best = known
            best_distance = dist
    return best


def mean(values: list[float]) -> float:
    """Mirrors libs/stats/src/lib.rs (mean): plain left-to-right sum; 0.0 when empty."""
    if not values:
        return 0.0
    total = 0.0
    for v in values:
        total += v
    return total / float(len(values))


def trailing_mean(values: list[float], window: int) -> float:
    """Mirrors libs/stats/src/lib.rs (trailing_mean): mean of the last window values (all when fewer); 0.0 when empty."""
    n = len(values)
    w = min(max(window, 1), n)
    if n == 0:
        return 0.0
    return mean(values[n - w:])


def percentile(values: list[float], p: float) -> float:
    """Mirrors libs/stats/src/lib.rs (percentile): nearest rank on sorted values; 0.0 when empty."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(math.ceil((p / 100.0) * float(len(ordered))), 1)
    return ordered[min(rank, len(ordered)) - 1]


def round_up(quantity: int, pack_size: int) -> int:
    """Mirrors libs/Packaging/Packs.cs (RoundUp)."""
    if pack_size <= 0:
        raise ValueError("pack size must be positive")
    if quantity <= 0:
        return 0
    return (quantity + pack_size - 1) // pack_size * pack_size


def window_dates(today: str) -> list[str]:
    """The 28 days before today, oldest first."""
    return [add_days(today, -WINDOW_DAYS + i) for i in range(WINDOW_DAYS)]


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.read())
    today: str = data["today"]

    totals: dict[tuple[str, str], int] = {}
    for sale in data["sales"]:
        key = (str(sale["sku"]), str(sale["date"]))
        totals[key] = totals.get(key, 0) + int(sale["qty"])

    days = window_dates(today)
    orders: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for item in data["items"]:
        sku = str(item["sku"])
        stock = int(item["stock"])
        pack = int(item["pack"])
        supplier = resolve_supplier(str(item["supplier"]))
        lead = lead_days(supplier) if supplier is not None else None
        if lead is None:
            unknown.append(sku)
            continue
        series = [float(totals.get((sku, d), 0)) for d in days]
        forecast = trailing_mean(series, TRAILING_WINDOW)
        if iso_week(today) in SEASON_WEEKS:
            forecast = forecast * SEASON_FACTOR
        safety = percentile(series, SAFETY_PERCENTILE)
        need = forecast * float(lead + EXTRA_DAYS) + safety - float(stock)
        if need > 0:
            qty = round_up(math.ceil(need), pack)
            price = float(item["price"])
            if qty * price >= MIN_ORDER_VALUE:
                orders[sku] = {"qty": qty, "arrive": to_weekday(add_days(today, lead))}

    print(json.dumps({"orders": orders, "unknown": sorted(unknown)}))


if __name__ == "__main__":
    main()
