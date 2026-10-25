from decimal import Decimal
from pathlib import Path

from camera_tracker.adapters.canon_hk import parse_canon_hk_product


def test_canon_hk_adapter_reads_public_official_hkd_price() -> None:
    quote = parse_canon_hk_product(
        Path("tests/fixtures/canon_hk_product.html").read_text(encoding="utf-8"),
        product_id="canon-r5m2", url="https://hk.canon/en/example",
    )

    assert quote.final_price == Decimal("30580.00")
    assert quote.currency == "HKD"
    assert quote.market_variant == "hk_authorized"
