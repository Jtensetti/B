"""Monthly invoices for a subscription service.

Reads one line of JSON from stdin and writes one line of JSON to stdout.
"""

from __future__ import annotations

import calendar
import json
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENT: Decimal = Decimal("0.01")
WHOLE_KRONA: Decimal = Decimal("1")
WHOLE_KRONA_CURRENCIES: frozenset[str] = frozenset({"SEK", "NOK"})
TRIAL_DAYS: int = 14

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

REVERSE_CHARGE_COUNTRIES: frozenset[str] = frozenset({"DE", "FR"})

LEGACY_CUTOFF: str = "2.0.0"
LEGACY_DISCOUNT: Decimal = Decimal("0.8")  # 20 % off the plan price

ANNUAL_PERIOD: str = "year"

MIN_INVOICE_SEK: Decimal = Decimal("10")  # invoices whose total is below this are left out


def parse_semver(text: str) -> tuple[tuple[int, int, int], tuple[str, ...]]:
    """Split a semver string into (major, minor, patch) and prerelease identifiers.

    Build metadata (after '+') is ignored, as semver precedence requires.
    """
    core: str = text.strip().split("+", 1)[0]
    pre: str = ""
    if "-" in core:
        core, pre = core.split("-", 1)
    major, minor, patch = (int(part) for part in core.split("."))
    prerelease: tuple[str, ...] = tuple(pre.split(".")) if pre else ()
    return (major, minor, patch), prerelease


def _compare_identifier(a: str, b: str) -> int:
    a_num: bool = a.isdigit()
    b_num: bool = b.isdigit()
    if a_num and b_num:
        return (int(a) > int(b)) - (int(a) < int(b))
    if a_num != b_num:
        # Numeric identifiers rank lower than alphanumeric ones.
        return -1 if a_num else 1
    return (a > b) - (a < b)


def compare_semver(a_text: str, b_text: str) -> int:
    """Return -1, 0 or 1 as version a is lower, equal or higher than version b."""
    a_core, a_pre = parse_semver(a_text)
    b_core, b_pre = parse_semver(b_text)
    if a_core != b_core:
        return -1 if a_core < b_core else 1
    if not a_pre and not b_pre:
        return 0
    # A release outranks any prerelease of the same version.
    if not a_pre:
        return 1
    if not b_pre:
        return -1
    for a_id, b_id in zip(a_pre, b_pre):
        result: int = _compare_identifier(a_id, b_id)
        if result != 0:
            return result
    return (len(a_pre) > len(b_pre)) - (len(a_pre) < len(b_pre))


def is_legacy(app_version: str) -> bool:
    """Customers on a version below 2.0.0 (prereleases of 2.0.0 included) keep legacy pricing."""
    return compare_semver(app_version, LEGACY_CUTOFF) < 0


def billable_days_by_plan(
    customer: dict[str, Any],
    billing_start: date,
    end: date | None,
    month_start: date,
    month_end: date,
) -> dict[str, int]:
    """Count billable days per plan; a plan change takes effect on its date."""
    changes: list[tuple[date, str]] = sorted(
        (date.fromisoformat(change["date"]), str(change["plan"]))
        for change in customer.get("changes") or []
    )
    lo: date = max(billing_start, month_start)
    hi: date = month_end if end is None else min(end, month_end)
    counts: dict[str, int] = {}
    day: date = lo
    while day <= hi:
        plan_name: str = customer["plan"]
        for change_date, change_plan in changes:
            if change_date > day:
                break
            plan_name = change_plan
        counts[plan_name] = counts.get(plan_name, 0) + 1
        day += timedelta(days=1)
    return counts


def is_annual_billing_month(
    start: date,
    end: date | None,
    year: int,
    month: int,
    month_start: date,
    month_end: date,
) -> bool:
    """An annual customer is billed in the start month and every 12 months after it,
    provided they are active on at least one day of that month."""
    month_index: int = (year * 12 + month) - (start.year * 12 + start.month)
    if month_index < 0 or month_index % 12 != 0:
        return False
    if start > month_end:
        return False
    return end is None or end >= month_start


