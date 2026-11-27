from __future__ import annotations

from dataclasses import dataclass
import json
import math
import posixpath
import re
import sys
from typing import Any

DEPOT_RE = re.compile(r"[a-z]{3}-[0-9]{2}", re.ASCII)
VALID_ZONES = frozenset({"SE", "EU", "NON-EU"})


@dataclass(frozen=True)
class LegInput:
    route: str
    dx_km: float
    dy_km: float
    weight_g: float
    zone: str


@dataclass(frozen=True)
class QuoteRequest:
    eur_to_sek: float
    legs: list[LegInput]


def parse_request(raw: dict[str, Any]) -> QuoteRequest:
    eur_to_sek = float(raw["eur_to_sek"])
    raw_legs: list[dict[str, Any]] = raw["legs"]
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
    return QuoteRequest(eur_to_sek=eur_to_sek, legs=legs)


def normalize_depot(route: str) -> str:
    return posixpath.basename(posixpath.normpath(route))


def normalize_zone(zone: str) -> str:
    return zone.strip().upper()


def is_valid_leg(depot: str, zone: str) -> bool:
    return DEPOT_RE.fullmatch(depot) is not None and zone in VALID_ZONES


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


def compute_quote(req: QuoteRequest) -> dict[str, int]:
    valid_legs = 0
    heavy_legs = 0
    customs_legs = 0
    long_haul_pairs = 0
    prev_long_haul = False
    total_km = 0.0
    total_eur = 0.0

    for leg in req.legs:
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
            leg_eur += 12.0
            heavy_legs += 1
        leg_eur = apply_zone_adjustment(leg_eur, zone)
        if zone == "NON-EU":
            customs_legs += 1

        is_long_haul = km > 100.0
        if prev_long_haul and is_long_haul:
            long_haul_pairs += 1
        prev_long_haul = is_long_haul

        total_km += km
        total_eur += leg_eur

    total_eur += 25.0 * long_haul_pairs

    return {
        "legs": len(req.legs),
        "valid_legs": valid_legs,
        "total_m": round(total_km * 1000.0),
        "total_eur_cents": round(total_eur * 100.0),
        "total_sek": round(total_eur * req.eur_to_sek),
        "heavy_legs": heavy_legs,
        "customs_legs": customs_legs,
        "long_haul_pairs": long_haul_pairs,
    }


def main() -> None:
    raw: dict[str, Any] = json.load(sys.stdin)
    req = parse_request(raw)
    result = compute_quote(req)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
