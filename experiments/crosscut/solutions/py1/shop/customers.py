"""Customers and their membership."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Customer:
    id: str
    country: str
    member: bool

    @property
    def currency(self) -> str:
        """Norwegian customers are invoiced in NOK, everyone else in SEK."""
        return "NOK" if self.country == "NO" else "SEK"


def load_customers(raw: list[dict[str, Any]]) -> dict[str, Customer]:
    return {str(c["id"]): Customer(str(c["id"]), str(c["country"]).upper(), bool(c.get("member", False)))
            for c in raw}
