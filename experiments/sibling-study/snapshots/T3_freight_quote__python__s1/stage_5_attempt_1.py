from __future__ import annotations

from dataclasses import dataclass
import json
import math
import posixpath
import re
import sys


DEPOT_PATTERN: re.Pattern[str] = re.compile(r"^[a-z]{3}-[0-9]{2}\Z")
VALID_ZONES: frozenset[str] = frozenset({"SE", "EU", "NON-EU"})


@dataclass(frozen=True)
class LegInput:
    route: str
    dx_km: float
    dy_km: float
    weight_g: float
    zone: str


@dataclass(frozen=True)
class QuoteInput:
    eur_to_sek: float
    max_sek: int
    legs: tuple[LegInput, ...]


@dataclass(frozen=True)
class QuoteOutput:
    legs: int
    valid_legs: int
    total_m: int
    total_eur_cents: int
    total_sek: int
    heavy_legs: int
    customs_legs: int
    long_haul_pairs: int
    vip_exempt: int
    within_cap: bool
    max_leg_eur_cents: int

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "legs": self.legs,
            "valid_legs": self.valid_legs,
            "total_m": self.total_m,
            "total_eur_cents": self.total_eur_cents,
            "total_sek": self.total_sek,
            "heavy_legs": self.heavy_legs,
            "customs_legs": self.customs_legs,
            "long_haul_pairs": self.long_haul_pairs,
            "vip_exempt": self.vip_exempt,
            "within_cap": self.within_cap,
            "max_leg_eur_cents": self.max_leg_eur_cents,
        }


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("Expected string object key")
        result[key] = item
    return result


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Expected JSON array")
    result: list[object] = []
    for item in value:
        result.append(item)
    return result


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected string")
    return value


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected number")
    return float(value)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Expected integer")
    return value


def parse_input(raw: object) -> QuoteInput:
    data = _as_dict(raw)
    eur_to_sek = _as_float(data["eur_to_sek"])
    max_sek = _as_int(data["max_sek"])
    raw_legs = _as_list(data["legs"])
    legs: list[LegInput] = []
    for raw_leg in raw_legs:
        leg_obj = _as_dict(raw_leg)
        legs.append(
            LegInput(
                route=_as_str(leg_obj["route"]),
                dx_km=_as_float(leg_obj["dx_km"]),
                dy_km=_as_float(leg_obj["dy_km"]),
                weight_g=_as_float(leg_obj["weight_g"]),
                zone=_as_str(leg_obj["zone"]),
            )
        )
    return QuoteInput(eur_to_sek=eur_to_sek, max_sek=max_sek, legs=tuple(legs))


def normalize_depot(route: str) -> str:
    norm = posixpath.normpath(route)
    return posixpath.basename(norm)


def normalize_zone(zone: str) -> str:
    return zone.strip().upper()


def is_valid_leg(depot: str, zone: str) -> bool:
    return DEPOT_PATTERN.match(depot) is not None and zone in VALID_ZONES


def distance_multiplier(km: float) -> float:
    if km <= 50.0:
        return 1.0
    if km <= 200.0:
        return 1.15
    return 1.35


def apply_zone_adjustment(leg_eur: float, zone: str) -> float:
    if zone == "SE":
        return leg_eur * 0.9
    if zone == "NON-EU":
        return leg_eur + 15.0
    return leg_eur


def compute_quote(quote_input: QuoteInput) -> QuoteOutput:
    valid_legs = 0
    heavy_legs = 0
    customs_legs = 0
    long_haul_pairs = 0
    vip_exempt = 0
    max_leg_eur_cents = 0
    prev_long_haul = False
    total_km = 0.0
    total_eur = 0.0

    for leg in quote_input.legs:
        depot = normalize_depot(leg.route)
        zone = normalize_zone(leg.zone)
        if not is_valid_leg(depot, zone):
            continue

        valid_legs += 1
        km = math.sqrt(leg.dx_km * leg.dx_km + leg.dy_km * leg.dy_km)
        kg = leg.weight_g / 1000.0
        base_eur = 5.0 + 0.5 * km + 2.0 * kg
        leg_eur = base_eur * distance_multiplier(km)
        if kg >= 10.0:
            heavy_legs += 1
            if depot == "sto-01" and zone == "SE":
                vip_exempt += 1
            else:
                leg_eur += 12.0
        if zone == "NON-EU":
            customs_legs += 1
        leg_eur = apply_zone_adjustment(leg_eur, zone)

        leg_eur_cents = round(leg_eur * 100.0)
        if valid_legs == 1 or leg_eur_cents > max_leg_eur_cents:
            max_leg_eur_cents = leg_eur_cents

        is_long_haul = km > 100.0
        if prev_long_haul and is_long_haul:
            long_haul_pairs += 1
        prev_long_haul = is_long_haul

        total_km += km
        total_eur += leg_eur

    total_eur += 25.0 * long_haul_pairs
    total_sek = round(total_eur * quote_input.eur_to_sek)

    return QuoteOutput(
        legs=len(quote_input.legs),
        valid_legs=valid_legs,
        total_m=round(total_km * 1000.0),
        total_eur_cents=round(total_eur * 100.0),
        total_sek=total_sek,
        heavy_legs=heavy_legs,
        customs_legs=customs_legs,
        long_haul_pairs=long_haul_pairs,
        vip_exempt=vip_exempt,
        within_cap=total_sek <= quote_input.max_sek,
        max_leg_eur_cents=max_leg_eur_cents,
    )


def main() -> None:
    raw: object = json.load(sys.stdin)
    quote_input = parse_input(raw)
    quote_output = compute_quote(quote_input)
    print(json.dumps(quote_output.to_dict()))


if __name__ == "__main__":
    main()
