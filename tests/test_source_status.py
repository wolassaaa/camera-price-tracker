from camera_tracker.source_status import SourceStatusRegistry


def test_repeated_failure_marks_source_for_manual_attention() -> None:
    status = SourceStatusRegistry()
    status.record_failure("tmall", "login required")
    status.record_failure("tmall", "login required")
    status.record_failure("tmall", "login required")

    source = status.get("tmall")
    assert source.manual_attention_required is True
    assert source.consecutive_failures == 3
