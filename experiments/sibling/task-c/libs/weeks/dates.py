"""Calendar helpers. Maintained by the operations team."""
from datetime import date, timedelta


def add_days(iso_date: str, days: int) -> str:
    """The date the given number of days after iso_date."""
    return (date.fromisoformat(iso_date) + timedelta(days=days)).isoformat()


def iso_week(iso_date: str) -> int:
    """The ISO week number (1-53) of a date."""
    return date.fromisoformat(iso_date).isocalendar()[1]


def to_weekday(iso_date: str) -> str:
    """The date itself on Monday to Friday; the following Monday for a Saturday or Sunday."""
    d = date.fromisoformat(iso_date)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()
