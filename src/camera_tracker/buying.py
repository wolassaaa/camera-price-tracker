"""Explainable purchase-timing recommendation."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PurchaseRecommendation:
    score: int
    label: str
    reason: str


def recommend(
    *, current_price: Decimal, trusted_historical_low: Decimal,
    historical_percentile: int, forecast_drop_probability: float,
    reliable_channel: bool, stock_status: str = "unknown", warranty_type: str = "unknown",
    complex_offer: bool = False, release_risk: bool = False, clearance_signal: bool = False,
    regional_savings: Decimal = Decimal("0"), preferred_region: str = "cn",
    price_anomaly: bool = False,
) -> PurchaseRecommendation:
    if price_anomaly:
        return PurchaseRecommendation(0, "价格异常，人工确认", "报价偏离可信市场范围，需第二来源或人工确认")
    distance = (current_price - trusted_historical_low) / trusted_historical_low
    score = 50
    reasons: list[str] = []
    if distance <= Decimal("0.03"):
        score += 25
        reasons.append("当前价格接近可信历史低位")
    if historical_percentile <= 20:
        score += 15
        reasons.append("价格处于历史低分位")
    if forecast_drop_probability >= 0.5:
        score -= 20
        reasons.append("预测仍有明显降价空间")
    if reliable_channel:
        score += 10
        reasons.append("渠道与保修条件可信")
    if stock_status == "in_stock":
        score += 5
        reasons.append("当前有库存")
    elif stock_status == "out_of_stock":
        score -= 15
        reasons.append("当前缺货")
    if warranty_type == "manufacturer":
        score += 5
        reasons.append("原厂保修")
    elif warranty_type == "none":
        score -= 5
        reasons.append("保修条件较弱或未知")
    if complex_offer:
        score -= 10
        reasons.append("价格依赖现金、会员或复杂优惠条件")
    if regional_savings >= Decimal("500"):
        score += 5
        reasons.append(f"相对偏好地区可节省 ¥{regional_savings}")
    if release_risk:
        score -= 25
        reasons.append("存在新品发布或预售信号")
    if clearance_signal:
        score -= 10
        reasons.append("存在清仓信号，价格可能继续调整")
    score = max(0, min(score, 100))
    if release_risk:
        label = "等待新品发布"
    elif forecast_drop_probability >= 0.6:
        label = "等待大型促销"
    elif score >= 85 and stock_status == "in_stock" and warranty_type == "manufacturer":
        label = "立即购买"
    elif score >= 70:
        label = "可以购买"
    else:
        label = "建议观望"
    if not reasons:
        reasons.append(f"按{preferred_region}地区偏好，历史与渠道信息有限")
    return PurchaseRecommendation(score=score, label=label, reason="；".join(reasons))
