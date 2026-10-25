from decimal import Decimal

import pytest

from camera_tracker.adapters.jd import extract_jd_sku, parse_jd_price_payload
from camera_tracker.collector import collect_jd_watch


def test_extract_jd_sku_from_public_product_url() -> None:
    assert extract_jd_sku("https://item.jd.com/100123456789.html") == "100123456789"


def test_parse_jd_public_price_response() -> None:
    quote = parse_jd_price_payload(
        '[{"id":"J_100123456789","p":"12999.00","m":"13999.00"}]',
        product_id="canon-r5m2",
        shop_name="京东自营",
        url="https://item.jd.com/100123456789.html",
    )

    assert quote.final_price == Decimal("12999.00")
    assert quote.platform == "jd"
    assert quote.currency == "CNY"


def test_jd_public_price_rejects_unavailable_product() -> None:
    with pytest.raises(ValueError, match="JD public price"):
        parse_jd_price_payload(
            '[{"id":"J_100123456789","p":"-1"}]',
            product_id="canon-r5m2",
            shop_name="京东自营",
            url="https://item.jd.com/100123456789.html",
        )


def test_collect_jd_watch_uses_public_sku_price_endpoint() -> None:
    watch = {
        "product_id": "canon-r5m2",
        "platform": "jd",
        "shop_name": "京东自营",
        "url": "https://item.jd.com/100123456789.html",
        "adapter": "jd",
    }

    quotes = collect_jd_watch(
        watch,
        fetch=lambda url: '[{"id":"J_100123456789","p":"12999.00"}]'
        if "p.3.cn/prices/mgets" in url else (_ for _ in ()).throw(AssertionError(url)),
    )

    assert len(quotes) == 1
    assert quotes[0].final_price == Decimal("12999.00")
    assert quotes[0].platform == "jd"
