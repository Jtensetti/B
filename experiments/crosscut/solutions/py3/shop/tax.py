"""VAT per class."""
from collections import defaultdict

from .catalog import vat_rate
from .pricing import Line


def vat_by_class(lines: list[Line], country: str) -> dict[str, float]:
    # Every class that appears on the invoice gets an entry, even when its VAT is 0.
    totals: dict[str, float] = defaultdict(float)
    for line in lines:
        totals[line.product.vat_class] += line.net_sek * vat_rate(country, line.product.vat_class)
    return dict(totals)
