"""VAT per class."""
from collections import defaultdict

from .pricing import Line


def vat_by_class(lines: list[Line]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for line in lines:
        totals[line.product.vat_class] += line.net_sek * line.product.vat_rate
    return dict(totals)
