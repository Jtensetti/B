"""Ground truth for the shipping trial."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "workspace"))
from carrier import rate

LB = 0.45359237
IN3_PER_L = 1000 / 2.54 ** 3


def levenshtein(a, b):
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def quote(data, step):
    catalog = data["catalog"]
    quotes, unknown, matched = {}, [], {}
    for order in data["orders"]:
        name = order["product"]
        if name not in catalog and step >= 2 and catalog:
            best = min(sorted(catalog), key=lambda c: levenshtein(name, c))
            if levenshtein(name, best) <= 2:
                matched[order["id"]] = best
                name = best
        if name not in catalog:
            unknown.append(order["id"])
            continue
        item = catalog[name]
        weight = order["qty"] * item["weight_kg"] / LB
        if step >= 4 and "volume_l" in item:
            weight = max(weight, order["qty"] * item["volume_l"] * IN3_PER_L / 139)
        quotes[order["id"]] = rate(weight, step >= 5 and order.get("express", False) is True)
    out = {}
    if step >= 3:
        sek = {k: round(v * data["usd_to_sek"], 2) for k, v in quotes.items()}
        out["quotes_sek"], out["total_sek"] = sek, round(sum(sek.values()), 2)
    else:
        out["quotes"], out["total_usd"] = quotes, round(sum(quotes.values()), 2)
    out["unknown"] = sorted(unknown)
    if step >= 2:
        out["matched"] = matched
    return out


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    expected = {}
    for f in sorted(folder.glob("*.json")):
        if f.name.startswith("_"):
            continue
        data = json.loads(f.read_text())
        expected[f.name] = {}
        for step in range(1, 6):
            fed = dict(data)
            if step < 3:
                fed.pop("usd_to_sek", None)
            expected[f.name][step] = quote(fed, step)
    (folder / "_expected.json").write_text(json.dumps(expected, indent=1) + "\n")
    print(len(expected), "fixtures")
