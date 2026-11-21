"""A plain Python library consumed from B without any handwritten foreign signature."""


def clamp(value: float, low: float, high: float) -> float:
    if low > high:
        raise ValueError("low cannot exceed high")
    return max(low, min(value, high))


def weighted_mean(values: list[float], weights: list[float]) -> float:
    if len(values) != len(weights) or not values:
        raise ValueError("values and weights must be nonempty and equal-length")
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def repeat(text: str, times: int = 1) -> str:
    return text * times
