"""Catalog entries as read from the input."""
from dataclasses import dataclass
from typing import Any

VAT_RATES: dict[str, float] = {"standard": 0.25, "food": 0.12, "books": 0.06}


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_sek: float  # net price per unit, excluding VAT
    vat_class: str

    @property
    def vat_rate(self) -> float:
        return VAT_RATES[self.vat_class]


def load_catalog(raw: dict[str, dict[str, Any]]) -> dict[str, Product]:
    # The catalog price includes Swedish VAT, so the net unit price is price / (1 + rate).
    return {sku: Product(sku, str(row["name"]), float(row["price"]) / (1 + VAT_RATES[str(row["vat_class"])]),
                         str(row["vat_class"]))
            for sku, row in raw.items()}
