from decimal import Decimal

from camera_tracker.alerts import historical_low_alert, market_spread_alert, price_drop_alert, restock_alert, target_price_alert


def test_target_price_alert_includes_actionable_quote_context() -> None:
    alert = target_price_alert(
        product_name="Canon EOS R5 Mark II", current_price=Decimal("29999"), target_price=Decimal("30000"),
        previous_price=Decimal("30599"), platform="canon_cn", shop_name="佳能官方线上商城",
        url="https://example.test", market_variant="cn", warranty_type="manufacturer",
    )

    assert alert is not None
    assert alert["event"] == "target_price_reached"
    assert alert["price_drop"] == "600"


def test_price_drop_requires_a_material_same_channel_drop() -> None:
    alert = price_drop_alert(
        product_name="Canon EOS R5 Mark II", current_price=Decimal("27000"), previous_price=Decimal("30599"),
        platform="canon_cn", shop_name="佳能官方线上商城", url="https://example.test",
        market_variant="cn", warranty_type="manufacturer",
    )

    assert alert is not None
    assert alert["event"] == "price_drop"
    assert price_drop_alert(
        product_name="Canon EOS R5 Mark II", current_price=Decimal("30000"), previous_price=Decimal("30599"),
        platform="canon_cn", shop_name="佳能官方线上商城", url="https://example.test",
        market_variant="cn", warranty_type="manufacturer",
    ) is None


def test_historical_low_alert_excludes_first_or_equal_observations() -> None:
    context = dict(
        product_name="Canon EOS R5 Mark II", current_price=Decimal("29999"),
        platform="canon_cn", shop_name="佳能官方线上商城", url="https://example.test",
        market_variant="cn", warranty_type="manufacturer",
    )

    assert historical_low_alert(historical_low=None, **context) is None
    assert historical_low_alert(historical_low=Decimal("29999"), **context) is None
    assert historical_low_alert(historical_low=Decimal("30000"), **context)["event"] == "new_historical_low"


def test_restock_alert_requires_a_real_out_of_stock_to_in_stock_transition() -> None:
    context = dict(
        product_name="Canon EOS R5 Mark II", current_price=Decimal("30000"), platform="canon_cn",
        shop_name="佳能官方线上商城", url="https://example.test", market_variant="cn", warranty_type="manufacturer",
    )

    assert restock_alert(previous_stock_status="unknown", current_stock_status="in_stock", **context) is None
    assert restock_alert(previous_stock_status="out_of_stock", current_stock_status="in_stock", **context)["event"] == "restocked"


def test_market_spread_alert_requires_meaningful_cny_and_percent_gap() -> None:
    alert = market_spread_alert(
        product_name="Canon EOS R5 Mark II", cn_price=Decimal("30599"), hk_price=Decimal("25925.60"),
        hk_market_variant="hk_authorized", threshold_cny=Decimal("500"),
    )

    assert alert is not None
    assert alert["cheaper_market"] == "香港行货"
    assert market_spread_alert(
        product_name="Canon EOS R5 Mark II", cn_price=Decimal("30599"), hk_price=Decimal("30200"),
        hk_market_variant="hk_authorized", threshold_cny=Decimal("500"),
    ) is None
