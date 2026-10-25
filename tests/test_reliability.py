from decimal import Decimal

from camera_tracker.reliability import assess_quote
from camera_tracker.normalization import normalize_quote


def test_flags_an_unrealistic_low_price_for_manual_confirmation() -> None:
    quote = normalize_quote(
        product_id="sony-a7v", platform="marketplace", shop_name="Unknown",
        url="https://example.test", list_price=Decimal("4000"), condition="new",
    )

    result = assess_quote(quote, market_median=Decimal("15000"), official_or_authorized=False)

    assert result.manual_confirmation_required is True
    assert result.eligible_for_historical_low is False
