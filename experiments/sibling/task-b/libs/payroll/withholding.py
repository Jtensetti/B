"""Preliminary tax withholding. Maintained by the finance team."""
import math


def withholding(gross: float, table: int) -> int:
    """Tax to withhold, in whole kronor (rounded down), from a monthly gross salary.

    The first 2000 SEK are tax free. Up to 50000 SEK the rate is the table number in percent
    (table 32 means 32 %). Above 50000 SEK another 20 percentage points are added.
    """
    rate = table / 100
    taxable = max(0.0, gross - 2000)
    low = min(taxable, 48000) * rate
    high = max(0.0, gross - 50000) * (rate + 0.20)
    return math.floor(low + high)
