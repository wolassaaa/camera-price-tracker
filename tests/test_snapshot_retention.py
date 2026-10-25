from datetime import datetime, timedelta, timezone
from decimal import Decimal

from camera_tracker.normalization import normalize_quote
from camera_tracker.repository import SqliteRepository


def test_snapshot_cleanup_keeps_recent_evidence_and_removes_expired_data(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    quote = normalize_quote(product_id="sony-a7v", platform="sony_cn", shop_name="Sony", url="https://example.test", list_price=Decimal("19999"))
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    repository.record_quote(quote, captured_at=now - timedelta(days=31), raw_payload={"old": True})
    repository.record_quote(quote, captured_at=now - timedelta(days=2), raw_payload={"new": True})

    removed = repository.prune_raw_snapshots(before=now - timedelta(days=30))

    assert removed == 1
    assert repository.raw_snapshot_count() == 1
