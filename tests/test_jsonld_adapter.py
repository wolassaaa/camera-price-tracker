from decimal import Decimal
from pathlib import Path

from camera_tracker.adapters.jsonld import parse_product_jsonld


def test_jsonld_adapter_parses_public_official_product_price() -> None:
    quotes = parse_product_jsonld(
        Path("tests/fixtures/official_product.jsonld.html").read_text(encoding="utf-8"),
        product_id="sony-a7v", platform="sony_cn", shop_name="Sony 中国官方商城", url="https://example.test/a7v",
    )

    assert quotes[0].final_price == Decimal("19999")
    assert quotes[0].stock_status == "in_stock"
    assert quotes[0].currency == "CNY"
