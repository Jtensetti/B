discard: set[tuple[str, str]] = {("probe", "setup")}


def contribution(sensor: str, phase: str, value: int) -> int:
    return 0 if (sensor, phase) in discard else value


def integrated(sensor: str, phase: str, value: int, previous: int) -> int:
    return previous + contribution(sensor, phase, value)


def samples(sensor: str, phase: str, previous: int) -> int:
    return previous + 1


def channel(sensor: str, phase: str) -> str:
    return sensor
