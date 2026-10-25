"""Safe browser-page quote envelopes; browser credentials never enter this module."""

from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from camera_tracker.normalization import NormalizedQuote, normalize_quote


class BrowserQuoteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_id: str
    url: str
    status: Literal["available", "unavailable", "paused"]
    final_price: Decimal | None = None
    list_price: Decimal | None = None
    promotion_text: str = ""
    delivery_region: str = ""
    reason: str | None = None

    @field_validator("url")
    @classmethod
    def valid_jd_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not (parsed.hostname == "jd.com" or (parsed.hostname or "").endswith(".jd.com")):
            raise ValueError("browser quote URL must be an HTTPS JD URL")
        return value

    @model_validator(mode="after")
    def validate_price_contract(self) -> "BrowserQuoteResult":
        if self.status == "available" and (self.final_price is None or self.final_price <= 0):
            raise ValueError("available browser quote requires final_price")
        if self.status != "available" and self.final_price is not None:
            raise ValueError("unavailable browser quote must not include final_price")
        if self.list_price is not None and self.list_price <= 0:
            raise ValueError("list_price must be positive")
        return self

    def evidence(self) -> dict[str, object]:
        return {
            "collector": "browser_jd", "promotion_text": self.promotion_text[:500],
            "delivery_region": self.delivery_region[:100], "status": self.status, "reason": self.reason,
        }


def browser_quote_from_result(result: BrowserQuoteResult) -> NormalizedQuote:
    if result.status != "available" or result.final_price is None:
        raise ValueError("only available browser quotes can be persisted")
    list_price = result.list_price or result.final_price
    return normalize_quote(
        product_id=result.product_id, platform="jd_account_visible", shop_name="京东（账户可见）",
        url=result.url, list_price=list_price, coupon_discount=max(list_price - result.final_price, Decimal("0")),
        currency="CNY", condition="new", market_variant="cn", warranty_type="jd", bundle_type="body_only",
    )
