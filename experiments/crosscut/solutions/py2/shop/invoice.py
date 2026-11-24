"""One invoice per order."""
from dataclasses import dataclass, field
from typing import Any

from .catalog import Product
from .customers import Customer
from .pricing import Line, price_line
from .tax import vat_by_class, vat_rates

SHIPPING_SEK = 49.0
FREE_SHIPPING_FROM_SEK = 500.0  # net order value


@dataclass
class Invoice:
    order_id: str
    customer: Customer
    lines: list[Line]
    shipping_sek: float
    vat_sek: dict[str, float] = field(default_factory=dict)

    @property
    def net_sek(self) -> float:
        return sum(line.net_sek for line in self.lines) + self.shipping_sek

    @property
    def total_sek(self) -> float:
        return self.net_sek + sum(self.vat_sek.values())


def make_invoice(order: dict[str, Any], catalog: dict[str, Product], customers: dict[str, Customer]) -> Invoice:
    customer = customers[str(order["customer"])]
    lines = [price_line(catalog[str(l["sku"])], int(l["qty"]), customer) for l in order["lines"]]
    goods = sum(line.net_sek for line in lines)
    shipping = 0.0 if goods >= FREE_SHIPPING_FROM_SEK else SHIPPING_SEK
    rates = vat_rates(customer.country)
    vat = vat_by_class(lines, rates)
    # Shipping is taxed at the standard rate.
    if shipping:
        vat["standard"] = vat.get("standard", 0.0) + shipping * rates["standard"]
    return Invoice(str(order["id"]), customer, lines, shipping, vat)


def invoice_json(invoice: Invoice, rates: dict[str, float]) -> dict[str, Any]:
    """Invoice amounts in the customer's currency.

    Norwegian customers are invoiced in NOK. ``rates["NOK"]`` is the value of
    1 NOK in SEK, so SEK amounts are divided by it. Everything else stays in SEK.
    """
    if invoice.customer.country == "NO":
        sek_per_unit = rates["NOK"]
        currency = "NOK"
    else:
        sek_per_unit = 1.0
        currency = "SEK"

    def money(sek: float) -> float:
        return round(sek / sek_per_unit, 2)

    return {
        "currency": currency,
        "net": money(invoice.net_sek),
        "vat": {k: money(v) for k, v in sorted(invoice.vat_sek.items())},
        "total": money(invoice.total_sek),
    }
