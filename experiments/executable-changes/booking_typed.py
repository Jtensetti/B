free_entry: set[tuple[bool, str]] = {(True, "sat")}


def price(child: bool, day: str) -> int:
    return 0 if (child, day) in free_entry else 100


def total(child: bool, day: str, previous: int) -> int:
    return previous + price(child, day)


def seats(child: bool, day: str, available: int) -> int:
    return available - 1


def recipient(child: bool, day: str, gift: bool) -> str:
    return "buyer" if gift else "guest"
