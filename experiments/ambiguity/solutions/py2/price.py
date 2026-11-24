import json
import sys
from typing import Any

TICKET_PRICE: int = 100
BOOKING_FEE: int = 15
MEMBER_DISCOUNT_PERCENT: int = 10


def booking_total(booking: dict[str, Any]) -> int:
    """Return the price in kr for one booking."""
    child: bool = bool(booking["child"])
    day: str = str(booking["day"])
    member: bool = bool(booking["member"])

    if child and day in ("sat", "sun"):
        return 0

    ticket: int = TICKET_PRICE
    if member:
        ticket = ticket * (100 - MEMBER_DISCOUNT_PERCENT) // 100
    ticket = max(0, ticket)
    return ticket + BOOKING_FEE


def main() -> None:
    data: dict[str, Any] = json.load(sys.stdin)
    totals: dict[str, int] = {}
    for booking in data["bookings"]:
        key: str = str(booking["id"])
        totals[key] = totals.get(key, 0) + booking_total(booking)
    json.dump({"totals": totals}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
