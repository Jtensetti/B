import tariff


def zone_or_none(country):
    try:
        return tariff.zone(country)
    except KeyError:
        return None
