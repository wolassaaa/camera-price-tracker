"""Reliability scoring and outlier protection."""

from dataclasses import dataclass
from decimal import Decimal

from camera_tracker.normalization import NormalizedQuote


@dataclass(frozen=True)
class ReliabilityAssessment:
    score: int
    manual_confirmation_required: bool
    eligible_for_historical_low: bool


def assess_quote(
    quote: NormalizedQuote, *, market_median: Decimal, official_or_authorized: bool
) -> ReliabilityAssessment:
    deviation = quote.final_price / market_median if market_median else Decimal("1")
    suspicious = (
        deviation < Decimal("0.60") or quote.condition != "new"
        or quote.stock_status == "out_of_stock" or quote.bundle_type not in {"body_only", "lens_only"}
    )
    score = 90 if official_or_authorized else 65
    if quote.warranty_type == "manufacturer":
        score += 5
    if quote.stock_status != "in_stock":
        score -= 10
    if suspicious:
        score -= 35
    return ReliabilityAssessment(
        score=score,
        manual_confirmation_required=suspicious,
        eligible_for_historical_low=not suspicious and score >= 70,
    )
