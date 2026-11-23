"""Compute booking totals from a JSON description on standard input.

Pricing rules:
- A ticket costs 100 kr and every booking has a 15 kr booking fee.
- Children pay no ticket and no booking fee on Saturdays and Sundays.
- Members get 10 percent off the ticket, but the ticket never goes below 0.
"""

import json
import sys
from typing import Any

TICKET_PRICE: int = 100
BOOKING_FEE: int = 15
MEMBER_DISCOUNT_PERCENT: int = 10


def booking_total(child: bool, day: str, member: bool) -> int:
    """Return the total in kr for a single booking."""
    if child and day in ("sat", "sun"):
        return 0

    ticket = TICKET_PRICE
    if member:
        ticket = max(0, ticket - ticket * MEMBER_DISCOUNT_PERCENT // 100)
    return ticket + BOOKING_FEE


def compute_totals(data: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Return {"totals": {id: total}} for all bookings.

    If the same id appears more than once, its totals are summed.
    """
    totals: dict[str, int] = {}
    for booking in data["bookings"]:
        booking_id = str(booking["id"])
        amount = booking_total(
            bool(booking["child"]),
            str(booking["day"]),
            bool(booking["member"]),
        )
        totals[booking_id] = totals.get(booking_id, 0) + amount
    return {"totals": totals}


def main() -> None:
    data = json.loads(sys.stdin.readline())
    sys.stdout.write(json.dumps(compute_totals(data)) + "\n")


if __name__ == "__main__":
    main()
