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
    eur: float


def normalize_depot(route: str) -> str:
    normalized = posixpath.normpath(route)
    return posixpath.basename(normalized)


def normalize_zone(zone: str) -> str:
    return zone.strip().upper()


def parse_valid_leg(leg: LegInput) -> ValidLeg | None:
    depot = normalize_depot(leg.route)
    zone = normalize_zone(leg.zone)
    if DEPOT_PATTERN.fullmatch(depot) is None or zone not in VALID_ZONES:
        return None
    km = math.sqrt(leg.dx_km * leg.dx_km + leg.dy_km * leg.dy_km)
    kg = leg.weight_g / 1000.0
    eur = 5.0 + 0.5 * km + 2.0 * kg
    return ValidLeg(depot=depot, zone=zone, km=km, kg=kg, eur=eur)


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

    for leg in legs:
        parsed = parse_valid_leg(leg)
        if parsed is None:
            continue
        valid_count += 1
        total_km += parsed.km
        total_eur += parsed.eur

    return {
        "legs": len(legs),
        "valid_legs": valid_count,
        "total_m": round(total_km * 1000.0),
        "total_eur_cents": round(total_eur * 100.0),
        "total_sek": round(total_eur * eur_to_sek),
    }


def main() -> None:
    payload: dict[str, Any] = json.loads(sys.stdin.read())
    eur_to_sek, legs = parse_input(payload)
    result = compute_quote(eur_to_sek, legs)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
