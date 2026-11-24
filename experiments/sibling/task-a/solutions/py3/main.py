"""Delivery quotes for the Stockholm furniture shop.

Reads one JSON line on stdin, writes one JSON line on stdout.
The carrier tariff (Go), geo distance (Rust), VAT rules (C#) and the
Levenshtein distance (Node, fastest-levenshtein) are called through the
helper binaries in bin/ and bridge/; the calendar is imported directly.
"""

import json
import os
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BIN = HERE / "bin"
sys.path.insert(0, str(HERE / "libs" / "calendar"))

import workdays  # noqa: E402

MAX_NAME_DISTANCE = 2
FREE_KM = 300.0
PER_KM_SEK = 0.80
EXPRESS_MULTIPLIER = 1.5
MAX_SURCHARGE_SEK = 400.0
FREE_FREIGHT_KG = 50.0


def run_helper(cmd: list[str], payload: object, env: dict[str, str] | None = None) -> Any:
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(proc.stdout)


def resolve_product(name: str, catalog: dict[str, float]) -> str | None:
    """Catalog name with the smallest Levenshtein distance (ties: alphabetical), if within 2."""
    names = sorted(catalog)
    if not names:
        return None
    lev_env = dict(os.environ)
    lev_env["LEV_PATH"] = str(HERE / "node_modules" / "fastest-levenshtein")
    dists: list[list[int]] = run_helper(
        ["node", str(HERE / "bridge" / "node" / "vq.js")],
        [{"name": name, "names": names}],
        lev_env,
    )
    best_name: str | None = None
    best_dist = MAX_NAME_DISTANCE + 1
    for candidate, dist in zip(names, dists[0]):
        if dist < best_dist:
            best_name = candidate
            best_dist = dist
    return best_name


def order_qty(order: dict[str, Any]) -> float:
    """Number of units ordered; defaults to 1 when the optional "qty" field is absent."""
    qty = order.get("qty", 1)
    return float(qty) if qty is not None else 1.0


def round_money(value: float) -> float:
    return float(Decimal(repr(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.read())
    depot: dict[str, float] = data["depot"]
    catalog: dict[str, float] = {k: float(v) for k, v in data["catalog"].items()}
    orders: list[dict[str, Any]] = data["orders"]
    eur_rate = float(data["rates"]["EUR"])

    unknown: set[str] = set()

    # 1. Resolve products.
    resolved: list[tuple[dict[str, Any], str]] = []
    for order in orders:
        product = resolve_product(str(order["product"]), catalog)
        if product is None:
            unknown.add(str(order["id"]))
        else:
            resolved.append((order, product))

    # 2. Carrier zone and base price (unserved countries are unknown).
    weights = [catalog[p] * order_qty(o) for o, p in resolved]
    tariff_reqs = [
        {"country": str(o["country"]), "weight": w}
        for (o, _), w in zip(resolved, weights)
    ]
    tariff_out: list[dict[str, Any]] = run_helper([str(BIN / "tariffq")], tariff_reqs)
    priced: list[tuple[dict[str, Any], float, float]] = []
    for (order, _), w, t in zip(resolved, weights, tariff_out):
        if not t["ok"]:
            unknown.add(str(order["id"]))
        else:
            priced.append((order, float(t["base"]), w))

    # 3. Road distance from depot to customer.
    geo_reqs = [
        [float(depot["lat"]), float(depot["lon"]), float(o["lat"]), float(o["lon"])]
        for o, _, _ in priced
    ]
    km_out: list[float] = run_helper([str(BIN / "geoq")], geo_reqs) if geo_reqs else []

    # 4. VAT rate or reverse charge.
    vat_reqs = [
        {"country": str(o["country"]), "business": bool(o["business"])} for o, _, _ in priced
    ]
    vat_out: list[dict[str, Any]] = run_helper([str(BIN / "vatq_out" / "Vatq")], vat_reqs) if vat_reqs else []

    quotes: dict[str, dict[str, Any]] = {}
    for (order, base, weight), km, v in zip(priced, km_out, vat_out):
        order_id = str(order["id"])
        if not v["ok"]:
            unknown.add(order_id)
            continue
        express = bool(order.get("express", False))
        if bool(order["business"]) and weight >= FREE_FREIGHT_KG:
            base = 0.0
        base_part = base * EXPRESS_MULTIPLIER if express else base
        surcharge = min(MAX_SURCHARGE_SEK, PER_KM_SEK * max(0.0, km - FREE_KM))
        net = base_part + surcharge
        rate = 0.0 if v["reverse"] else float(v["rate"])
        price = round_money(net * (1.0 + rate))
        order_date = str(order["date"])
        if express and workdays.is_workday(order_date):
            delivery = order_date
        else:
            delivery = workdays.next_workday(order_date)
        if str(order["country"]).strip().upper() == "SE":
            currency = "SEK"
        else:
            currency = "EUR"
            price = round_money(price / eur_rate)
        quotes[order_id] = {"price": price, "delivery": delivery, "currency": currency}

    result = {"quotes": quotes, "unknown": sorted(unknown - set(quotes))}
    sys.stdout.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
