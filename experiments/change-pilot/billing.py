def billable(extra: int) -> int:
    assert extra >= 0
    result = extra + 1
    assert result > 0
    return result


def rate(total: int, extra: int) -> float:
    assert extra >= 0
    return total / billable(extra)


def carry(total: int, extra: int) -> int:
    assert extra >= 0
    return total % billable(extra)


def label(extra: int) -> int:
    assert extra >= 0
    return 1000 + billable(extra)


def fee(net: int) -> int:
    return net * 3 + 2
