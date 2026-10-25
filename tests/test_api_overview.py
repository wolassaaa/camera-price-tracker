from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from camera_tracker.api import create_app
from camera_tracker.normalization import normalize_quote
from camera_tracker.repository import SqliteRepository


def test_overview_returns_current_quote_and_history_count_per_product(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    repository.record_quote(
        normalize_quote(product_id="sony-a7v", platform="sony_cn", shop_name="Sony", url="https://example.test", list_price=Decimal("19999")),
        captured_at=datetime(2026, 7, 23, tzinfo=timezone.utc), raw_payload={},
    )

    response = TestClient(create_app(repository=repository)).get("/api/overview")

    row = next(item for item in response.json() if item["product_id"] == "sony-a7v")
    assert row["current_price"] == "19999"
    assert row["history_points"] == 1
