#!/usr/bin/env python3
"""Monthly subscription invoices.

Reads one line of JSON from stdin and writes one line of JSON to stdout.
"""

from __future__ import annotations

import calendar
import json
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CURRENCY_BY_COUNTRY: dict[str, str] = {
    "SE": "SEK",
    "NO": "NOK",
    "DE": "EUR",
    "FR": "EUR",
}

VAT_BY_COUNTRY: dict[str, Decimal] = {
    "SE": Decimal("0.25"),
    "NO": Decimal("0.25"),
    "DE": Decimal("0.19"),
    "FR": Decimal("0.20"),
}

CENT: Decimal = Decimal("0.01")

REVERSE_CHARGE_COUNTRIES: frozenset[str] = frozenset({"DE", "FR"})

MIN_INVOICE_SEK: Decimal = Decimal(10)

WHOLE_KRONOR_CURRENCIES: frozenset[str] = frozenset({"SEK", "NOK"})

TRIAL_DAYS: int = 14


LEGACY_VERSION_CUTOFF: str = "2.0.0"
LEGACY_DISCOUNT: Decimal = Decimal("0.20")


def round2(value: Decimal) -> Decimal:
    """Round to 2 decimals, halves away from zero."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _parse_semver(text: str) -> tuple[tuple[int, int, int], list[str] | None]:
    """Split 'MAJOR.MINOR.PATCH[-pre][+build]' into the core triple and prerelease ids."""
    core_and_pre = text.split("+", 1)[0]
    core, _, pre = core_and_pre.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    return (major, minor, patch), (pre.split(".") if pre else None)


def _compare_prerelease_ids(a: list[str], b: list[str]) -> int:
    """Compare prerelease identifier lists per semver precedence rules."""
    for left, right in zip(a, b):
        if left == right:
            continue
        left_num, right_num = left.isdigit(), right.isdigit()
        if left_num and right_num:
            return -1 if int(left) < int(right) else 1
        if left_num != right_num:
            # Numeric identifiers rank below alphanumeric ones.
            return -1 if left_num else 1
        return -1 if left < right else 1
    if len(a) == len(b):
        return 0
    return -1 if len(a) < len(b) else 1


def compare_semver(a: str, b: str) -> int:
    """Return -1, 0 or 1 as version a is lower than, equal to or higher than b."""
    core_a, pre_a = _parse_semver(a)
    core_b, pre_b = _parse_semver(b)
    if core_a != core_b:
        return -1 if core_a < core_b else 1
    if pre_a is None and pre_b is None:
        return 0
    # A prerelease has lower precedence than the normal version.
    if pre_a is None:
        return 1
    if pre_b is None:
        return -1
    return _compare_prerelease_ids(pre_a, pre_b)


def is_legacy_version(app_version: str) -> bool:
    """Customers on a version below 2.0.0 (prereleases of 2.0.0 included) keep legacy pricing."""
    return compare_semver(app_version, LEGACY_VERSION_CUTOFF) < 0


def parse_month(text: str) -> tuple[int, int]:
    """Parse a 'YYYY-MM' string into (year, month)."""
    year_text, month_text = text.split("-")
    return int(year_text), int(month_text)


def billable_days(
    start: date,
    end: date | None,
    month_start: date,
    month_end: date,
) -> int:
    """Count the billable days in [start, end] (end None = open) that fall inside the month.

    The start day and the 13 days after it are a free trial and never billable.
    """
    first = max(start + timedelta(days=TRIAL_DAYS), month_start)
    last = month_end if end is None else min(end, month_end)
    if last < first:
        return 0
    return (last - first).days + 1


def annual_billed(
    start: date,
    end: date | None,
    year: int,
    month: int,
    month_start: date,
    month_end: date,
) -> bool:
    """True if an annual customer is billed this month.

    Billed in the start month and every 12th month after it, provided the
    customer is active on at least one day of that month. No trial applies.
    """
    offset = (year * 12 + month) - (start.year * 12 + start.month)
    if offset < 0 or offset % 12 != 0:
        return False
    last = month_end if end is None else min(end, month_end)
    return last >= max(start, month_start)


def coupon_applies(start: date, year: int, month: int, months: int) -> bool:
    """True if (year, month) is within the first `months` calendar months from start's month."""
    offset = (year * 12 + month) - (start.year * 12 + start.month)
    return 0 <= offset < months


