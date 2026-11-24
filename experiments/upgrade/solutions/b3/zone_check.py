import tariff


def served(country: str) -> bool:
    try:
        tariff.zone(country)
        return True
    except KeyError:
        return False
