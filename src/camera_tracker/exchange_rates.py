"""Historical foreign-exchange handling for cross-market comparison."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from collections.abc import Callable

import httpx


@dataclass(frozen=True)
class HkdRate:
    rate_date: date
    cny_per_hkd: Decimal
    source: str


def hkd_to_cny(amount: Decimal, rate: HkdRate) -> Decimal:
    return (amount * rate.cny_per_hkd).quantize(Decimal("0.01"))


def fetch_hkd_rate(
    fetch_json: Callable[[str], dict[str, object]] | None = None,
    *, rate_date: date | None = None,
) -> HkdRate:
    """Fetch a daily public HKD base rate; callers persist the dated result."""
    if fetch_json is None:
        response = httpx.get("https://open.er-api.com/v6/latest/HKD", timeout=20)
        response.raise_for_status()
        payload = response.json()
    else:
        payload = fetch_json("https://open.er-api.com/v6/latest/HKD")
    try:
        value = payload["rates"]["CNY"]  # type: ignore[index]
    except (KeyError, TypeError) as exc:
        raise ValueError("HKD/CNY rate missing from provider response") from exc
    return HkdRate(rate_date or date.today(), Decimal(str(value)), "open.er-api.com")
