"""Quote parcel shipping for a furniture shop.

Reads one line of JSON on stdin:
    {"orders": [{"id": str, "product": str, "country": str, "express": bool?}, ...],
     "catalog": {"<product name>": weight_kg, ...}}

Writes one line of JSON on stdout:
    {"quotes": {"<id>": price_sek_incl_vat, ...}, "unknown": [sorted ids]}
"""

from __future__ import annotations

import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import tariff

MAX_FUZZY_DISTANCE = 2
EXPRESS_FEE_SEK = Decimal("50")
ZONE_4_FUEL_SURCHARGE_SEK = Decimal("30")  # excluding VAT, like the express fee
VAT_MULTIPLIER = Decimal("1.25")  # 25 % VAT on top of the ex-VAT sum
CARRIER_VAT_FACTOR = Decimal("0.8")  # 1 / VAT_MULTIPLIER: strips VAT from tariff 2.0 prices
CENT = Decimal("0.01")
HEAVY_PARCEL_KG = 20.0  # parcels heavier than this get a discount on the quote
HEAVY_PARCEL_FACTOR = Decimal("0.9")  # 10 % off the final price incl. VAT


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings (insert, delete, substitute cost 1)."""
    if len(a) < len(b):
        a, b = b, a
    previous: list[int] = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current: list[int] = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(
                    previous[j] + 1,        # deletion
                    current[j - 1] + 1,     # insertion
                    previous[j - 1] + cost,  # substitution
                )
            )
        previous = current
    return previous[-1]


def resolve_product(product: str, catalog: dict[str, float]) -> str | None:
    """Return the catalog name closest to `product` if within the fuzzy limit.

    Ties go to the alphabetically first name; iterating the sorted names and
    keeping only strictly better matches gives that behaviour.
    """
    best_name: str | None = None
    best_distance = MAX_FUZZY_DISTANCE + 1
    for name in sorted(catalog):
        distance = levenshtein(product, name)
        if distance < best_distance:
            best_distance = distance
            best_name = name
    return best_name


def quote_sek(country: str, weight_kg: float, express: bool) -> Decimal | None:
    """Customer price in SEK incl. VAT, or None if the carrier does not serve the country."""
    try:
        zone = tariff.zone(country)
    except KeyError:
        return None
    # Since tariff 2.0.0, base_price() includes 25 % VAT. Remove it here: dividing
    # by 1.25 equals multiplying by 0.8, which is exact for a 2-decimal amount,
    # so no rounding error is introduced before the fees and VAT are applied.
    carrier_incl_vat = Decimal(str(tariff.base_price(zone, weight_kg)))
    carrier_ex_vat = carrier_incl_vat * CARRIER_VAT_FACTOR
    ex_vat = carrier_ex_vat + (EXPRESS_FEE_SEK if express else Decimal(0))
    if zone == 4:
        ex_vat += ZONE_4_FUEL_SURCHARGE_SEK
    return (ex_vat * VAT_MULTIPLIER).quantize(CENT, rounding=ROUND_HALF_UP)


def build_quotes(request: dict[str, Any]) -> dict[str, Any]:
    catalog: dict[str, float] = request.get("catalog", {})
    quotes: dict[str, float] = {}
    unknown: list[str] = []

    for order in request.get("orders", []):
        order_id: str = order["id"]
        product: str = order.get("product", "")
        country: str = order.get("country", "")
        express: bool = bool(order.get("express", False))
        qty: float = float(order.get("qty", 1))

        name = resolve_product(product, catalog)
        if name is None:
            unknown.append(order_id)
            continue

        weight_kg = qty * float(catalog[name])
        price = quote_sek(country, weight_kg, express)
        if price is None:
            unknown.append(order_id)
            continue

        if weight_kg > HEAVY_PARCEL_KG:
            price = (price * HEAVY_PARCEL_FACTOR).quantize(CENT, rounding=ROUND_HALF_UP)

        quotes[order_id] = float(price)

    return {"quotes": quotes, "unknown": sorted(unknown)}


def main() -> None:
    request: dict[str, Any] = json.loads(sys.stdin.read())
    sys.stdout.write(json.dumps(build_quotes(request)) + "\n")


if __name__ == "__main__":
    main()
