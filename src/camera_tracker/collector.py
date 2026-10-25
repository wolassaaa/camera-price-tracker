"""Compliant public-page collection orchestration."""

from collections.abc import Callable
from decimal import Decimal
from dataclasses import replace
import logging

import httpx

from camera_tracker.adapters.jsonld import parse_product_jsonld
from camera_tracker.adapters.price_com_hk import parse_price_com_html
from camera_tracker.adapters.canon_cn import parse_canon_cn_product
from camera_tracker.adapters.sony_hk import parse_sony_hk_product
from camera_tracker.adapters.canon_hk import parse_canon_hk_product
from camera_tracker.adapters.canon_hk_store import parse_canon_hk_store_product
from camera_tracker.adapters.jd import extract_jd_sku, jd_price_api_url, parse_jd_price_payload
from camera_tracker.normalization import NormalizedQuote, normalize_quote
from camera_tracker.repository import SqliteRepository
from camera_tracker.source_status import SourceStatusRegistry
from datetime import datetime, timezone
from camera_tracker.exchange_rates import HkdRate, fetch_hkd_rate, hkd_to_cny
from camera_tracker.alerts import historical_low_alert, market_spread_alert, price_drop_alert, restock_alert, target_price_alert
from camera_tracker.reliability import assess_quote


logger = logging.getLogger("camera_tracker.collector")


def fetch_public_page(url: str) -> str:
    response = httpx.get(
        url, timeout=20, follow_redirects=True,
        headers={"User-Agent": "CameraPriceTracker/0.1 (+local monitoring)"},
    )
    response.raise_for_status()
    return response.text


def collect_jsonld_watch(watch: dict[str, str], *, fetch: Callable[[str], str] = fetch_public_page) -> list[NormalizedQuote]:
    html = fetch(watch["url"])
    parsed = parse_product_jsonld(
        html, product_id=watch["product_id"], platform=watch["platform"],
        shop_name=watch["shop_name"], url=watch["url"],
    )
    return [
        normalize_quote(
            product_id=quote.product_id, platform=quote.platform, shop_name=quote.shop_name,
            url=quote.url, list_price=quote.final_price, currency=quote.currency,
            condition=quote.condition, market_variant=quote.market_variant,
            warranty_type=quote.warranty_type, bundle_type=quote.bundle_type, stock_status=quote.stock_status,
        )
        for quote in parsed
    ]


def collect_price_com_watch(watch: dict[str, str], *, fetch: Callable[[str], str] = fetch_public_page) -> list[NormalizedQuote]:
    parsed = parse_price_com_html(fetch(watch["url"]), product_id=watch["product_id"], url=watch["url"])
    return [
        normalize_quote(
            product_id=quote.product_id, platform=watch["platform"], shop_name=quote.shop_name,
            url=quote.url, list_price=quote.final_price, currency="HKD", condition="new",
            market_variant=quote.market_variant, warranty_type=quote.warranty_type, bundle_type="body_only",
            stock_status=quote.stock_status, cash_price_only=quote.is_cash_price,
        )
        for quote in parsed
    ]


def collect_canon_cn_watch(watch: dict[str, str], *, fetch: Callable[[str], str] = fetch_public_page) -> list[NormalizedQuote]:
    quote = parse_canon_cn_product(fetch(watch["url"]), product_id=watch["product_id"], url=watch["url"])
    return [normalize_quote(
        product_id=quote.product_id, platform=quote.platform, shop_name=quote.shop_name, url=quote.url,
        list_price=quote.final_price, currency=quote.currency, condition=quote.condition,
        market_variant=quote.market_variant, warranty_type=quote.warranty_type, bundle_type=quote.bundle_type,
        stock_status=quote.stock_status,
    )]


def collect_sony_hk_watch(watch: dict[str, str], *, fetch: Callable[[str], str] = fetch_public_page) -> list[NormalizedQuote]:
    quote = parse_sony_hk_product(fetch(watch["url"]), product_id=watch["product_id"], url=watch["url"])
    return [normalize_quote(
        product_id=quote.product_id, platform=quote.platform, shop_name=quote.shop_name, url=quote.url,
        list_price=quote.final_price, currency=quote.currency, condition=quote.condition,
        market_variant=quote.market_variant, warranty_type=quote.warranty_type, bundle_type=quote.bundle_type,
        stock_status=quote.stock_status,
    )]


