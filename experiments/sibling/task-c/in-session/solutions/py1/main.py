"""Reorder suggestions for the furniture warehouse.

Reads one JSON line from stdin and writes one JSON line to stdout.
The leadtime, stats and packaging libraries are maintained in Go, Rust and C#;
their behaviour is mirrored here, and the calendar helpers are imported from
libs/weeks.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "libs" / "weeks"))

from dates import add_days, iso_week, to_weekday  # noqa: E402

# Mirrors libs/leadtime/leadtime.go.
_LEAD_DAYS: dict[str, int] = {
    "Nordic Timber": 12,
    "Baltic Steel": 9,
    "Lumo Lighting": 5,
    "Fabrikk AS": 7,
    "Textil Partner": 14,
}

_HISTORY_DAYS = 28


def lead_days(supplier: str) -> int | None:
    """Delivery time in days, or None for an unknown supplier."""
    return _LEAD_DAYS.get(supplier)


def _code_units(text: str) -> list[int]:
    """UTF-16 code units, as the JavaScript distance function compares them."""
    units: list[int] = []
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF:
            code -= 0x10000
            units.append(0xD800 + (code >> 10))
            units.append(0xDC00 + (code & 0x3FF))
        else:
            units.append(code)
    return units


def levenshtein(a: str, b: str) -> int:
    """Edit distance (insert, delete, substitute), as in fastest-levenshtein."""
    x = _code_units(a)
    y = _code_units(b)
    prev = list(range(len(y) + 1))
    for i, cx in enumerate(x, start=1):
        cur = [i] + [0] * len(y)
        for j, cy in enumerate(y, start=1):
            cost = 0 if cx == cy else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(y)]


def match_supplier(name: str) -> str | None:
    """The known supplier closest to name (at most 2 edits; ties alphabetical), or None."""
    best: str | None = None
    best_distance = 3
    for candidate in sorted(_LEAD_DAYS):
        distance = levenshtein(name, candidate)
        if distance < best_distance:
            best = candidate
            best_distance = distance
    return best


# Mirrors libs/stats/src/lib.rs.
def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def trailing_mean(values: list[float], window: int) -> float:
    """Mean of the last window values (all when there are fewer)."""
    n = len(values)
    w = min(max(window, 1), n)
    if n == 0:
        return 0.0
    return mean(values[n - w :])


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile, p in 0..=100."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil((p / 100.0) * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


# Mirrors libs/Packaging/Packs.cs.
def round_up(quantity: int, pack_size: int) -> int:
    if pack_size <= 0:
        raise ValueError("pack size must be positive")
    if quantity <= 0:
        return 0
    return (quantity + pack_size - 1) // pack_size * pack_size


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.read())
    today: str = data["today"]
    items: list[dict[str, Any]] = data["items"]
    sales: list[dict[str, Any]] = data["sales"]

    sold: dict[tuple[str, str], int] = {}
    for sale in sales:
        key = (str(sale["sku"]), str(sale["date"]))
        sold[key] = sold.get(key, 0) + int(sale["qty"])

    # Oldest first: today - 28 up to today - 1.
    window = [add_days(today, i - _HISTORY_DAYS) for i in range(_HISTORY_DAYS)]
    # Season: weeks 48 to 52 sell more, so the forecast is raised.
    season_factor = 1.25 if 48 <= iso_week(today) <= 52 else 1.0

    orders: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for item in items:
        sku = str(item["sku"])
        supplier = match_supplier(str(item["supplier"]))
        lead = None if supplier is None else lead_days(supplier)
        if lead is None:
            unknown.append(sku)
            continue
        stock = int(item["stock"])
        pack = int(item["pack"])
        price = float(item["price"])

        series = [float(sold.get((sku, day), 0)) for day in window]
        forecast = trailing_mean(series, 7) * season_factor
        safety = percentile(series, 90.0)
        need = forecast * (lead + 7) + safety - stock
        if need > 0:
            qty = round_up(math.ceil(need), pack)
            # Orders worth less than 500 SEK are not placed.
            if qty * price < 500:
                continue
            orders[sku] = {"qty": qty, "arrive": to_weekday(add_days(today, lead))}

    print(json.dumps({"orders": orders, "unknown": sorted(unknown)}))


if __name__ == "__main__":
    main()
