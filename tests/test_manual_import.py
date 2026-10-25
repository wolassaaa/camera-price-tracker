from decimal import Decimal

from camera_tracker.adapters.manual_import import parse_manual_csv


def test_manual_csv_import_classifies_used_a1_listing() -> None:
    quotes = parse_manual_csv(
        "product_id,platform,shop_name,url,price,condition,market_variant,warranty_type,bundle_type,shutter_count\n"
        "sony-a1,goofish,个人卖家,https://example.test/a1,9500,used,cn,none,body_only,12345\n"
    )

    assert quotes[0].final_price == Decimal("9500")
    assert quotes[0].condition == "used"
    assert quotes[0].shutter_count == 12345


def test_manual_csv_import_preserves_used_condition_details() -> None:
    quotes = parse_manual_csv(
        "product_id,platform,shop_name,url,price,condition,market_variant,warranty_type,bundle_type,shutter_count,cosmetic_grade,packaging_status,warranty_remaining_days\n"
        "sony-a1,goofish,个人卖家,https://example.test/a1,9500,used,cn,shop,body_only,12345,excellent,complete,90\n"
    )

    assert quotes[0].cosmetic_grade == "excellent"
    assert quotes[0].packaging_status == "complete"
    assert quotes[0].warranty_remaining_days == 90
