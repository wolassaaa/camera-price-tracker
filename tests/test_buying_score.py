from decimal import Decimal

from camera_tracker.buying import recommend


def test_recommendation_explains_when_current_price_is_near_trusted_low() -> None:
    result = recommend(
        current_price=Decimal("10100"), trusted_historical_low=Decimal("10000"),
        historical_percentile=12, forecast_drop_probability=0.15, reliable_channel=True,
    )

    assert result.label == "可以购买"
    assert result.score >= 70
    assert "历史低位" in result.reason


def test_score_waits_for_release_when_event_risk_outweighs_low_price() -> None:
    result = recommend(
        current_price=Decimal("10000"), trusted_historical_low=Decimal("10000"), historical_percentile=5,
        forecast_drop_probability=0.2, reliable_channel=True, stock_status="in_stock",
        warranty_type="manufacturer", release_risk=True,
    )

    assert result.label == "等待新品发布"
    assert "新品发布" in result.reason


def test_score_marks_anomaly_for_manual_confirmation() -> None:
    result = recommend(
        current_price=Decimal("1000"), trusted_historical_low=Decimal("9000"), historical_percentile=1,
        forecast_drop_probability=0.1, reliable_channel=False, price_anomaly=True,
    )

    assert result.label == "价格异常，人工确认"
