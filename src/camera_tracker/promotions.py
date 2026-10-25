"""Known China retail promotion windows used as transparent forecast features."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class PromotionWindow:
    name: str
    starts_on: date
    ends_on: date

    def contains(self, value: date) -> bool:
        return self.starts_on <= value <= self.ends_on


# Lunar New Year is intentionally an explicit, reviewable mapping rather than a guessed conversion.
_SPRING_FESTIVAL = {2025: date(2025, 1, 29), 2026: date(2026, 2, 17), 2027: date(2027, 2, 6)}


def promotion_windows(year: int) -> tuple[PromotionWindow, ...]:
    fixed = (
        ("618", date(year, 6, 15), date(year, 6, 20)),
        ("双11", date(year, 11, 8), date(year, 11, 12)),
        ("双12", date(year, 12, 10), date(year, 12, 13)),
    )
    windows = [PromotionWindow(name, start, end) for name, start, end in fixed]
    spring = _SPRING_FESTIVAL.get(year)
    if spring is not None:
        windows.append(PromotionWindow("春节", spring - timedelta(days=10), spring + timedelta(days=3)))
    return tuple(windows)


def promotions_between(start: date, end: date) -> tuple[PromotionWindow, ...]:
    return tuple(
        window for year in range(start.year, end.year + 1)
        for window in promotion_windows(year)
        if window.ends_on >= start and window.starts_on <= end
    )


def promotion_names_for(value: date) -> tuple[str, ...]:
    return tuple(window.name for window in promotion_windows(value.year) if window.contains(value))
