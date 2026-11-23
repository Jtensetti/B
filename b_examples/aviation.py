"""A small library in imperial aviation units, standing in for a real dependency."""


def takeoff_distance(speed_knots: float, weight_lb: float) -> float:
    """Ground roll in feet for a light aircraft (illustrative formula)."""
    return 0.0004 * weight_lb * (speed_knots / 60.0) ** 2 * 10.0


def fuel_burn(hours: float) -> float:
    """US gallons of fuel burned per flight time in hours."""
    return 9.5 * hours
