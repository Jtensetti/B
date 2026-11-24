"""Monthly invoices for a subscription service.

Reads one line of JSON from stdin and writes one line of JSON to stdout.
"""

from __future__ import annotations

import calendar
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENT = Decimal("0.01")

VAT_RATES: dict[str, Decimal] = {
    "SE": Decimal("0.25"),
    "NO": Decimal("0.25"),
    "DE": Decimal("0.19"),
    "FR": Decimal("0.20"),
}

CURRENCY_BY_COUNTRY: dict[str, str] = {
    "SE": "SEK",
    "NO": "NOK",
    "DE": "EUR",
    "FR": "EUR",
}

# Customers on an app version below 2.0.0 keep legacy pricing: 20 % off.
LEGACY_CUTOFF_VERSION = "2.0.0"
LEGACY_DISCOUNT_FACTOR = Decimal("0.80")

# A semver key sorts by (major, minor, patch, is_release, prerelease identifiers).
# Releases get flag 1 so they sort above any prerelease with the same core version.
# Numeric prerelease identifiers sort below alphanumeric ones, as the spec requires.
SemverKey = tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]

TRIAL_DAYS = 14

# Invoices whose total is below this many SEK are not issued.
MIN_INVOICE_SEK = Decimal(10)


@dataclass(frozen=True)
class PlanChange:
    date: date
    plan: str


@dataclass(frozen=True)
class Customer:
    id: str
    country: str
    plan: str
    start: date
    end: date | None
    app_version: str | None
    coupon: str | None
    changes: tuple[PlanChange, ...]
    vat_id: str | None


def semver_key(text: str) -> SemverKey:
    """Parse a semantic version into a sort key. Build metadata is ignored."""
    core, _, _build = text.strip().partition("+")
    core, _, prerelease = core.partition("-")
    major_s, minor_s, patch_s = core.split(".")
    major, minor, patch = int(major_s), int(minor_s), int(patch_s)
    if not prerelease:
        return (major, minor, patch, 1, ())
    idents: list[tuple[int, int | str]] = []
    for part in prerelease.split("."):
        idents.append((0, int(part)) if part.isdigit() else (1, part))
    return (major, minor, patch, 0, tuple(idents))


LEGACY_CUTOFF_KEY = semver_key(LEGACY_CUTOFF_VERSION)


def is_legacy(customer: Customer) -> bool:
    if customer.app_version is None:
        return False
    return semver_key(customer.app_version) < LEGACY_CUTOFF_KEY


def to_decimal(value: Any) -> Decimal:
    """Convert a JSON number (or numeric string) to Decimal without float noise."""
    return Decimal(str(value))


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def billable_window(customer: Customer, month_start: date, month_end: date) -> tuple[date, date] | None:
    """First and last billable day of the customer within the month, or None if none.

    The start day and the 13 days after it are a free trial and never billable.
    """
    first = max(customer.start + timedelta(days=TRIAL_DAYS), month_start)
    last = month_end if customer.end is None else min(customer.end, month_end)
    if last < first:
        return None
    return first, last


def active_window(customer: Customer, month_start: date, month_end: date) -> tuple[date, date] | None:
    """First and last active day of the customer within the month, trial not applied."""
    first = max(customer.start, month_start)
    last = month_end if customer.end is None else min(customer.end, month_end)
    if last < first:
        return None
    return first, last


def count_days(first: date, last: date) -> int:
    return 0 if last < first else (last - first).days + 1


def coupon_last_day(customer: Customer, coupon_months: int) -> date | None:
    """Last day of the coupon period: the customer's first `coupon_months` months, start month = month 1."""
    if coupon_months <= 0:
        return None
    idx = customer.start.month - 1 + coupon_months - 1
    year = customer.start.year + idx // 12
    month = idx % 12 + 1
    return date(year, month, calendar.monthrange(year, month)[1])


def plan_in_force(customer: Customer, day: date) -> str:
    """The plan the customer is on for `day`, following the dated plan changes."""
    plan = customer.plan
    for change in customer.changes:
        if change.date > day:
            break
        plan = change.plan
    return plan


def is_annual_plan(plan: dict[str, Any]) -> bool:
    return plan.get("period") == "year"


def annual_billed_this_month(customer: Customer, month_start: date, month_end: date) -> bool:
    """Annual customers are billed in their start month and every 12 months after it,
    provided they are active on at least one day of that month."""
    offset = (month_start.year - customer.start.year) * 12 + (month_start.month - customer.start.month)
    if offset < 0 or offset % 12 != 0:
        return False
    return active_window(customer, month_start, month_end) is not None


