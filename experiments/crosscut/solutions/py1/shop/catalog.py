"""Catalog entries as read from the input."""
from dataclasses import dataclass
from typing import Any

VAT_RATES: dict[str, float] = {"standard": 0.25, "food": 0.12, "books": 0.06}


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_sek: float  # net price per unit, excluding Swedish VAT
    vat_class: str

    @property
    def vat_rate(self) -> float:
        return VAT_RATES[self.vat_class]


def load_catalog(raw: dict[str, dict[str, Any]]) -> dict[str, Product]:
    """Catalog prices include Swedish VAT, so the net price is the price without it."""
    products: dict[str, Product] = {}
    for sku, row in raw.items():
        vat_class = str(row["vat_class"])
        net = float(row["price"]) / (1 + VAT_RATES[vat_class])
        products[sku] = Product(sku, str(row["name"]), net, vat_class)
    return products
