from datetime import datetime, timedelta, timezone
from decimal import Decimal

from camera_tracker.forecasting import backtest, forecast, forecast_horizons, select_baseline
from camera_tracker.repository import PricePoint


def test_forecast_refuses_to_claim_reliability_for_less_than_30_days() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    history = [PricePoint(start + timedelta(days=index), Decimal("10000")) for index in range(10)]

    result = forecast(history)

    assert result.available is False
    assert "数据不足" in result.reason


def test_backtest_reports_error_for_rolling_median_baseline() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = [PricePoint(start + timedelta(days=index), Decimal(10000 - index * 10)) for index in range(40)]

    result = backtest(history, window=7)

    assert result.sample_count == 33
    assert result.mean_absolute_error >= Decimal("0")


def test_horizon_forecast_returns_intervals_and_downward_trend_for_falling_prices() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = [PricePoint(start + timedelta(days=index), Decimal(12000 - index * 10)) for index in range(40)]

    results = forecast_horizons(history)

    assert set(results) == {7, 30, 90}
    assert results[30].available is True
    assert results[30].trend == "down"
    assert results[30].lower_bound <= results[30].median_price <= results[30].upper_bound


def test_horizon_forecast_discloses_upcoming_618_without_inventing_discount_history() -> None:
    start = datetime(2026, 5, 14, tzinfo=timezone.utc)
    history = [PricePoint(start + timedelta(days=index), Decimal("10000")) for index in range(30)]

    result = forecast_horizons(history)[7]

    assert result.promotion_events == ("618",)
    assert result.promotion_sample_count == 0
    assert "历史促销样本不足" in result.reason


def test_rolling_validation_selects_a_named_baseline_and_reports_its_mae() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = [PricePoint(start + timedelta(days=index), Decimal(10000 + index * 20)) for index in range(40)]

    model_name, level, validation = select_baseline(history)

    assert model_name in {"moving_median", "ewma"}
    assert level > 0
    assert validation.model_name == model_name
    assert validation.sample_count > 0
