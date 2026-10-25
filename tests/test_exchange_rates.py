from datetime import date
from decimal import Decimal

from camera_tracker.exchange_rates import HkdRate, fetch_hkd_rate, hkd_to_cny
from camera_tracker.repository import SqliteRepository


def test_exchange_rate_is_saved_by_date_and_preserves_historical_conversion(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    repository.save_exchange_rate(HkdRate(date(2026, 7, 22), Decimal("0.91"), "test"))
    repository.save_exchange_rate(HkdRate(date(2026, 7, 23), Decimal("0.92"), "test"))

    rate = repository.exchange_rate("HKD", date(2026, 7, 22))

    assert hkd_to_cny(Decimal("100"), rate) == Decimal("91.00")


def test_rate_fetcher_reads_hkd_to_cny_payload() -> None:
    rate = fetch_hkd_rate(lambda _: {"rates": {"CNY": 0.92}})

    assert rate.cny_per_hkd == Decimal("0.92")
