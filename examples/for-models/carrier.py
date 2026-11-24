"""The carrier's quoting library. It works in pounds and US dollars."""
import math


def rate(weight_lb: float, express: bool) -> float:
    """Price in US dollars for one parcel. Weight is rounded up to a whole pound."""
    billable = max(1, math.ceil(weight_lb))
    price = 4.50 + 0.85 * billable
    if express:
        price *= 1.6
    return round(price, 2)
