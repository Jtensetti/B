"""The monthly report for the accountant, always in SEK."""
from collections import defaultdict
from typing import Any

from .invoice import Invoice


def report(invoices: list[Invoice]) -> dict[str, Any]:
    net_by_class: dict[str, float] = defaultdict(float)
    vat_total = 0.0
    shipping = 0.0
    for inv in invoices:
        for line in inv.lines:
            net_by_class[line.product.vat_class] += line.net_sek
        vat_total += sum(inv.vat_sek.values())
        shipping += inv.shipping_sek
    revenue = sum(net_by_class.values()) + shipping + vat_total
    return {
        "net_by_class": {k: round(v, 2) for k, v in sorted(net_by_class.items())},
        "shipping": round(shipping, 2),
        "vat": round(vat_total, 2),
        "revenue": round(revenue, 2),
    }
