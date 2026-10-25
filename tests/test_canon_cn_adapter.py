from decimal import Decimal
from pathlib import Path

from camera_tracker.adapters.canon_cn import parse_canon_cn_product


def test_canon_cn_adapter_reads_embedded_official_sku_price() -> None:
    quote = parse_canon_cn_product(
        Path("tests/fixtures/canon_cn_product.html").read_text(encoding="utf-8"),
        product_id="canon-r5m2", url="https://shop.canon.com.cn/prodetails?product_id=3416",
    )

    assert quote.final_price == Decimal("30599")
    assert quote.stock_status == "in_stock"
    assert quote.bundle_type == "body_only"
