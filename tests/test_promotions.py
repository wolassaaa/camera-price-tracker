from datetime import date

from camera_tracker.promotions import promotion_names_for, promotions_between


def test_promotion_calendar_exposes_known_retail_windows() -> None:
    assert promotion_names_for(date(2026, 6, 18)) == ("618",)
    assert promotion_names_for(date(2026, 11, 11)) == ("双11",)
    assert [window.name for window in promotions_between(date(2026, 11, 1), date(2026, 11, 15))] == ["双11"]
