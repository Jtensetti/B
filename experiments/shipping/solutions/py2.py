"""Quote parcels: reads one JSON line from stdin, writes one JSON line to stdout."""
import json
import sys
from typing import Any

from carrier import rate

KG_PER_LB: float = 0.45359237
MAX_DISTANCE: int = 2


CM_PER_INCH: float = 2.54
CM3_PER_LITER: float = 1000.0
DIM_DIVISOR: float = 139.0


def weight_lb(qty: int, weight_kg: float, volume_l: float | None = None) -> float:
    """Billable weight in pounds: actual weight, or dimensional weight if larger.

    Dimensional weight is the volume in cubic inches divided by 139.
    Without volume_l only the actual weight applies.
    """
    actual: float = (qty * weight_kg) / KG_PER_LB
    if volume_l is None:
        return actual
    cubic_inches: float = qty * volume_l * CM3_PER_LITER / CM_PER_INCH ** 3
    return max(actual, cubic_inches / DIM_DIVISOR)


def levenshtein(a: str, b: str) -> int:
    """Classic edit distance (insert, delete, substitute), two-row dynamic programming."""
    previous: list[int] = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current: list[int] = [i]
        for j, cb in enumerate(b, start=1):
            cost: int = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def closest_name(product: str, names: list[str]) -> str | None:
    """Catalog name with the smallest edit distance to product, if within MAX_DISTANCE.

    Ties go to the alphabetically first name.
    """
    best: str | None = None
    best_distance: int = MAX_DISTANCE + 1
    for name in sorted(names):
        distance: int = levenshtein(product, name)
        if distance < best_distance:
            best = name
            best_distance = distance
    return best


def quote_orders(data: dict[str, Any]) -> dict[str, Any]:
    """Quote every order in Swedish kronor; match near-miss product names; list the rest as unknown."""
    catalog: dict[str, Any] = data.get("catalog", {})
    usd_to_sek: float = float(data["usd_to_sek"])
    quotes_sek: dict[str, float] = {}
    unknown: list[str] = []
    matched: dict[str, str] = {}
    for order in data.get("orders", []):
        order_id: str = str(order["id"])
        product: str = order["product"]
        name: str | None = product if product in catalog else closest_name(product, list(catalog))
        if name is None:
            unknown.append(order_id)
            continue
        if name != product:
            matched[order_id] = name
        entry: dict[str, Any] = catalog[name]
        kg: float = float(entry["weight_kg"])
        volume_l: float | None = float(entry["volume_l"]) if "volume_l" in entry else None
        express: bool = bool(order.get("express", False))
        usd: float = rate(weight_lb(int(order["qty"]), kg, volume_l), express)
        quotes_sek[order_id] = round(usd * usd_to_sek, 2)
    total_sek: float = round(sum(quotes_sek.values()), 2)
    return {
        "quotes_sek": quotes_sek,
        "total_sek": total_sek,
        "unknown": sorted(unknown),
        "matched": matched,
    }


def main() -> None:
    """Read one JSON line from stdin and print the quote result as one JSON line."""
    data: dict[str, Any] = json.loads(sys.stdin.readline())
    print(json.dumps(quote_orders(data)))


if __name__ == "__main__":
    main()
