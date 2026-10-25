"""Polite, configurable source scheduling."""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def next_delay_seconds(*, interval_minutes: int, failure_count: int, jitter_seconds: int) -> int:
    """Exponential backoff capped at eight times the base interval."""
    base = interval_minutes * 60
    backed_off = min(base * (2 ** failure_count), base * 8)
    return backed_off + random.randint(0, jitter_seconds)


@dataclass
class BackoffGate:
    """Avoid actual requests until an exponential-backoff delay has elapsed."""
    next_allowed_at: dict[str, datetime] = field(default_factory=dict)

    def allows(self, source_id: str, now: datetime) -> bool:
        return now >= self.next_allowed_at.get(source_id, now)

    def record_success(self, source_id: str) -> None:
        self.next_allowed_at.pop(source_id, None)

    def record_failure(self, *, source_id: str, interval_minutes: int, jitter_seconds: int, failure_count: int, now: datetime) -> datetime:
        delay = next_delay_seconds(
            interval_minutes=interval_minutes, failure_count=failure_count, jitter_seconds=jitter_seconds,
        )
        next_allowed = now + timedelta(seconds=delay)
        self.next_allowed_at[source_id] = next_allowed
        return next_allowed
