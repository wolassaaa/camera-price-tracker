"""Canon Hong Kong Shopify-store product adapter."""

import re
from decimal import Decimal

from camera_tracker.adapters.jsonld import PublicProductQuote


def parse_canon_hk_store_product(html: str, *, product_id: str, url: str) -> PublicProductQuote:
    match = re.search(r'"price"\s*:\s*(\d+)', html)
    if match is None:
        raise ValueError("Canon Hong Kong store Shopify price not found")
    return PublicProductQuote(
        product_id=product_id, platform="canon_hk_store", shop_name="Canon Hong Kong Online Store", url=url,
        final_price=Decimal(match.group(1)) / Decimal("100"), currency="HKD", stock_status="unknown",
        condition="new", market_variant="hk_authorized", warranty_type="manufacturer", bundle_type="body_only",
    )
