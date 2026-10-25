from fastapi.testclient import TestClient

from camera_tracker.api import create_app
from camera_tracker.repository import SqliteRepository
from camera_tracker.source_status import SourceStatusRegistry


def test_sources_endpoint_exposes_manual_attention_state_with_persistent_history(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    repository.record_source_success("canon_cn")
    statuses = SourceStatusRegistry()
    for _ in range(3):
        statuses.record_failure("tmall", "login required")

    response = TestClient(create_app(repository, statuses=statuses)).get("/api/sources")

    assert response.status_code == 200
    assert response.json()[0]["source_id"] == "tmall"
    assert response.json()[0]["manual_attention_required"] is True


def test_sources_endpoint_distinguishes_jd_public_prices_from_restricted_sources(tmp_path) -> None:
    response = TestClient(create_app()).get("/api/sources")
    sources = {row["source_id"]: row for row in response.json()}

    assert sources["jd"]["manual_attention_required"] is False
    assert sources["tmall"]["manual_attention_required"] is True
    assert "手动导入" in sources["tmall"]["last_error"]
