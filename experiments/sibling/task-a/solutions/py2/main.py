"""Delivery quotes for a furniture shop in Stockholm.

Reads one line of JSON on standard input and writes one line of JSON.

The rules of the other team libraries in libs/ (tariff, geo, Tax, calendar)
and the Levenshtein matching of node_modules/fastest-levenshtein are ported
here so the program runs as a single Python file.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# --- libs/geo (routing team) -------------------------------------------------

EARTH_RADIUS_KM = 6371.0
ROAD_DETOUR_FACTOR = 1.25

# --- libs/tariff (logistics team) --------------------------------------------

ZONES: dict[str, int] = {
    "SE": 1, "NO": 2, "DK": 2, "FI": 2, "DE": 3, "NL": 3, "PL": 3,
    "FR": 4, "ES": 4, "IT": 4,
}
START_SEK: dict[int, float] = {1: 49.0, 2: 79.0, 3: 99.0, 4: 129.0}
PER_KG_SEK: dict[int, float] = {1: 6.5, 2: 9.0, 3: 11.0, 4: 14.5}

# --- libs/Tax (finance team) -------------------------------------------------

STANDARD_VAT: dict[str, float] = {
    "SE": 0.25, "NO": 0.25, "DK": 0.25, "FI": 0.255, "DE": 0.19,
    "NL": 0.21, "PL": 0.23, "FR": 0.20, "ES": 0.21, "IT": 0.22,
}
EU_COUNTRIES: frozenset[str] = frozenset(
    {"SE", "DK", "FI", "DE", "NL", "PL", "FR", "ES", "IT"}
)

# --- libs/calendar (operations team), 2026 holidays only ---------------------

HOLIDAYS_2026: frozenset[str] = frozenset({
    "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01",
    "2026-05-14", "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25",
    "2026-12-26", "2026-12-31",
})

# --- delivery rules ----------------------------------------------------------

MAX_NAME_DISTANCE = 2
FREE_KM = 300.0
SURCHARGE_PER_KM_SEK = 0.80
MAX_SURCHARGE_SEK = 400.0
FREE_FREIGHT_KG = 50.0


def normalise_country(code: str) -> str:
    return code.strip().upper()


def round_money(amount: float) -> float:
    """Round to 2 decimals, halves away from zero."""
    return float(Decimal(repr(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def levenshtein(a: str, b: str) -> int:
    """Classic edit distance (insert, delete, substitute each cost 1)."""
    previous: list[int] = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current: list[int] = [i]
        for j, char_b in enumerate(b, 1):
            substitution = previous[j - 1] + (0 if char_a == char_b else 1)
            current.append(min(previous[j] + 1, current[j - 1] + 1, substitution))
        previous = current
    return previous[-1]


def match_product(name: str, catalog: dict[str, float]) -> str | None:
    """Closest catalog name within the allowed distance; ties go to the alphabetically first."""
    best: str | None = None
    best_distance = MAX_NAME_DISTANCE + 1
    for candidate in sorted(catalog):
        distance = levenshtein(name, candidate)
        if distance < best_distance:
            best = candidate
            best_distance = distance
    if best is None or best_distance > MAX_NAME_DISTANCE:
        return None
    return best


def base_price(zone: int, weight_kg: float) -> float:
    """Carrier price in SEK excluding VAT; weight is rounded up to the next half kilogram."""
    billed = math.ceil(weight_kg * 2) / 2
    return START_SEK[zone] + PER_KG_SEK[zone] * billed


def road_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance times the detour factor."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2.0) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2)
    great_circle = 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
    return great_circle * ROAD_DETOUR_FACTOR


def is_workday(day: date) -> bool:
    return day.weekday() < 5 and day.isoformat() not in HOLIDAYS_2026


def next_workday(iso_date: str) -> str:
    """First Swedish working day strictly after the given date."""
    day = date.fromisoformat(iso_date) + timedelta(days=1)
    while not is_workday(day):
        day += timedelta(days=1)
    return day.isoformat()


def reverse_charge(country: str, business: bool) -> bool:
    code = normalise_country(country)
    return business and code != "SE" and code in EU_COUNTRIES


def quote_order(
    order: dict[str, Any],
    depot: dict[str, Any],
    catalog: dict[str, float],
) -> tuple[float, str] | None:
    """Price (SEK incl. VAT) and delivery date for one order, or None if unknown."""
    country = str(order["country"])
    code = normalise_country(country)
    zone = ZONES.get(code)
    if zone is None:
        return None

    product = match_product(str(order["product"]), catalog)
    if product is None:
        return None

    distance = road_km(
        float(depot["lat"]), float(depot["lon"]),
        float(order["lat"]), float(order["lon"]),
    )
    surcharge = min(
        SURCHARGE_PER_KM_SEK * max(0.0, distance - FREE_KM),
        MAX_SURCHARGE_SEK,
    )
    qty = float(order.get("qty", 1))
    weight = catalog[product] * qty
    business = bool(order["business"])
    if business and weight >= FREE_FREIGHT_KG:
        base = 0.0
    else:
        base = base_price(zone, weight)
    express = bool(order.get("express", False))
    if express:
        base *= 1.5
    net = base + surcharge

    vat = 0.0 if reverse_charge(country, business) else STANDARD_VAT[code]
    price = round_money(net * (1.0 + vat))
    order_date = str(order["date"])
    if express and is_workday(date.fromisoformat(order_date)):
        delivery = order_date
    else:
        delivery = next_workday(order_date)
    return price, delivery


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.read())
    depot: dict[str, Any] = data["depot"]
    catalog: dict[str, float] = {
        str(name): float(weight) for name, weight in data["catalog"].items()
    }

    rate_sek_per_eur = float(data["rates"]["EUR"])
    quotes: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for order in data["orders"]:
        order_id = str(order["id"])
        result = quote_order(order, depot, catalog)
        if result is None:
            unknown.append(order_id)
        else:
            price_sek, delivery = result
            code = normalise_country(str(order["country"]))
            if code == "SE":
                quotes[order_id] = {"price": price_sek, "delivery": delivery, "currency": "SEK"}
            else:
                price_eur = round_money(price_sek / rate_sek_per_eur)
                quotes[order_id] = {"price": price_eur, "delivery": delivery, "currency": "EUR"}

    output: dict[str, Any] = {"quotes": quotes, "unknown": sorted(unknown)}
    sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
