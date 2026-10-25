"""Public-page JSON-LD extractor shared by official and merchant adapters."""

import json
import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PublicProductQuote:
    product_id: str
    platform: str
    shop_name: str
    url: str
    final_price: Decimal
    currency: str
    stock_status: str
    condition: str = "new"
    market_variant: str = "cn"
    warranty_type: str = "manufacturer"
    bundle_type: str = "body_only"


def parse_product_jsonld(html: str, *, product_id: str, platform: str, shop_name: str, url: str) -> list[PublicProductQuote]:
    blocks = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I)
    quotes: list[PublicProductQuote] = []
    for block in blocks:
        payload = json.loads(block.strip())
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            offers = item.get("offers", {}) if isinstance(item, dict) else {}
            offers = offers if isinstance(offers, list) else [offers]
            for offer in offers:
                if not isinstance(offer, dict) or not offer.get("price"):
                    continue
                availability = str(offer.get("availability", ""))
                quotes.append(PublicProductQuote(
                    product_id=product_id, platform=platform, shop_name=shop_name, url=url,
                    final_price=Decimal(str(offer["price"])), currency=str(offer.get("priceCurrency", "CNY")),
                    stock_status="in_stock" if availability.endswith("InStock") else "unknown",
                ))
    return quotes
