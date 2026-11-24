"""Parcel shipping quotes for a furniture shop.

Reads one JSON line from stdin and writes one JSON line to stdout:
    {"orders": [...], "catalog": {...}}  ->  {"quotes": {...}, "unknown": [...]}
"""

from __future__ import annotations

import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

import tariff

MAX_MATCH_DISTANCE: Final[int] = 2
EXPRESS_FEE_SEK: Final[Decimal] = Decimal("50")
ZONE4_FUEL_SURCHARGE_SEK: Final[Decimal] = Decimal("30")
FUEL_SURCHARGE_ZONE: Final[int] = 4
VAT_FACTOR: Final[Decimal] = Decimal("1.25")
CENT: Final[Decimal] = Decimal("0.01")
HEAVY_PARCEL_KG: Final[Decimal] = Decimal("20")
HEAVY_PARCEL_DISCOUNT: Final[Decimal] = Decimal("0.90")


def levenshtein(a: str, b: str) -> int:
    """Classic edit distance (insert, delete, substitute each cost 1)."""
    if len(a) < len(b):
        a, b = b, a
    previous: list[int] = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current: list[int] = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            )
        previous = current
    return previous[-1]


def match_product(name: str, catalog: dict[str, float]) -> str | None:
    """Closest catalog name within MAX_MATCH_DISTANCE; ties go to the alphabetically first name."""
    best: str | None = None
    best_distance = MAX_MATCH_DISTANCE + 1
    for candidate in sorted(catalog):
        distance = levenshtein(name, candidate)
        if distance < best_distance:
            best, best_distance = candidate, distance
    return best


def carrier_price_ex_vat(zone: int, weight_kg: float) -> Decimal:
    """Carrier price excluding VAT.

    tariff >= 2.0.0 returns base_price() including 25 % VAT, rounded to cents.
    Dividing by 1.25 and rounding to cents recovers the excl-VAT price.
    """
    incl_vat = Decimal(str(tariff.base_price(zone, weight_kg)))
    return (incl_vat / VAT_FACTOR).quantize(CENT, rounding=ROUND_HALF_UP)


def quote_sek(weight_kg: float, zone: int, express: bool) -> float:
    """Carrier price (ex VAT) + express fee + zone 4 fuel surcharge, then 25 % VAT.

    Parcels over 20 kg get 10 % off the final (incl. VAT) quote. Rounded to cents last.
    """
    carrier = carrier_price_ex_vat(zone, weight_kg)
    net = carrier + (EXPRESS_FEE_SEK if express else Decimal(0))
    if zone == FUEL_SURCHARGE_ZONE:
        net += ZONE4_FUEL_SURCHARGE_SEK
    gross = net * VAT_FACTOR
    if Decimal(str(weight_kg)) > HEAVY_PARCEL_KG:
        gross *= HEAVY_PARCEL_DISCOUNT
    return float(gross.quantize(CENT, rounding=ROUND_HALF_UP))


def process(payload: dict[str, Any]) -> dict[str, Any]:
    catalog: dict[str, float] = {
        str(name): float(weight) for name, weight in (payload.get("catalog") or {}).items()
    }
    quotes: dict[str, float] = {}
    unknown: set[str] = set()

    for order in payload.get("orders") or []:
        order_id = str(order["id"])

        product = match_product(str(order.get("product", "")), catalog)
        if product is None:
            unknown.add(order_id)
            continue

        try:
            zone = tariff.zone(str(order.get("country", "")))
        except KeyError:
            unknown.add(order_id)
            continue

        express = bool(order.get("express", False))
        qty = float(order.get("qty", 1))
        weight_kg = qty * catalog[product]
        quotes[order_id] = quote_sek(weight_kg, zone, express)

    for order_id in unknown:
        quotes.pop(order_id, None)

    return {"quotes": quotes, "unknown": sorted(unknown)}


def main() -> None:
    payload: dict[str, Any] = json.loads(sys.stdin.read())
    sys.stdout.write(json.dumps(process(payload)) + "\n")


if __name__ == "__main__":
    main()
