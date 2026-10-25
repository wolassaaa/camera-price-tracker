"""Configurable price-alert rules and payload formatting."""

from decimal import Decimal


def _quote_context(
    *, event: str, product_name: str, current_price: Decimal, previous_price: Decimal,
    platform: str, shop_name: str, url: str, market_variant: str, warranty_type: str,
) -> dict[str, str]:
    return {
        "event": event, "product": product_name, "current_price": str(current_price),
        "previous_price": str(previous_price), "price_drop": str(previous_price - current_price),
        "platform": platform, "shop_name": shop_name, "url": url,
        "market_variant": market_variant, "warranty_type": warranty_type,
    }


def target_price_alert(
    *, product_name: str, current_price: Decimal, target_price: Decimal,
    previous_price: Decimal, platform: str, shop_name: str, url: str,
    market_variant: str, warranty_type: str,
) -> dict[str, str] | None:
    if current_price > target_price:
        return None
    return _quote_context(
        event="target_price_reached", product_name=product_name, current_price=current_price,
        previous_price=previous_price, platform=platform, shop_name=shop_name, url=url,
        market_variant=market_variant, warranty_type=warranty_type,
    )


def price_drop_alert(
    *, product_name: str, current_price: Decimal, previous_price: Decimal,
    platform: str, shop_name: str, url: str, market_variant: str, warranty_type: str,
    threshold: Decimal = Decimal("0.10"),
) -> dict[str, str] | None:
    """Alert only on a material drop on the same comparable channel."""
    if previous_price <= 0 or current_price >= previous_price:
        return None
    if (previous_price - current_price) / previous_price < threshold:
        return None
    return _quote_context(
        event="price_drop", product_name=product_name, current_price=current_price,
        previous_price=previous_price, platform=platform, shop_name=shop_name, url=url,
        market_variant=market_variant, warranty_type=warranty_type,
    )


def historical_low_alert(
    *, product_name: str, current_price: Decimal, historical_low: Decimal | None,
    platform: str, shop_name: str, url: str, market_variant: str, warranty_type: str,
) -> dict[str, str] | None:
    """Signal a new, strictly lower price; first observations do not alert."""
    if historical_low is None or current_price >= historical_low:
        return None
    return _quote_context(
        event="new_historical_low", product_name=product_name, current_price=current_price,
        previous_price=historical_low, platform=platform, shop_name=shop_name, url=url,
        market_variant=market_variant, warranty_type=warranty_type,
    )


def restock_alert(
    *, product_name: str, current_price: Decimal, previous_stock_status: str | None,
    current_stock_status: str, platform: str, shop_name: str, url: str,
    market_variant: str, warranty_type: str,
) -> dict[str, str] | None:
    if previous_stock_status != "out_of_stock" or current_stock_status != "in_stock":
        return None
    payload = _quote_context(
        event="restocked", product_name=product_name, current_price=current_price,
        previous_price=current_price, platform=platform, shop_name=shop_name, url=url,
        market_variant=market_variant, warranty_type=warranty_type,
    )
    payload["previous_stock_status"] = previous_stock_status
    payload["stock_status"] = current_stock_status
    return payload


def market_spread_alert(
    *, product_name: str, cn_price: Decimal, hk_price: Decimal, hk_market_variant: str,
    threshold_cny: Decimal, threshold_percent: Decimal = Decimal("0.05"),
) -> dict[str, str] | None:
    """Notify only when the tax/reference-CNY gap is material, never mixing used prices."""
    difference = abs(cn_price - hk_price)
    baseline = max(cn_price, hk_price)
    if baseline <= 0 or difference < threshold_cny or difference / baseline < threshold_percent:
        return None
    cheaper_market = "香港行货" if hk_market_variant == "hk_authorized" and hk_price < cn_price else (
        "香港水货" if hk_price < cn_price else "中国大陆"
    )
    return {
        "event": "cross_market_spread", "product": product_name,
        "current_price": str(hk_price), "previous_price": str(cn_price), "price_drop": str(cn_price - hk_price),
        "platform": "market_comparison", "shop_name": cheaper_market, "url": "",
        "market_variant": hk_market_variant, "warranty_type": "compare_before_purchase",
        "cn_reference_cny": str(cn_price), "hk_reference_cny": str(hk_price),
        "difference_cny": str(difference), "cheaper_market": cheaper_market,
    }