def collect_canon_hk_watch(watch: dict[str, str], *, fetch: Callable[[str], str] = fetch_public_page) -> list[NormalizedQuote]:
    quote = parse_canon_hk_product(fetch(watch["url"]), product_id=watch["product_id"], url=watch["url"])
    return [normalize_quote(
        product_id=quote.product_id, platform=quote.platform, shop_name=quote.shop_name, url=quote.url,
        list_price=quote.final_price, currency=quote.currency, condition=quote.condition,
        market_variant=quote.market_variant, warranty_type=quote.warranty_type, bundle_type=quote.bundle_type,
        stock_status=quote.stock_status,
    )]


def collect_canon_hk_store_watch(watch: dict[str, str], *, fetch: Callable[[str], str] = fetch_public_page) -> list[NormalizedQuote]:
    quote = parse_canon_hk_store_product(fetch(watch["url"]), product_id=watch["product_id"], url=watch["url"])
    return [normalize_quote(
        product_id=quote.product_id, platform=quote.platform, shop_name=quote.shop_name, url=quote.url,
        list_price=quote.final_price, currency=quote.currency, condition=quote.condition,
        market_variant=quote.market_variant, warranty_type=quote.warranty_type, bundle_type=quote.bundle_type,
        stock_status=quote.stock_status,
    )]


def collect_jd_watch(watch: dict[str, str], *, fetch: Callable[[str], str] = fetch_public_page) -> list[NormalizedQuote]:
    sku = extract_jd_sku(watch["url"])
    quote = parse_jd_price_payload(
        fetch(jd_price_api_url(sku)), product_id=watch["product_id"],
        shop_name=watch["shop_name"], url=watch["url"],
    )
    return [normalize_quote(
        product_id=quote.product_id, platform=quote.platform, shop_name=quote.shop_name, url=quote.url,
        list_price=quote.final_price, currency=quote.currency, condition=quote.condition,
        market_variant=quote.market_variant, warranty_type=quote.warranty_type, bundle_type=quote.bundle_type,
        stock_status=quote.stock_status,
    )]


def run_jsonld_watch(
    watch: dict[str, str], *, repository: SqliteRepository, status: SourceStatusRegistry,
    fetch: Callable[[str], str] = fetch_public_page,
) -> int:
    """Persist public quotes; preserve the failure rather than pretending success."""
    return run_watch(watch, repository=repository, status=status, fetch=fetch)


