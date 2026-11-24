"""Hidden fixtures and the owner's intended output after each step (0 = the inherited program)."""

SE_VAT = {"standard": 0.25, "food": 0.12, "books": 0.06}
NO_VAT = {"standard": 0.25, "food": 0.15, "books": 0.0}

CATALOG = {
    "tea": {"name": "Green tea", "price": 40, "vat_class": "food"},
    "honey": {"name": "Honey", "price": 85, "vat_class": "food"},
    "mug": {"name": "Mug", "price": 120, "vat_class": "standard"},
    "pot": {"name": "Teapot", "price": 390, "vat_class": "standard"},
    "book": {"name": "Tea book", "price": 250, "vat_class": "books"},
}
CUSTOMERS = [
    {"id": "c1", "country": "SE", "member": True},
    {"id": "c2", "country": "SE"},
    {"id": "c3", "country": "no", "member": True},
    {"id": "c4", "country": "NO", "member": False},
    {"id": "c5", "country": "se"},
    {"id": "c6", "country": "NO"},
]
RATES = {"NOK": 0.95}
_BASKETS = [
    [("tea", 1)], [("tea", 12), ("mug", 1)], [("book", 2)], [("pot", 1), ("honey", 3)],
    [("mug", 4)], [("honey", 10), ("book", 1)], [("tea", 3), ("mug", 1), ("book", 1)], [("pot", 2)],
]


def orders():
    rows = []
    for i in range(16):
        basket = _BASKETS[(i * 3) % 8] if i >= 8 else _BASKETS[i]
        rows.append({"id": f"o{i:02d}", "customer": CUSTOMERS[i % 6]["id"],
                     "lines": [{"sku": s, "qty": q} for s, q in basket]})
    return rows


def data():
    return {"rates": RATES, "catalog": CATALOG, "customers": CUSTOMERS, "orders": orders()}


def expected(step):
    customers = {c["id"]: c for c in CUSTOMERS}
    invoices, net_by_class, shipping_total, vat_total = {}, {}, 0.0, 0.0
    for o in orders():
        c = customers[o["customer"]]
        norway = c["country"].upper() == "NO"
        vat_rates = NO_VAT if (step >= 2 and norway) else SE_VAT
        lines = []
        for l in o["lines"]:
            p = CATALOG[l["sku"]]
            unit = p["price"] / (1 + SE_VAT[p["vat_class"]]) if step >= 3 else p["price"]
            rate = (0.10 if c.get("member") else 0.0) + (0.05 if l["qty"] >= 10 else 0.0)
            lines.append((p["vat_class"], unit * l["qty"] * (1 - rate)))
        goods = sum(n for _, n in lines)
        shipping = 0.0 if goods >= 500 else 49.0
        vat = {}
        for cls, n in lines:
            vat[cls] = vat.get(cls, 0.0) + n * vat_rates[cls]
        if shipping:
            vat["standard"] = vat.get("standard", 0.0) + shipping * vat_rates["standard"]
        net = goods + shipping
        total = net + sum(vat.values())
        factor = 1 / RATES["NOK"] if (step >= 1 and norway) else 1.0
        invoices[o["id"]] = {"currency": "NOK" if (step >= 1 and norway) else "SEK",
                             "net": round(net * factor, 2),
                             "vat": {k: round(v * factor, 2) for k, v in sorted(vat.items())},
                             "total": round(total * factor, 2)}
        for cls, n in lines:
            net_by_class[cls] = net_by_class.get(cls, 0.0) + n
        shipping_total += shipping
        vat_total += sum(vat.values())
    revenue = sum(net_by_class.values()) + shipping_total + vat_total
    report = {"net_by_class": {k: round(v, 2) for k, v in sorted(net_by_class.items())},
              "shipping": round(shipping_total, 2), "vat": round(vat_total, 2), "revenue": round(revenue, 2)}
    return {"invoices": invoices, "report": report}
