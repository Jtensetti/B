"""tariff 2.0.0: parcel tariffs for Nordic and European carriers."""

__version__ = "2.0.0"

VAT = 0.25

_ZONES = {"SE": 1, "NO": 2, "DK": 2, "FI": 2, "IS": 2, "DE": 3, "PL": 3, "NL": 3, "US": 4, "GB": 4}
_START = {1: 39.0, 2: 59.0, 3: 79.0, 4: 149.0}
_PER_KG = {1: 12.0, 2: 18.0, 3: 25.0, 4: 60.0}


def zone(country: str) -> int:
    """Tariff zone (1-4) for an ISO country code. Raises KeyError for countries not served."""
    return _ZONES[country.strip().upper()]


def base_price(zone: int, weight_kg: float) -> float:
    """Price in SEK for a parcel of the given weight to the given zone."""
    return round((_START[zone] + _PER_KG[zone] * weight_kg) * (1 + VAT), 2)