def build_invoices(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compute the invoice for each customer with at least one billable day."""
    year_text, month_text = str(data["month"]).split("-")
    year: int = int(year_text)
    month: int = int(month_text)
    days_in_month: int = calendar.monthrange(year, month)[1]
    month_start: date = date(year, month, 1)
    month_end: date = date(year, month, days_in_month)

    rates: dict[str, Decimal] = {
        code: Decimal(str(value)) for code, value in data["rates"].items()
    }
    prices: dict[str, Decimal] = {
        name: Decimal(str(plan["price"])) for name, plan in data["plans"].items()
    }
    annual_plans: set[str] = {
        name
        for name, plan in data["plans"].items()
        if plan.get("period", "month") == ANNUAL_PERIOD
    }

    # Coupon codes match without regard to case.
    coupons: dict[str, dict[str, Any]] = {
        str(code).casefold(): spec for code, spec in (data.get("coupons") or {}).items()
    }

    invoices: dict[str, dict[str, Any]] = {}
    for customer in data["customers"]:
        start: date = date.fromisoformat(customer["start"])
        end_text: str | None = customer.get("end")
        end: date | None = date.fromisoformat(end_text) if end_text else None
        is_annual: bool = customer["plan"] in annual_plans

        if is_annual:
            # Annual plans get no free trial and are never prorated.
            if not is_annual_billing_month(
                start, end, year, month, month_start, month_end
            ):
                continue
            billable_per_plan: dict[str, int] = {}
        else:
            # New customers get a 14-day free trial: the start day and the 13 days after it.
            billing_start: date = start + timedelta(days=TRIAL_DAYS)
            billable_per_plan = billable_days_by_plan(
                customer, billing_start, end, month_start, month_end
            )
            if sum(billable_per_plan.values()) == 0:
                continue

        country: str = customer["country"]
        currency: str = CURRENCY_BY_COUNTRY[country]
        # Discount factor applied to every billed amount of this customer's month.
        factor: Decimal = Decimal(1)
        if is_legacy(str(customer["app_version"])):
            factor *= LEGACY_DISCOUNT

        coupon_code: str | None = customer.get("coupon")
        coupon: dict[str, Any] | None = (
            coupons.get(str(coupon_code).casefold()) if coupon_code else None
        )
        if coupon is not None:
            # Month 1 is the start month; the coupon covers the first `months` months.
            month_index: int = (year * 12 + month) - (start.year * 12 + start.month)
            if 0 <= month_index < int(coupon["months"]):
                percent: Decimal = Decimal(str(coupon["percent"]))
                factor *= 1 - percent / 100

        if is_annual:
            # Full yearly price, not prorated.
            amount_sek: Decimal = prices[customer["plan"]] * factor
        else:
            # Each billable day is billed at the price of the plan in force that day.
            amount_sek = sum(
                (
                    prices[plan_name] * factor * count
                    for plan_name, count in billable_per_plan.items()
                ),
                Decimal(0),
            ) / days_in_month

        if currency == "SEK":
            amount: Decimal = amount_sek
        else:
            # Rates are SEK per unit of the foreign currency.
            amount = amount_sek / rates[currency]

        # SEK and NOK net amounts are whole kronor; EUR net amounts are cents.
        net_quantum: Decimal = WHOLE_KRONA if currency in WHOLE_KRONA_CURRENCIES else CENT
        net: Decimal = amount.quantize(net_quantum, rounding=ROUND_HALF_UP)
        # Reverse charge: German and French business customers (non-empty vat_id) pay no VAT.
        vat_id: str = str(customer.get("vat_id") or "").strip()
        if country in REVERSE_CHARGE_COUNTRIES and vat_id:
            vat: Decimal = Decimal("0.00")
        else:
            vat = (net * VAT_BY_COUNTRY[country]).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
        total: Decimal = net + vat

        # Tiny invoices are not sent: the total in SEK must be at least the minimum.
        total_sek: Decimal = total if currency == "SEK" else total * rates[currency]
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
    invoices = build_invoices(data)
    sys.stdout.write(json.dumps({"invoices": invoices}) + "\n")


if __name__ == "__main__":
    main()
