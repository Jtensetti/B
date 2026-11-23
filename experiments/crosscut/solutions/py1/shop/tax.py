"""VAT per class."""
from collections import defaultdict

from .catalog import VAT_RATES
from .customers import Customer
from .pricing import Line

# Norwegian VAT. Every class is listed on a Norwegian invoice, even at 0.
NO_VAT_RATES: dict[str, float] = {"standard": 0.25, "food": 0.15, "books": 0.0}


def vat_rates(customer: Customer) -> dict[str, float]:
    return NO_VAT_RATES if customer.country == "NO" else VAT_RATES


def vat_by_class(lines: list[Line], customer: Customer) -> dict[str, float]:
    rates = vat_rates(customer)
    totals: dict[str, float] = defaultdict(float)
    if customer.country == "NO":
        for vat_class in rates:
            totals[vat_class] = 0.0
    for line in lines:
        totals[line.product.vat_class] += line.net_sek * rates[line.product.vat_class]
    return dict(totals)
