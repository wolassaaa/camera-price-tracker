"""Sony Hong Kong official public product-price adapter."""

import re
from decimal import Decimal

from camera_tracker.adapters.jsonld import PublicProductQuote


def parse_sony_hk_product(html: str, *, product_id: str, url: str) -> PublicProductQuote:
    price = re.search(r'itemprop=["\']price["\'][^>]*content=["\']([0-9.]+)', html)
    if price is None:
        raise ValueError("Sony Hong Kong official price not found")
    return PublicProductQuote(
        product_id=product_id, platform="sony_hk", shop_name="Sony Hong Kong", url=url,
        final_price=Decimal(price.group(1)), currency="HKD", stock_status="unknown",
        condition="new", market_variant="hk_authorized", warranty_type="manufacturer", bundle_type="body_only",
    )
