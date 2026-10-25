from decimal import Decimal
import pytest

from camera_tracker.collector import collect_jsonld_watch
from camera_tracker.collector import run_jsonld_watch
from camera_tracker.collector import collect_price_com_watch
from camera_tracker.collector import run_watch
from camera_tracker.repository import SqliteRepository
from camera_tracker.source_status import SourceStatusRegistry
from camera_tracker.exchange_rates import HkdRate
from datetime import date, datetime, timezone


def test_collector_fetches_public_page_and_returns_normalized_quote() -> None:
    html = '<script type="application/ld+json">{"@type":"Product","offers":{"price":"19999","priceCurrency":"CNY","availability":"https://schema.org/InStock"}}</script>'

    quotes = collect_jsonld_watch(
        {"product_id": "sony-a7v", "platform": "sony_cn", "shop_name": "Sony", "url": "https://example.test"},
        fetch=lambda _: html,
    )

    assert quotes[0].final_price == Decimal("19999")
    assert quotes[0].platform == "sony_cn"


def test_runner_persists_quote_and_records_success(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    status = SourceStatusRegistry()
    html = '<script type="application/ld+json">{"@type":"Product","offers":{"price":"19999","priceCurrency":"CNY"}}</script>'

    count = run_jsonld_watch(
        {"product_id": "sony-a7v", "platform": "sony_cn", "shop_name": "Sony", "url": "https://example.test"},
        repository=repository, status=status, fetch=lambda _: html,
    )

    assert count == 1
    assert repository.price_history("sony-a7v")[0].final_price == Decimal("19999")
    assert status.get("sony_cn").consecutive_failures == 0


def test_price_com_collector_preserves_hkd_and_market_variant() -> None:
    html = '<p class="quotation-merchant-name">Camera</p><div class="quote-price-water">現金<span data-price="38450.0"></span></div>'

    quotes = collect_price_com_watch(
        {"product_id": "sony-a1m2", "platform": "price_com_hk", "shop_name": "Price.com.hk", "url": "https://example.test"},
        fetch=lambda _: html,
    )

    assert quotes[0].currency == "HKD"
    assert quotes[0].market_variant == "hk_grey"
    assert quotes[0].cash_price_only is True


def test_generic_runner_selects_price_com_adapter(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    status = SourceStatusRegistry()
    html = '<p class="quotation-merchant-name">Camera</p><div class="quote-price-water"><span data-price="38450.0"></span></div>'

    count = run_watch(
        {"product_id": "sony-a1m2", "platform": "price_com_hk", "shop_name": "Price", "url": "https://example.test", "adapter": "price_com_hk"},
        repository=repository, status=status, fetch=lambda _: html,
        rate_fetch=lambda: HkdRate(date(2026, 7, 23), Decimal("0.92"), "test"),
    )

    assert count == 1
    assert repository.price_history("sony-a1m2")[0].final_price == Decimal("38450.0")
    assert repository.exchange_rate("HKD", date(2026, 7, 23)).cny_per_hkd == Decimal("0.92")
    assert repository.latest_market_quotes("sony-a1m2")[0]["cash_price_only"] == 0
    assert any(row["source_id"] == "price_com_hk:Camera" for row in repository.source_health())


def test_hkd_runner_reuses_the_stored_daily_exchange_rate(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    status = SourceStatusRegistry()
    calls = 0
    html = '<p class="quotation-merchant-name">Camera</p><div class="quote-price-water"><span data-price="38450.0"></span></div>'

    def rate_fetch():
        nonlocal calls
        calls += 1
        return HkdRate(date.today(), Decimal("0.92"), "test")

    watch = {"product_id": "sony-a1m2", "platform": "price_com_hk", "shop_name": "Price", "url": "https://example.test", "adapter": "price_com_hk"}
    run_watch(watch, repository=repository, status=status, fetch=lambda _: html, rate_fetch=rate_fetch)
    run_watch(watch, repository=repository, status=status, fetch=lambda _: html, rate_fetch=rate_fetch)

    assert calls == 1


def test_generic_runner_selects_canon_cn_adapter(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    status = SourceStatusRegistry()

    count = run_watch(
        {"product_id": "canon-r5m2", "platform": "canon_cn", "shop_name": "Canon", "url": "https://example.test", "adapter": "canon_cn"},
        repository=repository, status=status,
        fetch=lambda _: '<script>{"rawprice":30599,"price":30599,"quantity":"4"}</script>',
    )

    assert count == 1
    assert repository.price_history("canon-r5m2")[0].final_price == Decimal("30599")


def test_generic_runner_selects_canon_hk_adapter(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()

    count = run_watch(
        {"product_id": "canon-r5m2", "platform": "canon_hk", "shop_name": "Canon", "url": "https://example.test", "adapter": "canon_hk"},
        repository=repository, status=SourceStatusRegistry(),
        fetch=lambda _: '<script>{"price":30580.00}</script>',
        rate_fetch=lambda: HkdRate(date(2026, 7, 23), Decimal("0.92"), "test"),
    )

    assert count == 1
    assert repository.latest_market_quotes("canon-r5m2")[0]["currency"] == "HKD"


def test_generic_runner_selects_canon_hk_store_adapter(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()

    count = run_watch(
        {"product_id": "canon-r5m2", "platform": "canon_hk_store", "shop_name": "Canon", "url": "https://example.test", "adapter": "canon_hk_store"},
        repository=repository, status=SourceStatusRegistry(),
        fetch=lambda _: '<script>{"product":{"variants":[{"price":2818000}]}}</script>',
        rate_fetch=lambda: HkdRate(date(2026, 7, 23), Decimal("0.92"), "test"),
    )

    assert count == 1
    assert repository.price_history("canon-r5m2")[0].final_price == Decimal("28180")


def test_runner_notifies_when_official_stock_recovers(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    watch = {"product_id": "canon-r5m2", "platform": "canon_cn", "shop_name": "Canon", "url": "https://example.test", "adapter": "canon_cn"}
    status = SourceStatusRegistry()
    alerts: list[dict[str, str]] = []

    run_watch(
        watch, repository=repository, status=status,
        fetch=lambda _: '<script>{"rawprice":30599,"quantity":"0"}</script>', notifier=alerts.append,
    )
    run_watch(
        watch, repository=repository, status=status,
        fetch=lambda _: '<script>{"rawprice":30599,"quantity":"3"}</script>', notifier=alerts.append,
    )

    assert [alert["event"] for alert in alerts] == ["restocked"]


def test_runner_escalates_a_source_after_three_failures(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    watch = {"product_id": "sony-a7v", "platform": "broken", "shop_name": "Broken", "url": "https://example.test", "adapter": "missing"}
    status = SourceStatusRegistry()
    alerts: list[dict[str, str]] = []

    for _ in range(3):
        with pytest.raises(ValueError, match="Unsupported adapter"):
            run_watch(watch, repository=repository, status=status, source_notifier=alerts.append)

    assert alerts[-1]["event"] == "source_manual_attention"
    assert alerts[-1]["product"] == "source:broken"


def test_target_price_recovery_resets_persistent_notification_state(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    now = datetime.now(timezone.utc)
    repository.mark_notification_sent(product_id="canon-r5m2", event="target_price_reached", now=now)
    watch = {"product_id": "canon-r5m2", "platform": "canon_cn", "shop_name": "Canon", "url": "https://example.test", "adapter": "canon_cn"}

    run_watch(
        watch, repository=repository, status=SourceStatusRegistry(),
        fetch=lambda _: '<script>{"rawprice":30599,"quantity":"2"}</script>',
        target_prices={"canon-r5m2": Decimal("30000")}, notifier=lambda _: None,
    )

    assert repository.notification_due(product_id="canon-r5m2", event="target_price_reached", now=now, cooldown_seconds=24 * 3600)
