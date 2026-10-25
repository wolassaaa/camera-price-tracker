"""JD.com public SKU price adapter without login or cookie access."""

import json
import re
from decimal import Decimal, InvalidOperation

from camera_tracker.adapters.jsonld import PublicProductQuote


def extract_jd_sku(url: str) -> str:
    match = re.search(r"(?:item\.jd\.com/|item\.m\.jd\.com/product/)(\d+)(?:\.html)?", url)
    if match is None:
        raise ValueError("JD watch URL must contain a public SKU")
    return match.group(1)


def jd_price_api_url(sku: str) -> str:
    return f"https://p.3.cn/prices/mgets?skuIds=J_{sku}&type=1"


def parse_jd_price_payload(payload: str, *, product_id: str, shop_name: str, url: str) -> PublicProductQuote:
    try:
        rows = json.loads(payload)
        row = rows[0] if isinstance(rows, list) and rows else None
        price = Decimal(str(row.get("p"))) if isinstance(row, dict) else Decimal("-1")
    except (json.JSONDecodeError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("JD public price response is invalid") from exc
    if price <= 0:
        raise ValueError("JD public price is unavailable")
    return PublicProductQuote(
        product_id=product_id,
        platform="jd",
        shop_name=shop_name,
        url=url,
        final_price=price,
        currency="CNY",
        stock_status="unknown",
        market_variant="cn",
        warranty_type="merchant",
    )
