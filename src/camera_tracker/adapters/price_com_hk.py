"""Price.com.hk adapter with explicit merchant attributes."""

import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PriceComQuote:
    product_id: str
    shop_name: str
    final_price: Decimal
    market_variant: str
    warranty_type: str
    is_cash_price: bool
    stock_status: str
    url: str


def _text(fragment: str, class_name: str) -> str:
    match = re.search(rf'<[^>]*class=["\']{class_name}["\'][^>]*>(.*?)</[^>]+>', fragment, re.S)
    return re.sub(r"<[^>]+>", "", match.group(1)).strip() if match else ""


def parse_price_com_html(html: str, *, product_id: str, url: str) -> list[PriceComQuote]:
    live_quotes = _parse_live_quote_markup(html, product_id=product_id, url=url)
    if live_quotes:
        return live_quotes
    blocks = re.findall(r'<div class=["\']merchant["\']>(.*?)</div>', html, re.S)
    quotes: list[PriceComQuote] = []
    for block in blocks:
        tags = _text(block, "tags")
        amount = re.sub(r"[^0-9.]", "", _text(block, "price"))
        if not amount:
            continue
        quotes.append(PriceComQuote(
            product_id=product_id, shop_name=_text(block, "merchant-name"), final_price=Decimal(amount),
            market_variant="hk_grey" if "水貨" in tags else "hk_authorized",
            warranty_type="manufacturer" if "原廠保養" in tags else "shop",
            is_cash_price="現金價" in tags, stock_status="in_stock" if "有現貨" in tags else "unknown", url=url,
        ))
    return quotes


def _parse_live_quote_markup(html: str, *, product_id: str, url: str) -> list[PriceComQuote]:
    markers = list(re.finditer(r'<p[^>]*class=["\']quotation-merchant-name["\'][^>]*>(.*?)</p>', html, re.S))
    quotes: list[PriceComQuote] = []
    for index, marker in enumerate(markers):
        next_start = markers[index + 1].start() if index + 1 < len(markers) else len(html)
        block = html[marker.end():next_start]
        shop_name = re.sub(r"<[^>]+>", "", marker.group(1)).strip()
        for price_block in re.finditer(r'<div[^>]*class=["\']([^"\']*(?:price-refer-btn|quote-price-water)[^"\']*)["\'][^>]*>(.*?)</div>', block, re.S):
            class_name, content = price_block.groups()
            price = re.search(r'data-price=["\']([0-9.]+)["\']', content)
            if not price:
                continue
            is_grey = "quote-price-water" in class_name or "水貨" in content
            quotes.append(PriceComQuote(
                product_id=product_id, shop_name=shop_name, final_price=Decimal(price.group(1)),
                market_variant="hk_grey" if is_grey else "hk_authorized",
                warranty_type="manufacturer" if "原廠保養" in content else "shop",
                is_cash_price="現金" in content, stock_status="in_stock" if "現貨" in content else "unknown", url=url,
            ))
    return quotes
