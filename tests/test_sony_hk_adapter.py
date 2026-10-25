from decimal import Decimal
from pathlib import Path

from camera_tracker.adapters.sony_hk import parse_sony_hk_product


def test_sony_hk_adapter_parses_official_itemprop_price() -> None:
    quote = parse_sony_hk_product(
        Path("tests/fixtures/sony_hk_product.html").read_text(encoding="utf-8"),
        product_id="sony-a1m2", url="https://www.sony.com.hk/example",
    )

    assert quote.final_price == Decimal("48990.00")
    assert quote.currency == "HKD"
    assert quote.warranty_type == "manufacturer"
