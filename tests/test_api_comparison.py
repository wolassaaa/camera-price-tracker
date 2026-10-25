from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from camera_tracker.api import create_app
from camera_tracker.normalization import normalize_quote
from camera_tracker.repository import SqliteRepository


def test_market_comparison_keeps_hkd_and_cny_reference_separate(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    timestamp = datetime(2026, 7, 23, tzinfo=timezone.utc)
    repository.record_quote(normalize_quote(product_id="canon-r5m2", platform="canon_cn", shop_name="Canon CN", url="https://cn.test", list_price=Decimal("30599")), captured_at=timestamp, raw_payload={})
    repository.record_quote(normalize_quote(product_id="canon-r5m2", platform="canon_hk", shop_name="Canon HK", url="https://hk.test", list_price=Decimal("28180"), currency="HKD", exchange_rate_to_cny=Decimal("0.92"), market_variant="hk_authorized"), captured_at=timestamp, raw_payload={})

    response = TestClient(create_app(repository=repository)).get("/api/products/canon-r5m2/comparison")

    assert response.status_code == 200
    assert response.json()["cn"]["final_price"] == "30599"
    assert response.json()["hk"]["currency"] == "HKD"
    assert response.json()["hk"]["reference_cny"] == "25925.60"
    assert response.json()["spread"]["cheaper_market"] == "hk"
    assert response.json()["spread"]["difference_cny"] == "4673.40"


def test_metrics_keep_official_authorized_and_grey_market_metrics_distinct(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    timestamp = datetime(2026, 7, 23, tzinfo=timezone.utc)
    for platform, price, variant in [
        ("canon_cn", "30599", "cn"), ("price_com_hk", "20000", "hk_grey"), ("shop", "29000", "hk_authorized"),
    ]:
        repository.record_quote(
            normalize_quote(product_id="canon-r5m2", platform=platform, shop_name=platform, url=f"https://{platform}.test", list_price=Decimal(price), market_variant=variant),
            captured_at=timestamp, raw_payload={}, trust_score=90,
        )

    response = TestClient(create_app(repository=repository)).get("/api/products/canon-r5m2/metrics")

    assert response.status_code == 200
    assert response.json()["official_trusted_low_cny"] == "30599"
    assert response.json()["authorized_trusted_low_cny"] == "29000"
    assert response.json()["market_trusted_low_cny"] == "20000"
