from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from camera_tracker.api import create_app
from camera_tracker.normalization import normalize_quote
from camera_tracker.repository import SqliteRepository


def test_recommendation_endpoint_explains_a_low_reliable_price(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(35):
        repository.record_quote(
            normalize_quote(product_id="sony-a7v", platform="sony_cn", shop_name="Sony", url="https://example.test", list_price=Decimal(12000 - index * 10)),
            captured_at=start + timedelta(days=index), raw_payload={},
        )

    response = TestClient(create_app(repository=repository)).get("/api/products/sony-a7v/recommendation")

    assert response.status_code == 200
    assert response.json()["label"] in {"可以购买", "建议观望"}
    assert response.json()["reason"]
