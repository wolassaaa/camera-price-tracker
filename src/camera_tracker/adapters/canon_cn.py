"""Canon China official-store embedded product state adapter."""

import re
from decimal import Decimal

from camera_tracker.adapters.jsonld import PublicProductQuote


def parse_canon_cn_product(html: str, *, product_id: str, url: str) -> PublicProductQuote:
    price_match = re.search(r'"(?:rawprice|price)"\s*:\s*"?([0-9.]+)', html)
    if price_match is None:
        raise ValueError("Canon China product price not found")
    quantity_match = re.search(r'"quantity"\s*:\s*"?([0-9.]+)', html)
    quantity = Decimal(quantity_match.group(1)) if quantity_match else Decimal("0")
    return PublicProductQuote(
        product_id=product_id, platform="canon_cn", shop_name="佳能官方线上商城", url=url,
        final_price=Decimal(price_match.group(1)), currency="CNY",
        stock_status="in_stock" if quantity > 0 else "out_of_stock",
        condition="new", market_variant="cn", warranty_type="manufacturer", bundle_type="body_only",
    )
