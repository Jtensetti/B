"""Quote parcels: read one JSON line on stdin, write one JSON line on stdout."""
import json
import sys
from typing import Any

from carrier import rate

KG_PER_LB: float = 0.45359237
CM3_PER_CUBIC_INCH: float = 2.54 ** 3
CM3_PER_LITER: float = 1000.0
DIM_DIVISOR: float = 139.0
MAX_MATCH_DISTANCE: int = 2


def levenshtein(a: str, b: str) -> int:
    """Classic edit distance (insert, delete, substitute each cost 1)."""
    previous: list[int] = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current: list[int] = [i]
        for j, cb in enumerate(b, start=1):
            cost: int = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def closest_name(product: str, names: list[str]) -> str | None:
    """Catalog name with the smallest edit distance (alphabetical tie-break), if within the limit."""
    best: tuple[int, str] | None = None
    for name in names:
        candidate: tuple[int, str] = (levenshtein(product, name), name)
        if best is None or candidate < best:
            best = candidate
    if best is None or best[0] > MAX_MATCH_DISTANCE:
        return None
    return best[1]


def quote_orders(data: dict[str, Any]) -> dict[str, Any]:
    """Price every order whose product is in the catalog (exactly or by close misspelling)."""
    catalog: dict[str, Any] = data.get("catalog", {})
    usd_to_sek: float = float(data["usd_to_sek"])
    names: list[str] = sorted(catalog)
    quotes: dict[str, float] = {}
    unknown: list[str] = []
    matched: dict[str, str] = {}

    for order in data.get("orders", []):
        order_id: str = order["id"]
        product: str = order["product"]
        name: str | None = product if product in catalog else closest_name(product, names)
        if name is None:
            unknown.append(order_id)
            continue
        if name != product:
            matched[order_id] = name
        weight_kg: float = float(catalog[name]["weight_kg"])
        qty: int = int(order["qty"])
        actual_lb: float = qty * weight_kg / KG_PER_LB
        billable_lb: float = actual_lb
        if "volume_l" in catalog[name]:
            volume_cm3: float = qty * float(catalog[name]["volume_l"]) * CM3_PER_LITER
            dimensional_lb: float = (volume_cm3 / CM3_PER_CUBIC_INCH) / DIM_DIVISOR
            billable_lb = max(actual_lb, dimensional_lb)
        express: bool = bool(order.get("express", False))
        price_usd: float = rate(billable_lb, express)
        quotes[order_id] = round(price_usd * usd_to_sek, 2)

    return {
        "quotes_sek": quotes,
        "total_sek": round(sum(quotes.values()), 2),
        "unknown": sorted(unknown),
        "matched": matched,
    }


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.readline())
    sys.stdout.write(json.dumps(quote_orders(data)) + "\n")


if __name__ == "__main__":
    main()
