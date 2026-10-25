from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

import camera_tracker.repository as repository
from camera_tracker.normalization import normalize_quote


def test_repository_keeps_raw_quote_and_a_historical_price_point(tmp_path) -> None:
    db = repository.SqliteRepository(tmp_path / "tracker.db")
    db.migrate()
    quote = normalize_quote(
        product_id="sony-a7v", platform="sony_cn", shop_name="Sony Official",
        url="https://example.test/a7v", list_price=Decimal("19999"),
    )

    db.record_quote(quote, captured_at=datetime(2026, 7, 23, tzinfo=timezone.utc), raw_payload={"price": "19999"})

    points = db.price_history("sony-a7v")
    assert len(points) == 1
    assert points[0].final_price == Decimal("19999")
    assert db.raw_snapshot_count() == 1


def test_repository_migrates_and_preserves_extended_quote_terms(tmp_path) -> None:
    db = repository.SqliteRepository(tmp_path / "tracker.db")
    db.migrate()
    quote = normalize_quote(
        product_id="sony-a1", platform="goofish", shop_name="Seller", url="https://example.test",
        list_price=Decimal("10000"), member_price=Decimal("9000"), payment_discount=Decimal("100"),
        tax=Decimal("20"), stock_status="in_stock", shutter_count=5000,
    )

    db.record_quote(quote, captured_at=datetime(2026, 7, 23, tzinfo=timezone.utc), raw_payload={})

    row = db.latest_market_quotes("sony-a1")[0]
    assert row["member_price"] == "9000"
    assert row["shutter_count"] == 5000


def test_reference_history_uses_cny_for_hong_kong_quotes(tmp_path) -> None:
    db = repository.SqliteRepository(tmp_path / "tracker.db")
    db.migrate()
    db.record_quote(
        normalize_quote(
            product_id="sony-a1m2", platform="price_com_hk", shop_name="Shop", url="https://example.test",
            list_price=Decimal("30000"), currency="HKD", exchange_rate_to_cny=Decimal("0.9"),
            market_variant="hk_grey",
        ),
        captured_at=datetime(2026, 7, 23, tzinfo=timezone.utc), raw_payload={},
    )

    assert db.cny_reference_history("sony-a1m2")[0].final_price == Decimal("27000.0")


def test_reference_history_excludes_quotes_pending_manual_confirmation(tmp_path) -> None:
    db = repository.SqliteRepository(tmp_path / "tracker.db")
    db.migrate()
    for price, pending in [(Decimal("30000"), False), (Decimal("10000"), True)]:
        db.record_quote(
            normalize_quote(product_id="sony-a1", platform="shop", shop_name="Shop", url="https://example.test", list_price=price),
            captured_at=datetime(2026, 7, 23, tzinfo=timezone.utc), raw_payload={},
            trust_score=35 if pending else 90, manual_confirmation_required=pending,
        )

    assert [point.final_price for point in db.cny_reference_history("sony-a1")] == [Decimal("30000")]


def test_persistent_notification_state_obeys_cooldown_and_can_be_reset(tmp_path) -> None:
    db = repository.SqliteRepository(tmp_path / "tracker.db")
    db.migrate()
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)

    assert db.notification_due(product_id="canon-r5m2", event="target_price_reached", now=now, cooldown_seconds=3600)
    db.mark_notification_sent(product_id="canon-r5m2", event="target_price_reached", now=now)
    assert not db.notification_due(product_id="canon-r5m2", event="target_price_reached", now=now, cooldown_seconds=3600)
    db.reset_notification_state(product_id="canon-r5m2", event="target_price_reached")
    assert db.notification_due(product_id="canon-r5m2", event="target_price_reached", now=now, cooldown_seconds=3600)


def test_migration_upgrades_legacy_quotes_table_without_losing_existing_row(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE quotes (
                id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, platform TEXT NOT NULL,
                shop_name TEXT NOT NULL, url TEXT NOT NULL, captured_at TEXT NOT NULL,
                final_price TEXT NOT NULL, currency TEXT NOT NULL, reference_cny TEXT,
                condition TEXT NOT NULL, market_variant TEXT NOT NULL,
                warranty_type TEXT NOT NULL, bundle_type TEXT NOT NULL
            )"""
        )
        connection.execute(
            """INSERT INTO quotes VALUES (1, 'sony-a1', 'legacy', 'Legacy Shop', 'https://example.test',
               '2026-07-23T00:00:00+00:00', '10000', 'CNY', '10000', 'new', 'cn', 'manufacturer', 'body_only')"""
        )

    db = repository.SqliteRepository(path)
    db.migrate()

    row = db.latest_market_quotes("sony-a1")[0]
    assert row["final_price"] == "10000"
    assert row["cash_price_only"] == 0
    assert db.notification_due(product_id="sony-a1", event="target_price_reached", now=datetime(2026, 7, 23, tzinfo=timezone.utc), cooldown_seconds=60)
