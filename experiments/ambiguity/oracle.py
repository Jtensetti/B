"""The owner's intent for the ambiguity trial, fixed in PREREGISTRATION.md."""
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def total(child: bool, day: str, member: bool, change: int) -> int:
    free = child and (day == "sat" or (change >= 1 and day == "sun"))
    if free:
        return 0
    fee = 15 if change >= 2 else 10
    if member:
        ticket = 90 if change >= 3 else max(100 - 20, 0)
    else:
        ticket = 100
    return ticket + fee


def bookings():
    return [{"id": f"{'c' if c else 'a'}-{d}-{'m' if m else 'n'}", "child": c, "day": d, "member": m}
            for c in (False, True) for d in DAYS for m in (False, True)]


def expected(change: int) -> dict:
    return {b["id"]: total(b["child"], b["day"], b["member"], change) for b in bookings()}
