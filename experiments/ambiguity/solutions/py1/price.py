"""Compute booking totals in kr from one line of JSON on stdin."""

import json
import sys
from typing import Any

TICKET_PRICE: int = 100
BOOKING_FEE: int = 15
MEMBER_DISCOUNT_PERCENT: int = 10


def booking_total(booking: dict[str, Any]) -> int:
    """Return the cost in kr of a single booking."""
    is_child: bool = bool(booking["child"])
    is_member: bool = bool(booking["member"])
    is_free_day: bool = booking["day"] in ("sat", "sun")

    if is_child and is_free_day:
        return 0

    ticket: int = TICKET_PRICE
    if is_member:
        ticket = max(0, ticket - ticket * MEMBER_DISCOUNT_PERCENT // 100)
    return ticket + BOOKING_FEE


def compute_totals(data: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Sum booking totals per booking id."""
    totals: dict[str, int] = {}
    for booking in data["bookings"]:
        bid: str = str(booking["id"])
        totals[bid] = totals.get(bid, 0) + booking_total(booking)
    return {"totals": totals}


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.readline())
    sys.stdout.write(json.dumps(compute_totals(data)) + "\n")


if __name__ == "__main__":
    main()
