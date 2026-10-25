import camera_tracker.worker as worker
from camera_tracker.worker import job_specs, run_once


def test_worker_uses_source_intervals_for_enabled_watches() -> None:
    specs = job_specs(
        watches=[{"product_id": "sony-a7v", "platform": "sony_cn", "shop_name": "Sony", "url": "https://example.test"}],
        sources={"sony_cn": {"enabled": True, "interval_minutes": 60, "jitter_seconds": 120}},
    )

    assert specs[0].source_id == "sony_cn"
    assert specs[0].interval_minutes == 60


def test_run_once_executes_each_enabled_watch_immediately(tmp_path) -> None:
    calls: list[str] = []

    count = run_once(
        watches=[{"product_id": "sony-a7v", "platform": "sony_cn", "shop_name": "Sony", "url": "https://example.test"}],
        sources={"sony_cn": {"enabled": True, "interval_minutes": 60, "jitter_seconds": 0}},
        database_path=tmp_path / "tracker.db",
        runner=lambda watch, **_: calls.append(watch["product_id"]) or 1,
    )

    assert count == 1
    assert calls == ["sony-a7v"]


def test_run_once_keeps_collecting_when_one_source_fails(tmp_path) -> None:
    calls: list[str] = []

    def runner(watch, **_):
        calls.append(watch["product_id"])
        if watch["product_id"] == "first":
            raise RuntimeError("rate limited")
        return 2

    count = run_once(
        watches=[
            {"product_id": "first", "platform": "first_source", "shop_name": "First", "url": "https://example.test"},
            {"product_id": "second", "platform": "second_source", "shop_name": "Second", "url": "https://example.test"},
        ],
        sources={
            "first_source": {"enabled": True, "interval_minutes": 60},
            "second_source": {"enabled": True, "interval_minutes": 60},
        },
        database_path=tmp_path / "tracker.db",
        runner=runner,
    )

    assert count == 2
    assert calls == ["first", "second"]


def test_worker_once_cli_runs_enabled_watches_and_exits(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(worker, "run_once", lambda **_: 3)
    monkeypatch.setattr(worker, "load_watches", lambda _: [])
    monkeypatch.setattr(worker, "load_sources", lambda _: {})

    code = worker.main(["--once", "--config-dir", str(tmp_path), "--database", str(tmp_path / "tracker.db")])

    assert code == 0
    assert "quotes_written=3" in capsys.readouterr().out
