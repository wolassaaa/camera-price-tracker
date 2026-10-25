from decimal import Decimal

import camera_tracker.normalization as normalization


def test_normalizes_hong_kong_quote_without_treating_gift_as_cash_discount() -> None:
    quote = normalization.normalize_quote(
        product_id="sony-a7v",
        platform="price_com_hk",
        shop_name="Example Camera",
        url="https://example.test/item",
        list_price=Decimal("18999"),
        coupon_discount=Decimal("500"),
        shipping=Decimal("80"),
        currency="HKD",
        exchange_rate_to_cny=Decimal("0.92"),
        condition="new",
        market_variant="hk_grey",
        warranty_type="shop",
        bundle_type="body_only",
        gift_value=Decimal("300"),
    )

    assert quote.final_price == Decimal("18579")
    assert quote.reference_cny == Decimal("17092.68")
    assert quote.gift_value == Decimal("300")


def test_keeps_payment_terms_and_used_metadata_separate_from_final_price() -> None:
    quote = normalization.normalize_quote(
        product_id="sony-a1", platform="goofish", shop_name="Seller", url="https://example.test/a1",
        list_price=Decimal("10000"), member_price=Decimal("9000"), coupon_discount=Decimal("500"),
        payment_discount=Decimal("100"), full_reduction=Decimal("200"), shipping=Decimal("50"), tax=Decimal("20"),
        condition="used", bundle_type="body_only", shutter_count=12345, cosmetic_grade="95new",
        packaging_status="box_and_accessories", warranty_remaining_days=100,
    )

    assert quote.final_price == Decimal("8270")
    assert quote.member_price == Decimal("9000")
    assert quote.shutter_count == 12345
    assert quote.gift_value == Decimal("0")
