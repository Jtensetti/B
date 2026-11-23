"""Helpers for quote.bee."""
from decimal import Decimal, ROUND_HALF_UP

import tariff


def zone_code(country):
    """Tariff zone for a country, or 0 when the carrier does not serve it."""
    try:
        zone = tariff.zone(country)
    except KeyError:
        return 0
    return zone or 0


def money(amount):
    """Round to 2 decimals, halves away from zero (2.675 -> 2.68)."""
    return float(Decimal(repr(float(amount))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def base_ex_vat(zone, weight_kg):
    """Carrier price in SEK excluding VAT. tariff 2.0 and later return the price including 25 % VAT."""
    price = tariff.base_price(zone, weight_kg)
    major = int(str(tariff.__version__).split(".")[0])
    if major >= 2:
        return money(price / (1 + tariff.VAT))
    return price
