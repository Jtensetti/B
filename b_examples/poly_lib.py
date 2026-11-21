"""Small real Python library for exercising B's v0.4 boundary contracts."""


def describe(value: int | str) -> int | str:
    if type(value) is int:
        return value + 1
    if type(value) is str:
        return value.upper()
    raise TypeError('unsupported value')


def find_code(name: str) -> int | None:
    return {"Ada": 42, "Maja": 7}.get(name)


def adjust(data: dict[str, float]) -> dict[str, float]:
    return {k: v * 2 for k, v in data.items()}


def broken(name: str) -> dict[str, int]:
    """Intentionally violates its stub to demonstrate runtime boundary defense."""
    return {"name": name}  # type: ignore[return-value]
