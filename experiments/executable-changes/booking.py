free_entry = {(True, "sat")}


def price(child, day):
    return 0 if (child, day) in free_entry else 100


def total(child, day, previous):
    return previous + price(child, day)


def seats(child, day, available):
    return available - 1


def recipient(child, day, gift):
    return "buyer" if gift else "guest"
