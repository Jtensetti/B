discard = {("probe", "setup")}


def contribution(sensor, phase, value):
    return 0 if (sensor, phase) in discard else value


def integrated(sensor, phase, value, previous):
    return previous + contribution(sensor, phase, value)


def samples(sensor, phase, previous):
    return previous + 1


def channel(sensor, phase):
    return sensor
