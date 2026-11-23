"""A second small library, in feet and degrees Celsius."""


def density_altitude(elevation_ft: float, temperature_c: float) -> float:
    """Approximate density altitude in feet."""
    isa = 15.0 - 2.0 * elevation_ft / 1000.0
    return elevation_ft + 120.0 * (temperature_c - isa)
