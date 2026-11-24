"""Hidden fixtures and the owner's intended invoices after each step (0 = build, 1-8 = changes).

Every step is graded on two months, February 2026 (28 days) and March 2026 (31 days).
Each step's input contains only the fields that exist at that step.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

MONTHS = ["2026-02", "2026-03"]
RATES = {"EUR": 11.2, "NOK": 0.98}
PLANS = {"basic": {"price": 99}, "pro": {"price": 299}, "team": {"price": 899},
         "solo_year": {"price": 990, "period": "year"}, "pro_year": {"price": 2990, "period": "year"}}
COUPONS = {"WELCOME10": {"percent": 10, "months": 3}, "HALF": {"percent": 50, "months": 1},
           "LOYAL": {"percent": 15, "months": 12}}
VAT = {"SE": 0.25, "NO": 0.25, "DE": 0.19, "FR": 0.20}
CURRENCY = {"SE": "SEK", "NO": "NOK", "DE": "EUR", "FR": "EUR"}

_C = []


def _c(id, country, plan, start, end=None, version="2.3.0", coupon=None, changes=None, vat_id=None):
    row = {"id": id, "country": country, "plan": plan, "start": start, "end": end, "app_version": version}
    if coupon is not None:
        row["coupon"] = coupon
    if changes:
        row["changes"] = changes
    if vat_id is not None:
        row["vat_id"] = vat_id
    _C.append(row)


_c("a01", "SE", "pro", "2025-06-01")
_c("a02", "NO", "basic", "2025-11-15", version="1.9.3")
_c("a03", "DE", "team", "2025-01-10", version="1.10.0")
_c("a04", "FR", "pro", "2026-02-10", version="2.0.0-beta.1")
_c("a05", "SE", "basic", "2026-03-05", version="2.0.0")
_c("a06", "SE", "team", "2025-09-01", end="2026-02-14", version="0.9.0")
_c("a07", "NO", "pro", "2026-02-20", version="2.1.0-rc.1")
_c("a08", "DE", "basic", "2026-01-25", end="2026-03-03", version="10.0.0")
_c("a09", "FR", "team", "2026-04-01")
_c("a10", "SE", "pro", "2025-12-01", end="2026-01-31", version="1.0.0")
_c("a11", "SE", "pro", "2026-01-01", coupon="welcome10")
_c("a12", "NO", "team", "2025-12-20", version="1.2.3", coupon="WELCOME10")
_c("a13", "DE", "pro", "2026-02-01", coupon="Half")
_c("a14", "FR", "basic", "2025-03-01", coupon="LOYAL", version="1.99.0")
_c("a15", "SE", "basic", "2026-02-27", coupon="NOPE")
_c("a16", "SE", "team", "2026-03-20", coupon="half", version="2.0.0-alpha")
_c("a17", "NO", "basic", "2026-02-15", end="2026-02-28")
_c("a18", "SE", "pro", "2026-02-25", end="2026-03-02")
_c("a19", "DE", "team", "2026-02-12", version="1.4.0", coupon="LOYAL")
_c("a20", "SE", "basic", "2025-10-01", changes=[{"date": "2026-02-15", "plan": "pro"}])
_c("a21", "NO", "pro", "2025-12-01", changes=[{"date": "2026-03-10", "plan": "basic"},
                                              {"date": "2026-03-25", "plan": "team"}], version="1.5.0")
_c("a22", "DE", "basic", "2026-02-18", changes=[{"date": "2026-03-01", "plan": "team"}], coupon="welcome10")
_c("a23", "FR", "team", "2025-05-05", changes=[{"date": "2026-01-10", "plan": "pro"}], end="2026-03-15")
_c("a24", "SE", "pro", "2026-02-01", changes=[{"date": "2026-02-10", "plan": "team"}])
_c("a25", "DE", "pro", "2025-08-01", vat_id="DE123456789")
_c("a26", "FR", "team", "2026-02-05", vat_id="FR99887766", version="1.0.1")
_c("a27", "SE", "pro", "2025-08-01", vat_id="SE556677889901")
_c("a28", "NO", "team", "2025-08-01", vat_id="NO998877665")
_c("a29", "DE", "basic", "2025-08-01", vat_id="")
_c("a30", "SE", "solo_year", "2025-03-14")
_c("a31", "NO", "pro_year", "2025-02-28", version="1.8.0")
_c("a32", "DE", "solo_year", "2026-02-27", coupon="HALF")
_c("a33", "FR", "pro_year", "2024-03-31", vat_id="FR11223344")
_c("a34", "SE", "solo_year", "2025-02-01", end="2026-01-31")
_c("a35", "SE", "pro_year", "2026-03-15", coupon="loyal", version="1.0.0")
_c("a36", "DE", "solo_year", "2025-03-01", end="2026-03-01")
_c("a37", "SE", "basic", "2026-02-12", end="2026-03-01")
_c("a38", "NO", "basic", "2026-03-30")
_c("a39", "DE", "basic", "2026-02-13", version="1.0.0")
_c("a40", "FR", "basic", "2026-03-17", end="2026-03-31", coupon="HALF")

CUSTOMERS = _C


def _semver_key(v):
    core, _, pre = v.partition("-")
    nums = tuple(int(x) for x in core.split("."))
    if not pre:
        return nums, (1,)
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return nums, (0, ids)


def legacy(v):
    return _semver_key(v) < _semver_key("2.0.0")


def _d(s):
    return date.fromisoformat(s)


def data(step, month):
    plans = {k: ({"price": p["price"], "period": "year"} if "period" in p else {"price": p["price"]})
             for k, p in PLANS.items() if step >= 6 or "period" not in p}
    customers = []
    for c in CUSTOMERS:
        if "period" in PLANS[c["plan"]] and step < 6:
            continue
        row = {k: c[k] for k in ("id", "country", "plan", "start", "end", "app_version")}
        if step >= 2:
            row["coupon"] = c.get("coupon")
        if step >= 4 and c.get("changes"):
            row["changes"] = c["changes"]
        if step >= 5 and "vat_id" in c:
            row["vat_id"] = c["vat_id"]
        customers.append(row)
    out = {"month": month, "rates": RATES, "plans": plans, "customers": customers}
    if step >= 2:
        out["coupons"] = COUPONS
    return out


def _months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def _half_up(x, places):
    q = Decimal(1).scaleb(-places)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_UP))


def expected(step, month):
    year, mon = map(int, month.split("-"))
    days = calendar.monthrange(year, mon)[1]
    first, last = date(year, mon, 1), date(year, mon, days)
    invoices = {}
    for c in data(step, month)["customers"]:
        start = _d(c["start"])
        end = _d(c["end"]) if c["end"] else None
        active = [first + timedelta(i) for i in range(days)
                  if start <= first + timedelta(i) and (end is None or first + timedelta(i) <= end)]
        plan = PLANS[c["plan"]]
        if step >= 6 and plan.get("period") == "year":
            since = _months_between(start, first)
            if not active or since < 0 or since % 12:
                continue
            sek = float(plan["price"])
        else:
            billable = [d for d in active if not (step >= 3 and d <= start + timedelta(13))]
            if not billable:
                continue
            changes = c.get("changes", []) if step >= 4 else []

            def price_on(d):
                name = c["plan"]
                for ch in changes:
                    if _d(ch["date"]) <= d:
                        name = ch["plan"]
                return PLANS[name]["price"]
            sek = sum(price_on(d) for d in billable) / days
        if step >= 1 and legacy(c["app_version"]):
            sek *= 0.8
        if step >= 2 and c.get("coupon"):
            coupon = COUPONS.get(c["coupon"].upper())
            if coupon and _months_between(start, first) + 1 <= coupon["months"]:
                sek *= 1 - coupon["percent"] / 100
        cur = CURRENCY[c["country"]]
        amount = sek / (RATES[cur] if cur != "SEK" else 1.0)
        net = _half_up(amount, 0) if (step >= 8 and cur != "EUR") else round(amount, 2)
        rate = 0.0 if (step >= 5 and c["country"] in ("DE", "FR") and c.get("vat_id")) else VAT[c["country"]]
        vat = round(net * rate, 2)
        total = round(net + vat, 2)
        if step >= 7 and total * (RATES[cur] if cur != "SEK" else 1.0) < 10:
            continue
        invoices[c["id"]] = {"currency": cur, "net": net, "vat": vat, "total": total}
    return {"invoices": invoices}
