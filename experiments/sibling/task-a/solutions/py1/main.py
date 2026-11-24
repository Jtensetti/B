"""Delivery quotes for a furniture shop in Stockholm.

Reads one line of JSON on stdin and writes one line of JSON on stdout. The business rules live here;
the carrier tariff, road distance, VAT, working days and string distance come from libs/ through
small bridge programs in bridge/, so each library's own code stays the source of truth.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from typing import Any, Callable, Dict, List, Tuple, cast

# Keep libs/ free of __pycache__ when the Python calendar module is loaded.
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.path.join(HERE, "bridge")
LIBS = os.path.join(HERE, "libs")

MAX_MATCH_DISTANCE = 2
FREE_ROAD_KM = 300.0
EXTRA_PER_ROAD_KM_SEK = 0.80
EXPRESS_BASE_MULTIPLIER = 1.5
MAX_DISTANCE_SURCHARGE_SEK = 400.0
FREE_FREIGHT_MIN_KG = 50.0


def run_json_bridge(cmd: List[str], cwd: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"bridge {cmd[0]} failed: {proc.stderr.strip()}")
    return cast(Dict[str, Any], json.loads(proc.stdout))


def run_line_bridge(cmd: List[str], cwd: str, lines: List[str]) -> List[str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"bridge {cmd[0]} failed: {proc.stderr.strip()}")
    return proc.stdout.split("\n")[: len(lines)]


def lev_distances(pairs: List[List[str]]) -> List[int]:
    if not pairs:
        return []
    res = run_json_bridge(
        ["node", os.path.join(BRIDGE, "node", "levenshtein.js")],
        HERE,
        {"pairs": pairs},
    )
    return [int(d) for d in cast(List[Any], res["distances"])]


def tariff_lookup(items: List[Tuple[str, float]]) -> List[Dict[str, Any]]:
    if not items:
        return []
    res = run_json_bridge(
        ["go", "run", "."],
        os.path.join(BRIDGE, "go"),
        {"items": [{"country": c, "weight": w} for c, w in items]},
    )
    return cast(List[Dict[str, Any]], res["results"])


def road_distances(points: List[Tuple[float, float, float, float]]) -> List[float]:
    if not points:
        return []
    lines = [f"{a!r} {b!r} {c!r} {d!r}" for a, b, c, d in points]
    out = run_line_bridge(
        ["cargo", "run", "--quiet", "--manifest-path", os.path.join(BRIDGE, "rust", "Cargo.toml")],
        HERE,
        lines,
    )
    return [float(x) for x in out[: len(points)]]


def vat_lookup(items: List[Tuple[str, bool]]) -> List[Dict[str, Any]]:
    if not items:
        return []
    res = run_json_bridge(
        ["dotnet", "run", "--project", os.path.join(BRIDGE, "csharp", "VatBridge.csproj"), "-v", "q"],
        HERE,
        {"items": [{"country": c, "business": b} for c, b in items]},
    )
    return cast(List[Dict[str, Any]], res["results"])


def load_calendar() -> Tuple[Callable[[str], str], Callable[[str], bool]]:
    path = os.path.join(LIBS, "calendar", "workdays.py")
    spec = importlib.util.spec_from_file_location("workdays", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    next_workday = cast(Callable[[str], str], getattr(module, "next_workday"))
    is_workday = cast(Callable[[str], bool], getattr(module, "is_workday"))
    return next_workday, is_workday


def quote(req: Dict[str, Any]) -> Dict[str, Any]:
    depot = cast(Dict[str, Any], req["depot"])
    depot_lat = float(depot["lat"])
    depot_lon = float(depot["lon"])
    catalog: Dict[str, float] = {str(k): float(v) for k, v in cast(Dict[str, Any], req["catalog"]).items()}
    orders = cast(List[Dict[str, Any]], req["orders"])
    rates = cast(Dict[str, Any], req.get("rates", {}))

    # Product: nearest catalog name by Levenshtein distance, ties to the alphabetically first name.
    pairs: List[List[str]] = []
    owners: List[Tuple[int, str]] = []
    for idx, order in enumerate(orders):
        for name in catalog:
            pairs.append([str(order["product"]), name])
            owners.append((idx, name))
    distances = lev_distances(pairs)
    best: Dict[int, Tuple[int, str]] = {}
    for (idx, name), dist in zip(owners, distances):
        cur = best.get(idx)
        if cur is None or (dist, name) < cur:
            best[idx] = (dist, name)
    product_of: Dict[int, str] = {
        idx: name for idx, (dist, name) in best.items() if dist <= MAX_MATCH_DISTANCE
    }

    # Zone and carrier base price (parcel weight = qty x catalog weight; 0 when there is no match).
    weights: List[float] = [
        catalog[product_of[i]] * float(order.get("qty", 1)) if i in product_of else 0.0
        for i, order in enumerate(orders)
    ]
    tariff = tariff_lookup([(str(o["country"]), weights[i]) for i, o in enumerate(orders)])

    # Road distance from depot to customer.
    roads = road_distances(
        [(depot_lat, depot_lon, float(o["lat"]), float(o["lon"])) for o in orders]
    )

    # VAT rate, or reverse charge for business customers in other EU countries.
    vat = vat_lookup([(str(o["country"]), bool(o["business"])) for o in orders])

    next_workday, is_workday = load_calendar()

    quotes: Dict[str, Dict[str, Any]] = {}
    unknown: List[str] = []
    for idx, order in enumerate(orders):
        oid = str(order["id"])
        t = tariff[idx]
        v = vat[idx]
        if idx not in product_of or not t["served"] or not v["ok"]:
            unknown.append(oid)
            continue
        express = bool(order.get("express", False))
        order_date = str(order["date"])
        base = float(t["base"])
        if bool(order["business"]) and weights[idx] >= FREE_FREIGHT_MIN_KG:
            base = 0.0
        base = base * (EXPRESS_BASE_MULTIPLIER if express else 1.0)
        extra = min(MAX_DISTANCE_SURCHARGE_SEK, EXTRA_PER_ROAD_KM_SEK * max(0.0, roads[idx] - FREE_ROAD_KM))
        net = base + extra
        rate = float(v["rate"])
        price = round(net * (1 + rate), 2)
        if express and is_workday(order_date):
            delivery = order_date
        else:
            delivery = next_workday(order_date)
        currency = "SEK"
        if str(order["country"]).strip().upper() != "SE":
            eur_per_sek_rate = float(rates["EUR"])
            price = round(price / eur_per_sek_rate, 2)
            currency = "EUR"
        quotes[oid] = {"price": price, "delivery": delivery, "currency": currency}

    return {"quotes": quotes, "unknown": sorted(unknown)}


def main() -> None:
    req = cast(Dict[str, Any], json.load(sys.stdin))
    sys.stdout.write(json.dumps(quote(req)) + "\n")


if __name__ == "__main__":
    main()
