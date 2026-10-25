"""Conservative, explainable price forecasting."""

from dataclasses import dataclass
from decimal import Decimal
from datetime import timedelta

from camera_tracker.repository import PricePoint
from camera_tracker.promotions import promotion_names_for, promotions_between


@dataclass(frozen=True)
class Forecast:
    available: bool
    reason: str
    sample_count: int
    days_covered: int
    median_price: Decimal | None = None


@dataclass(frozen=True)
class BacktestResult:
    sample_count: int
    mean_absolute_error: Decimal
    model_name: str = "moving_median"


@dataclass(frozen=True)
class HorizonForecast:
    horizon_days: int
    available: bool
    median_price: Decimal | None
    lower_bound: Decimal | None
    upper_bound: Decimal | None
    trend: str
    confidence: str
    sample_count: int
    days_covered: int
    reason: str
    better_buy_window_probability: float | None = None
    near_historical_low: bool = False
    promotion_events: tuple[str, ...] = ()
    promotion_sample_count: int = 0
    model_name: str = "moving_median"
    backtest_mae: Decimal | None = None


def forecast(history: list[PricePoint]) -> Forecast:
    if not history:
        return Forecast(False, "数据不足，无法提供可靠预测", 0, 0)
    days_covered = (history[-1].captured_at - history[0].captured_at).days + 1
    if days_covered < 30:
        return Forecast(False, "数据不足，无法提供可靠预测", len(history), days_covered)
    prices = sorted(point.final_price for point in history)
    return Forecast(True, "基于历史移动中位数", len(history), days_covered, prices[len(prices) // 2])


def _ewma(points: list[Decimal], alpha: Decimal = Decimal("0.3")) -> Decimal:
    value = points[0]
    for price in points[1:]:
        value = alpha * price + (Decimal("1") - alpha) * value
    return value


def backtest(history: list[PricePoint], *, window: int, model_name: str = "moving_median") -> BacktestResult:
    """Rolling one-step validation across transparent robust baseline models."""
    if len(history) <= window:
        return BacktestResult(0, Decimal("0"), model_name)
    errors: list[Decimal] = []
    for index in range(window, len(history)):
        train = [point.final_price for point in history[index - window:index]]
        if model_name == "moving_median":
            ordered = sorted(train)
            predicted = ordered[len(ordered) // 2]
        elif model_name == "ewma":
            predicted = _ewma(train)
        else:
            raise ValueError(f"Unknown forecast model: {model_name}")
        errors.append(abs(predicted - history[index].final_price))
    return BacktestResult(len(errors), sum(errors, Decimal("0")) / len(errors), model_name)


def select_baseline(history: list[PricePoint], *, window: int = 7) -> tuple[str, Decimal, BacktestResult]:
    """Select the lowest rolling-MAE transparent baseline; ties prefer the robust median."""
    results = [backtest(history, window=window, model_name=name) for name in ("moving_median", "ewma")]
    valid = [result for result in results if result.sample_count]
    selected = min(valid, key=lambda result: (result.mean_absolute_error, result.model_name != "moving_median")) if valid else results[0]
    recent = [point.final_price for point in history[-window:]]
    level = sorted(recent)[len(recent) // 2] if selected.model_name == "moving_median" else _ewma(recent)
    return selected.model_name, level, selected


def forecast_horizons(history: list[PricePoint]) -> dict[int, HorizonForecast]:
    """Explainable 7/30/90-day baseline forecasts from recent robust prices."""
    base = forecast(history)
    horizons = (7, 30, 90)
    if not base.available or base.median_price is None:
        return {
            horizon: HorizonForecast(horizon, False, None, None, None, "flat", "low",
                                     base.sample_count, base.days_covered, base.reason)
            for horizon in horizons
        }
    recent = [point.final_price for point in history[-7:]]
    earlier = [point.final_price for point in history[-14:-7]] or recent
    recent_median = sorted(recent)[len(recent) // 2]
    earlier_median = sorted(earlier)[len(earlier) // 2]
    trend = "down" if recent_median < earlier_median else "up" if recent_median > earlier_median else "flat"
    prices = sorted(point.final_price for point in history)
    q1, q3 = prices[len(prices) // 4], prices[(len(prices) * 3) // 4]
    model_name, baseline, validation = select_baseline(history)
    spread = max((q3 - q1) / Decimal("2"), baseline * Decimal("0.02"))
    confidence = "medium" if base.days_covered >= 90 else "low"
    historical_low = min(point.final_price for point in history)
    current = history[-1].final_price
    near_low = (current - historical_low) / historical_low <= Decimal("0.03")
    results: dict[int, HorizonForecast] = {}
    for horizon in horizons:
        future_events = promotions_between(
            history[-1].captured_at.date() + timedelta(days=1),
            history[-1].captured_at.date() + timedelta(days=horizon),
        )
        event_names = tuple(window.name for window in future_events)
        event_names_set = set(event_names)
        historical_promo_prices = [
            point.final_price for point in history if event_names_set.intersection(promotion_names_for(point.captured_at.date()))
        ]
        adjusted = baseline
        reason = f"基于{model_name}与历史四分位距（滚动 MAE {validation.mean_absolute_error:.2f}）"
        if event_names and len(historical_promo_prices) >= 3:
            promo_median = sorted(historical_promo_prices)[len(historical_promo_prices) // 2]
            if promo_median < baseline:
                adjusted -= (baseline - promo_median) / Decimal("2")
                reason += f"；参考历史{','.join(event_names)}促销窗口"
        elif event_names:
            reason += f"；未来含{','.join(event_names)}，但历史促销样本不足，未下调价格"
        probability = 0.25
        if trend == "down":
            probability += 0.20
        if event_names and len(historical_promo_prices) >= 3 and adjusted < base.median_price:
            probability += 0.20
        if near_low:
            probability -= 0.15
        results[horizon] = HorizonForecast(
            horizon, True, adjusted, adjusted - spread, adjusted + spread,
            trend, confidence, base.sample_count, base.days_covered, reason,
            better_buy_window_probability=max(0.05, min(0.85, probability)), near_historical_low=near_low,
            promotion_events=event_names, promotion_sample_count=len(historical_promo_prices),
            model_name=model_name, backtest_mae=validation.mean_absolute_error,
        )
    return results
