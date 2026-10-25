from decimal import Decimal

from camera_tracker.collector import run_watch
from camera_tracker.repository import SqliteRepository
from camera_tracker.source_status import SourceStatusRegistry


def test_runner_emits_target_price_alert_after_persisting_quote(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    received: list[dict[str, str]] = []

    run_watch(
        {"product_id": "canon-r5m2", "platform": "canon_cn", "shop_name": "Canon", "url": "https://example.test", "adapter": "canon_cn"},
        repository=repository, status=SourceStatusRegistry(),
        fetch=lambda _: '<script>{"rawprice":29999,"quantity":"4"}</script>',
        target_prices={"canon-r5m2": Decimal("30000")}, notifier=received.append,
    )

    assert received[0]["event"] == "target_price_reached"
    assert received[0]["current_price"] == "29999"
