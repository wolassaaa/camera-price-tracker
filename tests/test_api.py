from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import shutil

from camera_tracker.api import create_app
from camera_tracker.normalization import normalize_quote
from camera_tracker.repository import SqliteRepository


def test_health_endpoint_reports_local_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_notification_test_endpoint_reports_configured_delivery(monkeypatch) -> None:
    monkeypatch.setattr("camera_tracker.api.send_all", lambda _config, _payload: ["webhook"])

    response = TestClient(create_app()).post("/api/notifications/test")

    assert response.status_code == 200
    assert response.json()["delivered"] == ["webhook"]


def test_products_endpoint_reads_configured_catalog() -> None:
    response = TestClient(create_app()).get("/api/products")

    assert response.status_code == 200
    assert any(product["id"] == "sony-a7v" for product in response.json())


def test_history_endpoint_returns_recorded_price_points(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    repository.record_quote(
        normalize_quote(product_id="sony-a7v", platform="sony_cn", shop_name="Sony", url="https://example.test", list_price=Decimal("19999")),
        captured_at=datetime(2026, 7, 23, tzinfo=timezone.utc), raw_payload={},
    )

    response = TestClient(create_app(repository=repository)).get("/api/products/sony-a7v/history")

    assert response.status_code == 200
    assert response.json()[0]["final_price"] == "19999"


def test_history_endpoint_filters_to_requested_time_window(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for offset in range(10):
        repository.record_quote(
            normalize_quote(product_id="sony-a7v", platform="sony_cn", shop_name="Sony", url="https://example.test", list_price=Decimal("19999")),
            captured_at=start + timedelta(days=offset), raw_payload={},
        )

    response = TestClient(create_app(repository=repository)).get("/api/products/sony-a7v/history?window=7d")

    assert response.status_code == 200
    assert len(response.json()) == 8


def test_history_endpoint_does_not_mix_hk_grey_and_cn_segments(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    timestamp = datetime(2026, 7, 23, tzinfo=timezone.utc)
    repository.record_quote(normalize_quote(product_id="sony-a1", platform="cn", shop_name="CN", url="https://cn.test", list_price=Decimal("20000")), captured_at=timestamp, raw_payload={})
    repository.record_quote(normalize_quote(product_id="sony-a1", platform="hk", shop_name="HK", url="https://hk.test", list_price=Decimal("15000"), currency="HKD", exchange_rate_to_cny=Decimal("0.9"), market_variant="hk_grey"), captured_at=timestamp, raw_payload={})

    response = TestClient(create_app(repository=repository)).get("/api/products/sony-a1/history?segment=hk_grey")

    assert response.status_code == 200
    assert [row["final_price"] for row in response.json()] == ["13500.0"]


def test_manual_import_endpoint_persists_user_supplied_quote(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    csv = "product_id,platform,shop_name,url,price,condition,market_variant,warranty_type,bundle_type\nsony-a1,goofish,个人卖家,https://example.test/a1,9500,used,cn,none,body_only\n"

    response = TestClient(create_app(repository=repository)).post("/api/import/csv", content=csv, headers={"content-type": "text/plain"})

    assert response.status_code == 200
    assert response.json() == {"imported": 1}
    assert repository.price_history("sony-a1")[0].final_price == Decimal("9500")


def test_manual_import_reports_invalid_csv_as_validation_error(tmp_path) -> None:
    response = TestClient(create_app(SqliteRepository(tmp_path / "tracker.db"))).post(
        "/api/import/csv", content="product_id,price\nsony-a1,not-a-number\n", headers={"content-type": "text/plain"},
    )

    assert response.status_code == 422
    assert "required columns" in response.json()["detail"]


def test_api_updates_validated_target_prices_in_local_config(tmp_path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree("config", config_dir)
    app = create_app(SqliteRepository(tmp_path / "tracker.db"), config_dir=config_dir)
    client = TestClient(app)

    response = client.put("/api/settings/targets", json=[{"product_id": "canon-r5m2", "target_price_cny": "29888"}])

    assert response.status_code == 200
    assert response.json()["targets"][0]["target_price_cny"] == "29888"
    assert "29888" in (config_dir / "alerts.yaml").read_text(encoding="utf-8")


def test_browser_quote_records_only_explicit_account_visible_price(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    client = TestClient(create_app(repository=repository))
    response = client.post("/api/browser-quotes", json={
        "product_id": "canon-r5m2", "url": "https://item.jd.com/1001.html", "status": "available",
        "list_price": "30999", "final_price": "28499", "promotion_text": "满减", "delivery_region": "上海",
    })
    assert response.json() == {"recorded": True, "status": "available"}
    assert repository.price_history("canon-r5m2")[0].final_price == Decimal("28499")


def test_browser_quote_paused_does_not_write_price(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    response = TestClient(create_app(repository=repository)).post("/api/browser-quotes", json={
        "product_id": "canon-r5m2", "url": "https://item.jd.com/1001.html", "status": "paused", "reason": "当前页面异常",
    })
    assert response.json() == {"recorded": False, "status": "paused"}
    assert repository.price_history("canon-r5m2") == []


def test_api_updates_source_frequency_with_safe_bounds(tmp_path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree("config", config_dir)
    client = TestClient(create_app(SqliteRepository(tmp_path / "tracker.db"), config_dir=config_dir))

    response = client.put("/api/settings/sources", json={"sony_cn": {"enabled": False, "interval_minutes": 75}})

    assert response.status_code == 200
    assert response.json()["restart_required"] is True
    assert response.json()["sources"]["sony_cn"]["interval_minutes"] == 75
    assert "interval_minutes: 75" in (config_dir / "sources.yaml").read_text(encoding="utf-8")


def test_used_market_endpoint_filters_a1_by_price_and_shutter_count(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    timestamp = datetime(2026, 7, 23, tzinfo=timezone.utc)
    for shop, price, shutter in [("合格卖家", "9500", 4000), ("高快门卖家", "9000", 40000)]:
        repository.record_quote(
            normalize_quote(
                product_id="sony-a1", platform="goofish", shop_name=shop, url=f"https://example.test/{shop}",
                list_price=Decimal(price), condition="used", warranty_type="none", shutter_count=shutter,
                cosmetic_grade="excellent", packaging_status="complete",
            ), captured_at=timestamp, raw_payload={}, trust_score=70,
        )

    response = TestClient(create_app(repository=repository)).get("/api/used/sony-a1?max_price_cny=10000&max_shutter_count=10000")

    assert response.status_code == 200
    assert response.json()["summary"]["count"] == 1
    assert response.json()["quotes"][0]["shop_name"] == "合格卖家"


def test_api_adds_a_configured_product_without_alias_conflicts(tmp_path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree("config", config_dir)
    client = TestClient(create_app(SqliteRepository(tmp_path / "tracker.db"), config_dir=config_dir))

    response = client.put("/api/settings/products/sigma-50-150", json={
        "id": "sigma-50-150", "name": "Sigma 50-150mm F2", "type": "lens",
        "aliases": ["Sigma 50-150 F2", "50-150 F2"],
    })

    assert response.status_code == 200
    assert response.json()["product"]["type"] == "lens"
    assert "sigma-50-150" in (config_dir / "lenses.yaml").read_text(encoding="utf-8")


def test_api_adds_explicit_public_watch_for_configured_product(tmp_path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree("config", config_dir)
    client = TestClient(create_app(SqliteRepository(tmp_path / "tracker.db"), config_dir=config_dir))

    response = client.put("/api/settings/watches", json={
        "product_id": "sony-a7v", "platform": "sony_cn", "shop_name": "Sony 中国官方商城",
        "url": "https://public.example.test/products/a7v", "adapter": "jsonld",
    })

    assert response.status_code == 200
    assert response.json()["watch"]["adapter"] == "jsonld"
    assert "public.example.test" in (config_dir / "watches.yaml").read_text(encoding="utf-8")


def test_api_stores_auditable_product_promotion_event(tmp_path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree("config", config_dir)
    client = TestClient(create_app(SqliteRepository(tmp_path / "tracker.db"), config_dir=config_dir))

    response = client.put("/api/settings/events/r5m2-618-2026", json={
        "product_id": "canon-r5m2", "type": "promotion", "title": "618 促销", "date": "2026-06-18",
        "url": "https://example.test/r5m2-promo",
    })

    assert response.status_code == 200
    assert response.json()["event"]["type"] == "promotion"
    assert TestClient(create_app(SqliteRepository(tmp_path / "tracker2.db"), config_dir=config_dir)).get("/api/products/canon-r5m2/events").json()[0]["id"] == "r5m2-618-2026"


def test_api_persists_user_purchase_region_preference(tmp_path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree("config", config_dir)
    client = TestClient(create_app(SqliteRepository(tmp_path / "tracker.db"), config_dir=config_dir))

    response = client.put("/api/settings/preferences", json={"user_purchase_region": "hk"})

    assert response.status_code == 200
    assert response.json()["preferences"]["user_purchase_region"] == "hk"
    assert "user_purchase_region: hk" in (config_dir / "settings.yaml").read_text(encoding="utf-8")
