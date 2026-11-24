"""One invoice per order."""
from dataclasses import dataclass, field
from typing import Any

from .catalog import Product, vat_rate
from .customers import Customer
from .pricing import Line, price_line
from .tax import vat_by_class

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
    vat = vat_by_class(lines, customer.country)
    # Shipping is taxed at the standard rate.
    if shipping:
        vat["standard"] = vat.get("standard", 0.0) + shipping * vat_rate(customer.country, "standard")
    return Invoice(str(order["id"]), customer, lines, shipping, vat)


def invoice_json(invoice: Invoice, rates: dict[str, float]) -> dict[str, Any]:
    # Amounts are computed in SEK. Norwegian customers get their invoice in NOK;
    # rates["NOK"] is the value of 1 NOK in SEK, so SEK / rate gives NOK.
    if invoice.customer.country == "NO":
        currency = "NOK"
        rate = rates["NOK"]

        def convert(sek: float) -> float:
            return round(sek / rate, 2)
    else:
        currency = "SEK"

        def convert(sek: float) -> float:
            return round(sek, 2)

    return {
        "currency": currency,
        "net": convert(invoice.net_sek),
        "vat": {k: convert(v) for k, v in sorted(invoice.vat_sek.items())},
        "total": convert(invoice.total_sek),
    }
