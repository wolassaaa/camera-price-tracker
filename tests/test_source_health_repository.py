from camera_tracker.repository import SqliteRepository


def test_source_health_survives_worker_process_restart(tmp_path) -> None:
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    repository.record_source_failure("price_com_hk", "timeout")
    repository.record_source_failure("price_com_hk", "timeout")
    repository.record_source_success("price_com_hk")

    row = repository.source_health()[0]
    assert row["source_id"] == "price_com_hk"
    assert row["consecutive_failures"] == 0
    assert row["last_success_at"] is not None
