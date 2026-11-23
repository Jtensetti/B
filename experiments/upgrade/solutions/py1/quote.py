"""Parcel shipping quotes for a furniture shop.

Reads one line of JSON from stdin:
    {"orders": [{"id": ..., "product": ..., "country": ..., "express": bool?}, ...],
     "catalog": {"<product name>": <weight kg>, ...}}

Writes one line of JSON to stdout:
    {"quotes": {"<id>": <price SEK incl. VAT>, ...}, "unknown": [<ids>, sorted]}
"""

from __future__ import annotations

import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import tariff

MAX_NAME_DISTANCE: int = 2
EXPRESS_FEE_SEK: Decimal = Decimal("50")
ZONE4_FUEL_SURCHARGE_SEK: Decimal = Decimal("30")
VAT_FACTOR: Decimal = Decimal("1.25")
# tariff.base_price() includes VAT since tariff 2.0.0; 1 / 1.25 converts it back exactly.
VAT_DIVISOR_INVERSE: Decimal = Decimal("0.8")
HEAVY_PARCEL_KG: float = 20.0
HEAVY_PARCEL_DISCOUNT_FACTOR: Decimal = Decimal("0.9")  # 10 % off the quote incl. VAT
CENT: Decimal = Decimal("0.01")


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings (insert, delete, substitute)."""
    if len(a) < len(b):
        a, b = b, a
    previous: list[int] = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current: list[int] = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + cost,
                )
            )
        previous = current
    return previous[-1]


def match_product(name: str, catalog: dict[str, float]) -> str | None:
    """Catalog name closest to `name` (distance <= 2), ties to the alphabetically first."""
    best_name: str | None = None
    best_distance: int = MAX_NAME_DISTANCE + 1
    for candidate in sorted(catalog):
        distance = levenshtein(name, candidate)
        if distance < best_distance:
            best_name = candidate
            best_distance = distance
    return best_name


def price_incl_vat(weight_kg: float, zone: int, express: bool) -> Decimal:
    """Carrier price + express fee + zone 4 fuel surcharge, then 25 % VAT, rounded to 2 decimals."""
    carrier_incl_vat = Decimal(str(tariff.base_price(zone, weight_kg)))
    ex_vat = carrier_incl_vat * VAT_DIVISOR_INVERSE
    if express:
        ex_vat += EXPRESS_FEE_SEK
    if zone == 4:
        ex_vat += ZONE4_FUEL_SURCHARGE_SEK
    gross = ex_vat * VAT_FACTOR
    if weight_kg > HEAVY_PARCEL_KG:
        gross *= HEAVY_PARCEL_DISCOUNT_FACTOR
    return gross.quantize(CENT, rounding=ROUND_HALF_UP)


def quote(request: dict[str, Any]) -> dict[str, Any]:
    catalog: dict[str, float] = request.get("catalog") or {}
    quotes: dict[str, float] = {}
    unknown: list[str] = []

    for order in request.get("orders") or []:
        order_id = str(order["id"])

        product = match_product(str(order.get("product") or ""), catalog)
        if product is None:
            unknown.append(order_id)
            continue

        try:
            zone = tariff.zone(str(order.get("country") or ""))
        except KeyError:
            unknown.append(order_id)
            continue

        qty = order.get("qty")
        quantity = 1 if qty is None else qty

        price = price_incl_vat(
            weight_kg=quantity * catalog[product],
            zone=zone,
            express=bool(order.get("express", False)),
        )
        quotes[order_id] = float(price)

    return {"quotes": quotes, "unknown": sorted(unknown)}


def main() -> None:
    request = json.loads(sys.stdin.read())
    print(json.dumps(quote(request)))


if __name__ == "__main__":
    main()