def parse_customer(raw: dict[str, Any]) -> Customer:
    end_raw = raw.get("end")
    coupon_raw = raw.get("coupon")
    changes = sorted(
        (PlanChange(date=date.fromisoformat(c["date"]), plan=str(c["plan"])) for c in raw.get("changes") or []),
        key=lambda c: c.date,
    )
    return Customer(
        id=str(raw["id"]),
        country=str(raw["country"]),
        plan=str(raw["plan"]),
        start=date.fromisoformat(raw["start"]),
        end=None if end_raw is None else date.fromisoformat(end_raw),
        app_version=None if raw.get("app_version") is None else str(raw["app_version"]),
        coupon=None if coupon_raw is None else str(coupon_raw).upper(),
        changes=tuple(changes),
        vat_id=None if raw.get("vat_id") is None else str(raw["vat_id"]),
    )


def is_reverse_charge(customer: Customer) -> bool:
    """Business customers in DE and FR with a VAT id pay no VAT (reverse charge)."""
    has_vat_id = customer.vat_id is not None and customer.vat_id.strip() != ""
    return has_vat_id and customer.country in ("DE", "FR")


def annual_sek_amount(
    customer: Customer,
    plans: dict[str, Any],
    coupon: dict[str, Any] | None,
    coupon_end: date | None,
    month_start: date,
) -> Decimal:
    """Full yearly price in SEK for the billing month, with legacy discount and coupon applied.

    The coupon applies when the billing month falls within the coupon period.
    """
    price_sek = to_decimal(plans[customer.plan]["price"])
    if is_legacy(customer):
        price_sek *= LEGACY_DISCOUNT_FACTOR
    if coupon is not None and coupon_end is not None and month_start <= coupon_end:
        price_sek *= Decimal(1) - to_decimal(coupon["percent"]) / Decimal(100)
    return price_sek


def monthly_sek_amount(
    customer: Customer,
    plans: dict[str, Any],
    coupon: dict[str, Any] | None,
    coupon_end: date | None,
    first: date,
    last: date,
    days_in_month: int,
) -> Decimal:
    """Prorated SEK amount for a monthly plan. Each billable day is priced at the plan in force that day."""
    coupon_factor = Decimal(1) - to_decimal(coupon["percent"]) / Decimal(100) if coupon else Decimal(1)
    sek_total = Decimal(0)
    day = first
    while day <= last:
        price_sek = to_decimal(plans[plan_in_force(customer, day)]["price"])
        if is_legacy(customer):
            price_sek *= LEGACY_DISCOUNT_FACTOR
        if coupon_end is not None and day <= coupon_end:
            price_sek *= coupon_factor
        sek_total += price_sek
        day += timedelta(days=1)
    return sek_total / Decimal(days_in_month)


def build_invoices(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    year_str, month_str = str(data["month"]).split("-")
    year, month = int(year_str), int(month_str)
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    rates: dict[str, Any] = data.get("rates", {})
    plans: dict[str, Any] = data.get("plans", {})
    # Coupon codes match regardless of case; unknown codes do nothing.
    coupons: dict[str, Any] = {str(k).upper(): v for k, v in data.get("coupons", {}).items()}

    invoices: dict[str, dict[str, Any]] = {}
    for raw in data.get("customers", []):
        customer = parse_customer(raw)
        coupon = coupons.get(customer.coupon) if customer.coupon is not None else None
        coupon_end = coupon_last_day(customer, int(coupon["months"])) if coupon else None

        if is_annual_plan(plans[customer.plan]):
            if not annual_billed_this_month(customer, month_start, month_end):
                continue
            amount_sek = annual_sek_amount(customer, plans, coupon, coupon_end, month_start)
        else:
            window = billable_window(customer, month_start, month_end)
            if window is None:
                continue
            first, last = window
            amount_sek = monthly_sek_amount(
                customer, plans, coupon, coupon_end, first, last, days_in_month
            )

        currency = CURRENCY_BY_COUNTRY[customer.country]
        if currency == "SEK":
            amount = amount_sek
        else:
            amount = amount_sek / to_decimal(rates[currency])

        if currency == "EUR":
            net = round_money(amount)
        else:
            # SEK and NOK invoices are in whole kronor; halves round up.
            net = amount.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if is_reverse_charge(customer):
            vat = Decimal("0.00")
        else:
            vat = round_money(net * VAT_RATES[customer.country])
        total = net + vat

        # Tiny invoices are not sent: skip when the total, in SEK at the input rate, is below 10 SEK.
        total_sek = total if currency == "SEK" else total * to_decimal(rates[currency])
        if total_sek < MIN_INVOICE_SEK:
            continue

        invoices[customer.id] = {
            "currency": currency,
            "net": float(net),
            "vat": float(vat),
            "total": float(total),
        }
    return invoices


def main() -> None:
    data = json.loads(sys.stdin.readline())
    result = {"invoices": build_invoices(data)}
    sys.stdout.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
