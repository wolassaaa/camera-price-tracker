"""User-provided CSV quotes for sources that cannot be collected compliantly."""

import csv
from dataclasses import dataclass
from decimal import Decimal
from io import StringIO


@dataclass(frozen=True)
class ManualQuote:
    product_id: str
    platform: str
    shop_name: str
    url: str
    final_price: Decimal
    condition: str
    market_variant: str
    warranty_type: str
    bundle_type: str
    shutter_count: int | None
    cosmetic_grade: str | None
    packaging_status: str | None
    warranty_remaining_days: int | None


def parse_manual_csv(content: str) -> list[ManualQuote]:
    return [
        ManualQuote(
            product_id=row["product_id"], platform=row["platform"], shop_name=row["shop_name"],
            url=row["url"], final_price=Decimal(row["price"]), condition=row["condition"],
            market_variant=row["market_variant"], warranty_type=row["warranty_type"],
            bundle_type=row["bundle_type"], shutter_count=int(row["shutter_count"]) if row.get("shutter_count") else None,
            cosmetic_grade=row.get("cosmetic_grade") or None,
            packaging_status=row.get("packaging_status") or None,
            warranty_remaining_days=int(row["warranty_remaining_days"]) if row.get("warranty_remaining_days") else None,
        )
        for row in csv.DictReader(StringIO(content))
    ]
