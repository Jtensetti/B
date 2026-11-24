"""Reorder suggestions for a furniture warehouse.

Reads one line of JSON on stdin, writes one line of JSON on stdout.

The helpers below are ports of the behaviour of the team libraries in libs/
(Go leadtime, Rust stats, C# Packs, Python weeks), since those cannot be
imported from a Python program directly.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from typing import Any, Final

# libs/leadtime (Go): delivery time in days per supplier.
LEAD_DAYS: Final[dict[str, int]] = {
    "Nordic Timber": 12,
    "Baltic Steel": 9,
    "Lumo Lighting": 5,
    "Fabrikk AS": 7,
    "Textil Partner": 14,
}

# The daily series covers the 28 days before today.
SERIES_DAYS: Final[int] = 28

# The forecast is the trailing mean of the last 7 days of the series.
FORECAST_WINDOW: Final[int] = 7

# Safety stock is the 90th percentile of the series.
SAFETY_PERCENT: Final[float] = 90.0

# Seasonal uplift: ISO weeks 48 to 52 multiply the forecast by 1.25.
SEASON_WEEKS: Final[tuple[int, int]] = (48, 52)
SEASON_FACTOR: Final[float] = 1.25


# An order worth less than this many SEK (qty x price) is not placed.
MIN_ORDER_SEK: Final[float] = 500.0

# Largest edit distance still accepted when matching a misspelled supplier name.
MAX_SUPPLIER_DISTANCE: Final[int] = 2


def levenshtein(a: str, b: str) -> int:
    """Edit distance with unit costs for insert, delete and substitute (fastest-levenshtein)."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def match_supplier(name: str) -> str | None:
    """The known supplier closest to name (ties: alphabetically first), if within the maximum distance."""
    best: str | None = None
    best_distance = MAX_SUPPLIER_DISTANCE + 1
    for known in sorted(LEAD_DAYS):
        distance = levenshtein(name, known)
        if distance < best_distance:
            best, best_distance = known, distance
    return best


def lead_days(supplier: str) -> int | None:
    """Delivery days for a supplier, or None when the supplier is unknown."""
    matched = match_supplier(supplier)
    if matched is None:
        return None
    return LEAD_DAYS[matched]


def mean(values: list[float]) -> float:
    """Arithmetic mean; 0.0 for an empty list (libs/stats)."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def trailing_mean(values: list[float], window: int) -> float:
    """Mean of the last window values (all values when there are fewer); 0.0 for an empty list (libs/stats)."""
    n = len(values)
    w = min(max(window, 1), n)
    if n == 0:
        return 0.0
    return mean(values[n - w :])


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile on the sorted values; 0.0 for an empty list (libs/stats)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(math.ceil((p / 100.0) * len(ordered)), 1)
    return ordered[min(rank, len(ordered)) - 1]


def round_up(quantity: int, pack_size: int) -> int:
    """Smallest multiple of pack_size that is at least quantity (libs/Packaging)."""
    if pack_size <= 0:
        raise ValueError("pack size must be positive")
    if quantity <= 0:
        return 0
    return (quantity + pack_size - 1) // pack_size * pack_size


def add_days(iso_date: str, days: int) -> str:
    """The date the given number of days after iso_date (libs/weeks)."""
    return (date.fromisoformat(iso_date) + timedelta(days=days)).isoformat()


def to_weekday(iso_date: str) -> str:
    """The date itself on Monday to Friday; the following Monday for a Saturday or Sunday (libs/weeks)."""
    d = date.fromisoformat(iso_date)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


def build_series(today: date, sales: list[dict[str, Any]], skus: set[str]) -> dict[str, list[float]]:
    """Quantity sold per sku on each of the 28 days before today, oldest first."""
    first_day = today - timedelta(days=SERIES_DAYS)
    position = {(first_day + timedelta(days=i)).isoformat(): i for i in range(SERIES_DAYS)}
    series: dict[str, list[float]] = {sku: [0.0] * SERIES_DAYS for sku in skus}
    for sale in sales:
        sku = str(sale["sku"])
        index = position.get(str(sale["date"]))
        if sku in series and index is not None:
            series[sku][index] += float(sale["qty"])
    return series


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.read())
    today_text = str(data["today"])
    today = date.fromisoformat(today_text)
    items: list[dict[str, Any]] = data["items"]
    sales: list[dict[str, Any]] = data["sales"]

    series = build_series(today, sales, {str(item["sku"]) for item in items})

    orders: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for item in items:
        sku = str(item["sku"])
        lead = lead_days(str(item["supplier"]))
        if lead is None:
            unknown.append(sku)
            continue
        history = series[sku]
        forecast = trailing_mean(history, FORECAST_WINDOW)
        if SEASON_WEEKS[0] <= today.isocalendar()[1] <= SEASON_WEEKS[1]:
            forecast = forecast * SEASON_FACTOR
        safety = percentile(history, SAFETY_PERCENT)
        need = forecast * (lead + 7) + safety - int(item["stock"])
        if need > 0:
            qty = round_up(math.ceil(need), int(item["pack"]))
            if qty * float(item["price"]) >= MIN_ORDER_SEK:
                orders[sku] = {"qty": qty, "arrive": to_weekday(add_days(today_text, lead))}

    result: dict[str, Any] = {"orders": orders, "unknown": sorted(unknown)}
    sys.stdout.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
