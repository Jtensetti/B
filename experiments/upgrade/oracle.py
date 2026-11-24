"""Hidden fixtures and the owner's intended quotes after each step (0 = build)."""
CATALOG = {"desk lamp": 1.2, "office chair": 14.5, "bookshelf": 22.0, "monitor": 6.8, "keyboard": 0.9,
           "standing desk": 31.0}
ZONES = {"SE": 1, "NO": 2, "DK": 2, "FI": 2, "DE": 3, "PL": 3, "NL": 3, "US": 4, "GB": 4}
START = {1: 39.0, 2: 59.0, 3: 79.0, 4: 149.0}
PER_KG = {1: 12.0, 2: 18.0, 3: 25.0, 4: 60.0}

_PRODUCTS = ["desk lamp", "ofice chair", "bookshelf", "monitr", "keyboard", "standing desk", "sofa", "Monitor"]
_COUNTRIES = ["SE", "no", "DE", "US", "FI", "GB", "BR", "PL", "DK"]


def orders():
    rows = []
    for i in range(24):
        p, c = _PRODUCTS[i % 8], _COUNTRIES[(i * 5 + i // 8) % 9]
        row = {"id": f"o{i:02d}", "product": p, "country": c}
        if i % 3 == 0:
            row["express"] = True
        elif i % 3 == 1:
            row["express"] = False
        if i % 4 == 2:
            row["qty"] = 2
        elif i % 5 == 3:
            row["qty"] = 3
        rows.append(row)
    return rows


def _distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _match(name):
    if name in CATALOG:
        return name
    best = min(sorted(CATALOG), key=lambda k: _distance(name, k))
    return best if _distance(name, best) <= 2 else None


def expected(change):
    quotes, unknown = {}, []
    for o in orders():
        product, country = _match(o["product"]), o["country"].upper()
        if product is None or country not in ZONES:
            unknown.append(o["id"])
            continue
        z = ZONES[country]
        qty = o.get("qty", 1) if change >= 2 else 1
        weight = qty * CATALOG[product]
        extra = (50.0 if o.get("express") else 0.0) + (30.0 if change >= 1 and z == 4 else 0.0)
        quote = (START[z] + PER_KG[z] * weight + extra) * 1.25
        if change >= 3 and weight > 20:
            quote *= 0.9
        quotes[o["id"]] = round(quote, 2)
    return {"quotes": quotes, "unknown": sorted(unknown)}
