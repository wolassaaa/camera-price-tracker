from decimal import Decimal
from pathlib import Path

from camera_tracker.adapters.price_com_hk import parse_price_com_html


def test_price_com_parser_keeps_grey_cash_and_shop_warranty_fields() -> None:
    quotes = parse_price_com_html(Path("tests/fixtures/price_com_hk.html").read_text(encoding="utf-8"), product_id="sony-a7v", url="https://price.test")

    assert quotes[0].final_price == Decimal("18800")
    assert quotes[0].market_variant == "hk_grey"
    assert quotes[0].warranty_type == "shop"
    assert quotes[0].is_cash_price is True


def test_price_com_parser_supports_live_quote_markup() -> None:
    html = '''<p class="quotation-merchant-name">Live Camera</p>
    <div class="price-refer-btn"><span class="product-price"><span class="text-price-number" data-price="41198.0">41,198</span></span><img title="行貨"></div>
    <div class="quote-price-water"><span class="product-price"><span class="text-price-number" data-price="38450.0">38,450</span></span><img title="水貨"></div>
    <p class="quotation-merchant-name">Next</p>'''

    quotes = parse_price_com_html(html, product_id="sony-a1m2", url="https://price.test")

    assert {quote.market_variant for quote in quotes} == {"hk_authorized", "hk_grey"}
    assert min(quote.final_price for quote in quotes) == Decimal("38450.0")
