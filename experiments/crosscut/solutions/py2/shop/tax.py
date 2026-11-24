"""VAT per class."""
from collections import defaultdict

from .catalog import VAT_RATES
from .pricing import Line

# Norwegian customers pay Norwegian VAT. Classes not listed here use the Swedish rates.
VAT_RATES_BY_COUNTRY: dict[str, dict[str, float]] = {
    "NO": {"standard": 0.25, "food": 0.15, "books": 0.0},
}


def vat_rates(country: str) -> dict[str, float]:
    return VAT_RATES_BY_COUNTRY.get(country, VAT_RATES)


def vat_by_class(lines: list[Line], rates: dict[str, float]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for line in lines:
        totals[line.product.vat_class] += line.net_sek * rates[line.product.vat_class]
    return dict(totals)