def run_watch(
    watch: dict[str, str], *, repository: SqliteRepository, status: SourceStatusRegistry,
    fetch: Callable[[str], str] = fetch_public_page,
    rate_fetch: Callable[[], HkdRate] = fetch_hkd_rate,
    target_prices: dict[str, Decimal] | None = None,
    notifier: Callable[[dict[str, str]], None] | None = None,
    source_notifier: Callable[[dict[str, str]], None] | None = None,
    market_spread_threshold_cny: Decimal = Decimal("500"),
) -> int:
    """Run a declared adapter only; unknown adapters remain visible failures."""
    try:
        adapter = watch.get("adapter", "jsonld")
        if adapter == "jsonld":
            quotes = collect_jsonld_watch(watch, fetch=fetch)
        elif adapter == "price_com_hk":
            quotes = collect_price_com_watch(watch, fetch=fetch)
        elif adapter == "canon_cn":
            quotes = collect_canon_cn_watch(watch, fetch=fetch)
        elif adapter == "sony_hk":
            quotes = collect_sony_hk_watch(watch, fetch=fetch)
        elif adapter == "canon_hk":
            quotes = collect_canon_hk_watch(watch, fetch=fetch)
        elif adapter == "canon_hk_store":
            quotes = collect_canon_hk_store_watch(watch, fetch=fetch)
        elif adapter == "jd":
            quotes = collect_jd_watch(watch, fetch=fetch)
        else:
            raise ValueError(f"Unsupported adapter: {adapter}")
        if any(quote.currency == "HKD" for quote in quotes):
            rate_date = datetime.now(timezone.utc).date()
            try:
                rate = repository.exchange_rate("HKD", rate_date)
            except LookupError:
                rate = rate_fetch()
                repository.save_exchange_rate(rate)
            quotes = [
                replace(quote, reference_cny=hkd_to_cny(quote.final_price, rate))
                if quote.currency == "HKD" else quote
                for quote in quotes
            ]
        for quote in quotes:
            previous_quote = repository.latest_comparable_quote(
                product_id=quote.product_id, platform=quote.platform, market_variant=quote.market_variant,
            )
            comparable = repository.comparable_price_history(
                product_id=quote.product_id, platform=quote.platform, market_variant=quote.market_variant,
            )
            previous_price = comparable[-1].final_price if comparable else quote.final_price
            historical_low = min((point.final_price for point in comparable), default=None)
            comparable_current = quote.final_price
            target_current = quote.reference_cny or quote.final_price
            median = sorted(point.final_price for point in comparable)
            market_median = median[len(median) // 2] if median else quote.final_price
            assessment = assess_quote(
                quote, market_median=market_median,
                official_or_authorized=quote.platform in {"sony_cn", "canon_cn", "sony_hk", "canon_hk", "canon_hk_store"},
            )
            repository.record_quote(
                quote, captured_at=datetime.now(timezone.utc),
                raw_payload={"collector": adapter, "url": watch["url"], "trust_score": assessment.score},
                trust_score=assessment.score, manual_confirmation_required=assessment.manual_confirmation_required,
            )
            if quote.platform == "price_com_hk":
                merchant_source = f"{quote.platform}:{quote.shop_name}"
                status.record_success(merchant_source)
                repository.record_source_success(merchant_source)
            if notifier is not None:
                alerts = [
                    price_drop_alert(
                        product_name=quote.product_id, current_price=comparable_current, previous_price=previous_price,
                        platform=quote.platform, shop_name=quote.shop_name, url=quote.url,
                        market_variant=quote.market_variant, warranty_type=quote.warranty_type,
                    ),
                    historical_low_alert(
                        product_name=quote.product_id, current_price=comparable_current, historical_low=historical_low,
                        platform=quote.platform, shop_name=quote.shop_name, url=quote.url,
                        market_variant=quote.market_variant, warranty_type=quote.warranty_type,
                    ) if assessment.eligible_for_historical_low else None,
                    restock_alert(
                        product_name=quote.product_id, current_price=comparable_current,
                        previous_stock_status=str(previous_quote["stock_status"]) if previous_quote else None,
                        current_stock_status=quote.stock_status, platform=quote.platform, shop_name=quote.shop_name,
                        url=quote.url, market_variant=quote.market_variant, warranty_type=quote.warranty_type,
                    ),
                ]
                if target_prices is not None and quote.product_id in target_prices:
                    target_price = target_prices[quote.product_id]
                    if target_current > target_price:
                        repository.reset_notification_state(product_id=quote.product_id, event="target_price_reached")
                    alerts.append(target_price_alert(
                        product_name=quote.product_id, current_price=target_current,
                        target_price=target_price, previous_price=previous_price,
                        platform=quote.platform, shop_name=quote.shop_name, url=quote.url,
                        market_variant=quote.market_variant, warranty_type=quote.warranty_type,
                    ))
                best_markets = repository.best_market_quotes(quote.product_id)
                cn_quote = best_markets.get("cn")
                hk_quote = best_markets.get("hk_authorized") or best_markets.get("hk_grey")
                if cn_quote is not None and hk_quote is not None:
                    alerts.append(market_spread_alert(
                        product_name=quote.product_id,
                        cn_price=Decimal(str(cn_quote["reference_cny"] or cn_quote["final_price"])),
                        hk_price=Decimal(str(hk_quote["reference_cny"] or hk_quote["final_price"])),
                        hk_market_variant=str(hk_quote["market_variant"]),
                        threshold_cny=market_spread_threshold_cny,
                    ))
                for alert in alerts:
                    if alert is not None:
                        try:
                            notifier(alert)
                        except Exception:
                            pass
        status.record_success(watch["platform"])
        repository.record_source_success(watch["platform"])
        logger.info("source=%s adapter=%s quotes_written=%s", watch["platform"], adapter, len(quotes))
        return len(quotes)
    except Exception as exc:
        status.record_failure(watch["platform"], str(exc))
        repository.record_source_failure(watch["platform"], str(exc))
        logger.warning("source=%s collection_failed=%s", watch["platform"], exc)
        if source_notifier is not None and status.get(watch["platform"]).manual_attention_required:
            try:
                source_notifier({
                    "event": "source_manual_attention", "product": f"source:{watch['platform']}",
                    "current_price": "", "previous_price": "", "price_drop": "", "platform": watch["platform"],
                    "shop_name": watch.get("shop_name", watch["platform"]), "url": watch["url"],
                    "market_variant": "", "warranty_type": "", "error": str(exc),
                })
            except Exception:
                pass
        raise
