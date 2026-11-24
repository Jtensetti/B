"""Catalog entries as read from the input."""
from dataclasses import dataclass
from typing import Any

VAT_RATES: dict[str, dict[str, float]] = {
    "SE": {"standard": 0.25, "food": 0.12, "books": 0.06},
    "NO": {"standard": 0.25, "food": 0.15, "books": 0.0},
}


def vat_rate(country: str, vat_class: str) -> float:
    # Countries without their own table are taxed as Sweden, as before.
    return VAT_RATES.get(country, VAT_RATES["SE"])[vat_class]


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_sek: float  # net price per unit, excluding VAT
    vat_class: str


def load_catalog(raw: dict[str, dict[str, Any]]) -> dict[str, Product]:
    # Catalog prices include Swedish VAT, so the net unit price is price / (1 + SE rate).
    return {sku: Product(sku, str(row["name"]),
                         float(row["price"]) / (1 + vat_rate("SE", str(row["vat_class"]))),
                         str(row["vat_class"]))
            for sku, row in raw.items()}
