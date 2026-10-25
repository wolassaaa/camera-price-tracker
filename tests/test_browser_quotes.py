from datetime import datetime, timezone
from decimal import Decimal

import pytest

from camera_tracker.browser_quotes import BrowserQuoteResult, browser_quote_from_result
from camera_tracker.repository import SqliteRepository


def test_account_visible_result_records_final_price_and_evidence(tmp_path) -> None:
    result = BrowserQuoteResult(
        product_id="canon-r5m2", url="https://item.jd.com/1001.html", status="available",
        list_price=Decimal("30999"), final_price=Decimal("28499"),
        promotion_text="满10000减500，PLUS券减2000", delivery_region="上海",
    )
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    repository.record_quote(
        browser_quote_from_result(result), captured_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        raw_payload=result.evidence(), trust_score=90,
    )

    latest = repository.latest_channel_quotes("canon-r5m2", trusted_only=False)[0]
    assert latest["final_price"] == "28499"
    assert latest["coupon_discount"] == "2500"
    assert latest["quote_origin"] == "account_visible"
    assert latest["promotion_evidence"] == "满10000减500，PLUS券减2000"


def test_unavailable_result_cannot_be_converted_to_quote() -> None:
    result = BrowserQuoteResult(
        product_id="canon-r5m2", url="https://item.jd.com/1001.html", status="paused",
        reason="当前页面异常",
    )

    with pytest.raises(ValueError, match="available"):
        browser_quote_from_result(result)


def test_available_result_rejects_cookie_field() -> None:
    with pytest.raises(ValueError, match="Extra inputs"):
        BrowserQuoteResult.model_validate({
            "product_id": "canon-r5m2", "url": "https://item.jd.com/1001.html", "status": "available",
            "final_price": "28499", "cookie": "sensitive",
        })
