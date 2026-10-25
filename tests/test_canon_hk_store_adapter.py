from decimal import Decimal
from pathlib import Path

from camera_tracker.adapters.canon_hk_store import parse_canon_hk_store_product


def test_canon_hk_store_adapter_converts_shopify_cents_to_hkd() -> None:
    quote = parse_canon_hk_store_product(
        Path("tests/fixtures/canon_hk_store_product.html").read_text(encoding="utf-8"),
        product_id="canon-r5m2", url="https://store.hk.canon/en/products/eos-r5-mark-ii",
    )

    assert quote.final_price == Decimal("28180")
    assert quote.bundle_type == "body_only"
