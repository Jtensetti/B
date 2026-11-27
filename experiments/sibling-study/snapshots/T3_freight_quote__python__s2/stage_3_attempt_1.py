from __future__ import annotations

from dataclasses import dataclass
import json
import math
import posixpath
import re
import sys
from typing import Any

DEPOT_PATTERN = re.compile(r"[a-z]{3}-[0-9]{2}", re.ASCII)
VALID_ZONES = frozenset({"SE", "EU", "NON-EU"})


@dataclass(frozen=True)
class LegInput:
    route: str
    dx_km: float
    dy_km: float
    weight_g: float
    zone: str


@dataclass(frozen=True)
class ValidLeg:
    depot: str
    zone: str
    km: float
    kg: float
    is_heavy: bool
    eur: float


def normalize_depot(route: str) -> str:
    normalized = posixpath.normpath(route)
    return posixpath.basename(normalized)


def normalize_zone(zone: str) -> str:
    return zone.strip().upper()


def distance_multiplier(km: float) -> float:
    if km <= 50.0:
        return 1.0
    if km <= 200.0:
        return 1.15
    return 1.35


def apply_zone_adjustment(eur: float, zone: str) -> float:
    if zone == "SE":
        return eur * 0.9
    if zone == "NON-EU":
        return eur + 15.0
    return eur


def parse_valid_leg(leg: LegInput) -> ValidLeg | None:
    depot = normalize_depot(leg.route)
    zone = normalize_zone(leg.zone)
    if DEPOT_PATTERN.fullmatch(depot) is None or zone not in VALID_ZONES:
        return None
    km = math.sqrt(leg.dx_km * leg.dx_km + leg.dy_km * leg.dy_km)
    kg = leg.weight_g / 1000.0
    base_eur = 5.0 + 0.5 * km + 2.0 * kg
    is_heavy = kg >= 10.0
    eur = base_eur * distance_multiplier(km) + (12.0 if is_heavy else 0.0)
    eur = apply_zone_adjustment(eur, zone)
    return ValidLeg(depot=depot, zone=zone, km=km, kg=kg, is_heavy=is_heavy, eur=eur)


def parse_input(payload: dict[str, Any]) -> tuple[float, list[LegInput]]:
    eur_to_sek = float(payload["eur_to_sek"])
    raw_legs: list[dict[str, Any]] = payload["legs"]
    legs = [
        LegInput(
            route=str(item["route"]),
            dx_km=float(item["dx_km"]),
            dy_km=float(item["dy_km"]),
            weight_g=float(item["weight_g"]),
            zone=str(item["zone"]),
        )
        for item in raw_legs
    ]
    return eur_to_sek, legs


def compute_quote(eur_to_sek: float, legs: list[LegInput]) -> dict[str, int]:
    total_km = 0.0
    total_eur = 0.0
    valid_count = 0
    heavy_count = 0
    customs_count = 0
    long_haul_pairs = 0
    prev_long_haul = False

    for leg in legs:
        parsed = parse_valid_leg(leg)
        if parsed is None:
            continue
        valid_count += 1
        if parsed.is_heavy:
            heavy_count += 1
        if parsed.zone == "NON-EU":
            customs_count += 1
        is_long_haul = parsed.km > 100.0
        if prev_long_haul and is_long_haul:
            long_haul_pairs += 1
        prev_long_haul = is_long_haul
        total_km += parsed.km
        total_eur += parsed.eur

    total_eur += 25.0 * long_haul_pairs

    return {
        "legs": len(legs),
        "valid_legs": valid_count,
        "total_m": round(total_km * 1000.0),
        "total_eur_cents": round(total_eur * 100.0),
        "total_sek": round(total_eur * eur_to_sek),
        "heavy_legs": heavy_count,
        "customs_legs": customs_count,
        "long_haul_pairs": long_haul_pairs,
    }


def main() -> None:
    payload: dict[str, Any] = json.loads(sys.stdin.read())
    eur_to_sek, legs = parse_input(payload)
    result = compute_quote(eur_to_sek, legs)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
