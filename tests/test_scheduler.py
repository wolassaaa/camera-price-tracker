from datetime import datetime, timedelta, timezone

from camera_tracker.scheduler import BackoffGate, next_delay_seconds


def test_failed_sources_back_off_without_exceeding_configured_ceiling() -> None:
    assert next_delay_seconds(interval_minutes=15, failure_count=0, jitter_seconds=0) == 900
    assert next_delay_seconds(interval_minutes=15, failure_count=3, jitter_seconds=0) == 7200
    assert next_delay_seconds(interval_minutes=15, failure_count=10, jitter_seconds=0) == 7200


def test_backoff_gate_skips_requests_until_the_failure_delay_expires() -> None:
    gate = BackoffGate()
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)

    next_allowed = gate.record_failure(source_id="canon_hk_store", interval_minutes=15, jitter_seconds=0, failure_count=2, now=now)

    assert gate.allows("canon_hk_store", now + timedelta(minutes=30)) is False
    assert gate.allows("canon_hk_store", next_allowed) is True
    gate.record_success("canon_hk_store")
    assert gate.allows("canon_hk_store", now) is True
