"""Net line amounts after discounts."""
from dataclasses import dataclass

from .catalog import Product
from .customers import Customer

MEMBER_DISCOUNT = 0.10
VOLUME_DISCOUNT = 0.05
VOLUME_THRESHOLD = 10


@dataclass(frozen=True)
class Line:
    product: Product
    qty: int
    net_sek: float  # after discounts, excluding VAT


def discount_rate(customer: Customer, qty: int) -> float:
    rate = MEMBER_DISCOUNT if customer.member else 0.0
    if qty >= VOLUME_THRESHOLD:
        rate += VOLUME_DISCOUNT
    return rate


def price_line(product: Product, qty: int, customer: Customer) -> Line:
    gross_net = product.price_sek * qty
    return Line(product, qty, gross_net * (1 - discount_rate(customer, qty)))
