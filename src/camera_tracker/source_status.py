"""Health state for source adapters."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SourceStatus:
    consecutive_failures: int = 0
    manual_attention_required: bool = False
    last_error: str | None = None
    last_success_at: datetime | None = None


class SourceStatusRegistry:
    def __init__(self) -> None:
        self._states: dict[str, SourceStatus] = {}

    def record_failure(self, source_id: str, error: str) -> None:
        previous = self.get(source_id)
        failures = previous.consecutive_failures + 1
        self._states[source_id] = SourceStatus(
            consecutive_failures=failures,
            manual_attention_required=failures >= 3,
            last_error=error,
            last_success_at=previous.last_success_at,
        )

    def record_success(self, source_id: str) -> None:
        self._states[source_id] = SourceStatus(last_success_at=datetime.now(timezone.utc))

    def get(self, source_id: str) -> SourceStatus:
        return self._states.get(source_id, SourceStatus())

    def all(self) -> dict[str, SourceStatus]:
        return dict(self._states)
