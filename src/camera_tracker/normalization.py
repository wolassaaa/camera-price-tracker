"""Convert source-specific price fields into comparable quotes."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class NormalizedQuote:
    product_id: str
    platform: str
    shop_name: str
    url: str
    list_price: Decimal
    member_price: Decimal | None
    coupon_discount: Decimal
    payment_discount: Decimal
    full_reduction: Decimal
    shipping: Decimal
    tax: Decimal
    final_price: Decimal
    currency: str
    reference_cny: Decimal | None
    condition: str
    market_variant: str
    warranty_type: str
    bundle_type: str
    gift_value: Decimal
    stock_status: str
    shutter_count: int | None
    cosmetic_grade: str | None
    packaging_status: str | None
    warranty_remaining_days: int | None
    cash_price_only: bool


def normalize_quote(
    *, product_id: str, platform: str, shop_name: str, url: str,
    list_price: Decimal, member_price: Decimal | None = None, coupon_discount: Decimal = Decimal("0"),
    payment_discount: Decimal = Decimal("0"), full_reduction: Decimal = Decimal("0"),
    shipping: Decimal = Decimal("0"), currency: str = "CNY",
    tax: Decimal = Decimal("0"),
    exchange_rate_to_cny: Decimal | None = None, condition: str = "new",
    market_variant: str = "cn", warranty_type: str = "unknown",
    bundle_type: str = "body_only", gift_value: Decimal = Decimal("0"),
    stock_status: str = "unknown", shutter_count: int | None = None,
    cosmetic_grade: str | None = None, packaging_status: str | None = None,
    warranty_remaining_days: int | None = None, cash_price_only: bool = False,
) -> NormalizedQuote:
    price_base = member_price if member_price is not None else list_price
    final_price = price_base - coupon_discount - payment_discount - full_reduction + shipping + tax
    reference_cny = final_price if currency == "CNY" else None
    if currency != "CNY" and exchange_rate_to_cny is not None:
        reference_cny = final_price * exchange_rate_to_cny
    return NormalizedQuote(
        product_id=product_id, platform=platform, shop_name=shop_name, url=url,
        list_price=list_price, member_price=member_price, coupon_discount=coupon_discount,
        payment_discount=payment_discount, full_reduction=full_reduction, shipping=shipping, tax=tax,
        final_price=final_price, currency=currency, reference_cny=reference_cny,
        condition=condition, market_variant=market_variant,
        warranty_type=warranty_type, bundle_type=bundle_type, gift_value=gift_value, stock_status=stock_status,
        shutter_count=shutter_count, cosmetic_grade=cosmetic_grade, packaging_status=packaging_status,
        warranty_remaining_days=warranty_remaining_days, cash_price_only=cash_price_only,
    )
