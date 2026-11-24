"""Hidden fixtures and the owner's intended quotes after each step (0 = build, 1-5 = changes)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "libs" / "calendar"))
import workdays  # noqa: E402  the task's own Python library

DEPOT = {"lat": 59.3293, "lon": 18.0686}
CATALOG = {"armchair": 14.2, "bookshelf": 31.5, "desk lamp": 1.8, "dining table": 42.0,
           "office chair": 16.4, "sofa": 58.0, "wardrobe": 77.5, "stool": 3.1}
RATES = {"EUR": 11.2}
ZONES = {"SE": 1, "NO": 2, "DK": 2, "FI": 2, "DE": 3, "NL": 3, "PL": 3, "FR": 4, "ES": 4, "IT": 4}
START = {1: 49, 2: 79, 3: 99, 4: 129}
PER_KG = {1: 6.5, 2: 9.0, 3: 11.0, 4: 14.5}
VAT = {"SE": 0.25, "NO": 0.25, "DK": 0.25, "FI": 0.255, "DE": 0.19, "NL": 0.21, "PL": 0.23,
       "FR": 0.20, "ES": 0.21, "IT": 0.22}
EU = {"SE", "DK", "FI", "DE", "NL", "PL", "FR", "ES", "IT"}

_ROWS = [
    # id, product, country, lat, lon, date, business, qty, express
    ("q01", "sofa", "SE", 59.3326, 18.0649, "2026-03-11", False, None, None),
    ("q02", "armchiar", "SE", 57.7089, 11.9746, "2026-04-02", False, 2, None),
    ("q03", "desk lamp", "NO", 59.9139, 10.7522, "2026-05-13", False, None, True),
    ("q04", "Bookshelf", "DE", 52.5200, 13.4050, "2026-06-05", True, None, None),
    ("q05", "wardrobe", "FR", 48.8566, 2.3522, "2026-12-23", False, None, True),
    ("q06", "sofa", "BR", -23.55, -46.63, "2026-03-11", False, None, None),
    ("q07", "bed", "SE", 59.85, 17.64, "2026-03-11", False, None, None),
    ("q08", "stool", "fi", 60.1699, 24.9384, "2026-04-03", True, 4, None),
    ("q09", "dining table", "PL", 52.2297, 21.0122, "2026-05-01", True, 2, True),
    ("q10", "office chair", "NL", 52.3676, 4.9041, "2026-06-19", False, 3, None),
    ("q11", "offic chair", "SE", 67.8558, 20.2253, "2026-12-31", True, None, True),
    ("q12", "sofa", "ES", 40.4168, -3.7038, "2026-01-05", True, None, None),
    ("q13", "wardrobe", "SE", 55.6050, 13.0038, "2026-01-06", True, None, None),
    ("q14", "desk lamp", "IT", 41.9028, 12.4964, "2026-04-04", False, 10, True),
    ("q15", "stool", "DK", 55.6761, 12.5683, "2026-05-14", False, None, None),
    ("q16", "armchair", "NO", 69.6492, 18.9553, "2026-06-06", True, 4, None),
    ("q17", "bookshelf", "US", 40.71, -74.0, "2026-03-11", False, None, None),
    ("q18", "sofaa", "DE", 48.1351, 11.5820, "2026-02-27", False, None, True),
    ("q19", "lamp", "SE", 59.33, 18.07, "2026-03-11", False, None, None),
    ("q20", "dining table", "FR", 43.2965, 5.3698, "2026-12-24", True, 1, None),
    ("q21", "stool", "SE", 59.3326, 18.0649, "2026-03-14", False, 20, True),
    ("q22", "wardrobe", "PL", 50.0647, 19.9450, "2026-04-06", False, None, None),
    ("q23", "sofa", "NO", 63.4305, 10.3951, "2026-12-25", True, 1, True),
    ("q24", "office chair", "DE", 53.5511, 9.9937, "2026-05-15", True, 3, None),
]


def orders(step):
    rows = []
    for id, product, country, lat, lon, day, business, qty, express in _ROWS:
        row = {"id": id, "product": product, "country": country, "lat": lat, "lon": lon, "date": day, "business": business}
        if step >= 1 and qty is not None:
            row["qty"] = qty
        if step >= 2 and express is not None:
            row["express"] = express
        rows.append(row)
    return rows


def data(step):
    out = {"depot": DEPOT, "catalog": CATALOG, "orders": orders(step)}
    if step >= 4:
        out["rates"] = RATES
    return out


def _lev(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _road_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a)) * 1.25


def expected(step):
    quotes, unknown = {}, []
    for o in orders(step):
        best = min(sorted(CATALOG), key=lambda k: _lev(o["product"], k))
        country = o["country"].strip().upper()
        if _lev(o["product"], best) > 2 or country not in ZONES:
            unknown.append(o["id"])
            continue
        zone = ZONES[country]
        weight = CATALOG[best] * (o.get("qty", 1) if step >= 1 else 1)
        base = START[zone] + PER_KG[zone] * (math.ceil(weight * 2) / 2)
        express = step >= 2 and o.get("express", False)
        if step >= 5 and o["business"] and weight >= 50:
            base = 0.0
        if express:
            base *= 1.5
        surcharge = 0.80 * max(0.0, _road_km(DEPOT["lat"], DEPOT["lon"], o["lat"], o["lon"]) - 300)
        if step >= 3:
            surcharge = min(surcharge, 400.0)
        net = base + surcharge
        vat = 0.0 if (o["business"] and country != "SE" and country in EU) else VAT[country]
        price = round(net * (1 + vat), 2)
        currency = "SEK"
        if step >= 4 and country != "SE":
            price, currency = round(price / RATES["EUR"], 2), "EUR"
        if express and workdays.is_workday(o["date"]):
            delivery = o["date"]
        else:
            delivery = workdays.next_workday(o["date"])
        quote = {"price": price, "delivery": delivery}
        if step >= 4:
            quote["currency"] = currency
        quotes[o["id"]] = quote
    return {"quotes": quotes, "unknown": sorted(unknown)}
