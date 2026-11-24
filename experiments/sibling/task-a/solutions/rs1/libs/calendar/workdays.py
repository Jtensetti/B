"""Swedish working days. Maintained by the operations team."""
from datetime import date, timedelta

# Swedish public holidays in 2026 (ISO dates).
HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14",
    "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
}


def is_workday(iso_date: str) -> bool:
    """True for Monday to Friday that is not a Swedish public holiday."""
    d = date.fromisoformat(iso_date)
    return d.weekday() < 5 and iso_date not in HOLIDAYS_2026


def next_workday(iso_date: str) -> str:
    """The first working day strictly after the given date."""
    d = date.fromisoformat(iso_date) + timedelta(days=1)
    while not is_workday(d.isoformat()):
        d += timedelta(days=1)
    return d.isoformat()