def build_invoices(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compute one invoice per customer that has at least one billable day."""
    year, month = parse_month(data["month"])
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    rates: dict[str, Decimal] = {
        code: Decimal(str(rate)) for code, rate in data["rates"].items()
    }
    prices: dict[str, Decimal] = {
        name: Decimal(str(plan["price"])) for name, plan in data["plans"].items()
    }
    # Coupon codes match regardless of case.
    coupons: dict[str, dict[str, Any]] = {
        code.upper(): spec for code, spec in data.get("coupons", {}).items()
    }

    invoices: dict[str, dict[str, Any]] = {}
    for customer in data["customers"]:
        start = date.fromisoformat(customer["start"])
        end_text = customer.get("end")
        end = date.fromisoformat(end_text) if end_text else None

        is_annual = data["plans"][customer["plan"]].get("period") == "year"
        if is_annual:
            if not annual_billed(start, end, year, month, month_start, month_end):
                continue
            days = 0
        else:
            days = billable_days(start, end, month_start, month_end)
            if days == 0:
                continue

        country = customer["country"]
        currency = CURRENCY_BY_COUNTRY[country]

        # Discounts that apply to every billable day of this month.
        factor = Decimal(1)
        if is_legacy_version(customer["app_version"]):
            factor *= Decimal(1) - LEGACY_DISCOUNT
        coupon_code = customer.get("coupon")
        if coupon_code:
            spec = coupons.get(coupon_code.upper())
            if spec is not None and coupon_applies(start, year, month, int(spec["months"])):
                factor *= Decimal(1) - Decimal(str(spec["percent"])) / Decimal(100)

        # Plan changes, sorted by date; each billable day uses the plan in force that day.
        changes: list[tuple[date, str]] = sorted(
            (date.fromisoformat(change["date"]), change["plan"])
            for change in customer.get("changes") or []
        )
        first_day = max(start + timedelta(days=TRIAL_DAYS), month_start)

        if is_annual:
            # Annual plans are billed the full yearly price, never prorated or changed.
            sek_amount = prices[customer["plan"]] * factor
        else:
            sek_amount = Decimal(0)
            for offset in range(days):
                day = first_day + timedelta(days=offset)
                plan_name = customer["plan"]
                for change_date, new_plan in changes:
                    if change_date <= day:
                        plan_name = new_plan
                sek_amount += prices[plan_name] * factor / days_in_month
        if currency == "SEK":
            amount = sek_amount
        else:
            amount = sek_amount / rates[currency]

        # SEK and NOK invoices are in whole kronor; EUR keeps cents.
        if currency in WHOLE_KRONOR_CURRENCIES:
            net = amount.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        else:
            net = round2(amount)
        # Reverse charge: business customers in DE and FR with a VAT id pay no VAT.
        reverse_charge = country in REVERSE_CHARGE_COUNTRIES and bool(
            (customer.get("vat_id") or "").strip()
        )
        vat_rate = Decimal(0) if reverse_charge else VAT_BY_COUNTRY[country]
        vat = round2(net * vat_rate)
        total = net + vat

        # Tiny invoices are not sent: skip when the total is below 10 SEK.
        total_sek = total if currency == "SEK" else total * rates[currency]
        if total_sek < MIN_INVOICE_SEK:
            continue

        invoices[customer["id"]] = {
            "currency": currency,
            "net": float(net),
            "vat": float(vat),
            "total": float(total),
        }

    return invoices


def main() -> None:
    data: dict[str, Any] = json.loads(sys.stdin.read())
    result = {"invoices": build_invoices(data)}
    sys.stdout.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
