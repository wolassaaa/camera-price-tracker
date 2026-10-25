"""FastAPI application factory."""

from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import re

from decimal import Decimal, InvalidOperation

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from camera_tracker.config import load_events, load_products, load_settings, load_sources, load_target_prices, load_watches, save_events, save_products, save_settings, save_sources, save_target_prices, save_watches
from camera_tracker.adapters.manual_import import parse_manual_csv
from camera_tracker.normalization import normalize_quote
from camera_tracker.repository import SqliteRepository
from camera_tracker.source_status import SourceStatusRegistry
from camera_tracker.forecasting import forecast_horizons
from camera_tracker.buying import recommend
from camera_tracker.notifications import NotificationConfig, send_all
from camera_tracker.browser_quotes import BrowserQuoteResult, browser_quote_from_result


def create_app(
    repository: SqliteRepository | None = None,
    statuses: SourceStatusRegistry | None = None,
    config_dir: Path = Path("config"),
) -> FastAPI:
    load_dotenv()
    app = FastAPI(title="Camera Price Tracker", version="0.1.0")
    dashboard = Path(__file__).parent / "web" / "index.html"
    repository = repository or SqliteRepository(Path("data") / "tracker.db")
    statuses = statuses or SourceStatusRegistry()
    repository.path.parent.mkdir(parents=True, exist_ok=True)
    repository.migrate()

    def segment_history(product_id: str, segment: str) -> list:
        segments = {
            "cn": ("cn", "new"), "hk_authorized": ("hk_authorized", "new"),
            "hk_grey": ("hk_grey", "new"), "used": (None, "used"),
        }
        if segment == "best":
            markets = repository.best_market_quotes(product_id)
            selected = next((name for name in ("cn", "hk_authorized", "hk_grey", "used") if name in markets), None)
            market_variant, condition = segments[selected] if selected is not None else ("cn", "new")
        elif segment in segments:
            market_variant, condition = segments[segment]
        else:
            raise HTTPException(status_code=422, detail="segment must be best, cn, hk_authorized, hk_grey, or used")
        return repository.cny_reference_history(product_id, market_variant=market_variant, condition=condition)

    @app.get("/", include_in_schema=False)
    def dashboard_page() -> FileResponse:
        return FileResponse(dashboard)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/notifications/test")
    def test_notification() -> dict[str, object]:
        """Send an explicit test message only to channels configured locally in .env."""
        payload: dict[str, object] = {
            "event": "test_notification", "product": "Camera Price Tracker",
            "current_price": "", "previous_price": "", "price_drop": "", "platform": "local",
            "shop_name": "本地测试", "url": "", "market_variant": "", "warranty_type": "",
            "message": "这是一条本地配置测试通知，不代表真实价格变化。",
        }
        delivered = send_all(NotificationConfig.from_env(), payload)
        if not delivered:
            raise HTTPException(status_code=422, detail="No notification channel is configured in .env")
        return {"delivered": delivered}

    @app.get("/api/products")
    def products() -> list[dict[str, object]]:
        return load_products(config_dir / "products.yaml")

    @app.get("/api/settings")
    def settings() -> dict[str, object]:
        return {
            "sources": load_sources(config_dir / "sources.yaml"),
            "targets": [
                {"product_id": product_id, "target_price_cny": str(price)}
                for product_id, price in load_target_prices(config_dir / "alerts.yaml").items()
            ],
            "preferences": {"user_purchase_region": str(load_settings(config_dir / "settings.yaml").get("user_purchase_region", "cn"))},
        }

    @app.put("/api/settings/targets")
    def update_target_prices(targets: list[dict[str, object]] = Body()) -> dict[str, object]:
        product_ids = {str(product["id"]) for product in load_products(config_dir / "products.yaml")}
        parsed = load_target_prices(config_dir / "alerts.yaml")
        try:
            for item in targets:
                product_id = str(item["product_id"])
                if product_id not in product_ids:
                    raise HTTPException(status_code=422, detail=f"Unknown product_id: {product_id}")
                value = Decimal(str(item["target_price_cny"]))
                if value <= 0:
                    raise HTTPException(status_code=422, detail="target_price_cny must be positive")
                parsed[product_id] = value
        except (KeyError, InvalidOperation) as exc:
            raise HTTPException(status_code=422, detail="Invalid target price payload") from exc
        save_target_prices(config_dir / "alerts.yaml", parsed)
        return {"targets": [{"product_id": product_id, "target_price_cny": str(price)} for product_id, price in parsed.items()]}

    @app.put("/api/settings/sources")
    def update_sources(changes: dict[str, dict[str, object]] = Body()) -> dict[str, object]:
        """Update enabled state and safe polling settings; restart Worker to apply them."""
        sources = load_sources(config_dir / "sources.yaml")
        for source_id, change in changes.items():
            if source_id not in sources:
                raise HTTPException(status_code=422, detail=f"Unknown source_id: {source_id}")
            allowed = {"enabled", "interval_minutes", "jitter_seconds"}
            if not set(change).issubset(allowed):
                raise HTTPException(status_code=422, detail="Unsupported source setting")
            if "enabled" in change and not isinstance(change["enabled"], bool):
                raise HTTPException(status_code=422, detail="enabled must be boolean")
            for key, lower, upper in (("interval_minutes", 5, 1440), ("jitter_seconds", 0, 600)):
                if key in change:
                    try:
                        value = int(change[key])
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(status_code=422, detail=f"{key} must be an integer") from exc
                    if not lower <= value <= upper:
                        raise HTTPException(status_code=422, detail=f"{key} must be between {lower} and {upper}")
                    change[key] = value
            sources[source_id].update(change)
        save_sources(config_dir / "sources.yaml", sources)
        return {"sources": sources, "restart_required": True}

    @app.put("/api/settings/preferences")
    def update_preferences(preferences: dict[str, object] = Body()) -> dict[str, object]:
        region = str(preferences.get("user_purchase_region", ""))
        if region not in {"cn", "hk"}:
            raise HTTPException(status_code=422, detail="user_purchase_region must be cn or hk")
        settings = load_settings(config_dir / "settings.yaml")
        settings["user_purchase_region"] = region
        save_settings(config_dir / "settings.yaml", settings)
        return {"preferences": {"user_purchase_region": region}}

    @app.put("/api/settings/products/{product_id}")
    def upsert_product(product_id: str, product: dict[str, object] = Body()) -> dict[str, object]:
        """Maintain catalog entries locally; adding a watch URL remains an explicit separate step."""
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", product_id):
            raise HTTPException(status_code=422, detail="product_id must use lowercase letters, digits, and hyphens")
        if product.get("id", product_id) != product_id:
            raise HTTPException(status_code=422, detail="Product id must match URL")
        name = str(product.get("name", "")).strip()
        product_type = str(product.get("type", ""))
        aliases_value = product.get("aliases", [])
        if not name or product_type not in {"body", "lens"} or not isinstance(aliases_value, list):
            raise HTTPException(status_code=422, detail="name, type (body/lens), and aliases[] are required")
        aliases = [str(alias).strip() for alias in aliases_value if str(alias).strip()]
        if len(set(alias.casefold() for alias in aliases)) != len(aliases):
            raise HTTPException(status_code=422, detail="Aliases must be unique")
        products = load_products(config_dir / "products.yaml")
        protected_aliases = {
            str(value).casefold()
            for item in products if item["id"] != product_id
            for value in [item["name"], *item.get("aliases", [])]
        }
        if name.casefold() in protected_aliases or any(alias.casefold() in protected_aliases for alias in aliases):
            raise HTTPException(status_code=422, detail="Name or alias conflicts with another product")
        normalized = {"id": product_id, "name": name, "type": product_type, "aliases": aliases}
        existing = next((index for index, item in enumerate(products) if item["id"] == product_id), None)
        if existing is None:
            products.append(normalized)
        else:
            products[existing] = normalized
        save_products(config_dir / "products.yaml", products)
        return {"product": normalized, "restart_required": True}

    @app.put("/api/settings/watches")
    def upsert_watch(watch: dict[str, object] = Body()) -> dict[str, object]:
        """Register an explicit public product URL; no discovery, cookie, or login bypass is performed."""
        required = ("product_id", "platform", "shop_name", "url", "adapter")
        if any(not str(watch.get(field, "")).strip() for field in required):
            raise HTTPException(status_code=422, detail="product_id, platform, shop_name, url, and adapter are required")
        normalized = {field: str(watch[field]).strip() for field in required}
        if normalized["product_id"] not in {str(item["id"]) for item in load_products(config_dir / "products.yaml")}:
            raise HTTPException(status_code=422, detail="Unknown product_id")
        if normalized["platform"] not in load_sources(config_dir / "sources.yaml"):
            raise HTTPException(status_code=422, detail="Unknown platform")
        if not normalized["url"].startswith("https://"):
            raise HTTPException(status_code=422, detail="Only explicit HTTPS public URLs are supported")
        if normalized["adapter"] not in {"jsonld", "price_com_hk", "canon_cn", "sony_hk", "canon_hk", "canon_hk_store", "jd", "browser_jd"}:
            raise HTTPException(status_code=422, detail="Unsupported adapter")
        watches = load_watches(config_dir / "watches.yaml")
        existing = next((index for index, item in enumerate(watches) if item["product_id"] == normalized["product_id"] and item["platform"] == normalized["platform"] and item["url"] == normalized["url"]), None)
        if existing is None:
            watches.append(normalized)
        else:
            watches[existing] = normalized
        save_watches(config_dir / "watches.yaml", watches)
        return {"watch": normalized, "restart_required": True}

    @app.get("/api/browser-watches")
    def browser_watches(platform: str = Query(default="jd")) -> list[dict[str, object]]:
        if platform != "jd":
            raise HTTPException(status_code=422, detail="Only jd browser watches are supported")
        source = load_sources(config_dir / "sources.yaml").get("jd_account_visible", {})
        if source.get("enabled") is not True:
            return []
        return [
            {"product_id": watch["product_id"], "url": watch["url"], "interval_minutes": max(60, int(source.get("interval_minutes", 60)))}
            for watch in load_watches(config_dir / "watches.yaml") if watch.get("adapter") == "browser_jd"
        ]

    @app.post("/api/browser-quotes")
    def browser_quote(result: BrowserQuoteResult) -> dict[str, object]:
        if result.status != "available":
            repository.record_source_failure("jd_account_visible", result.reason or "券后价不可得")
            return {"recorded": False, "status": result.status}
        repository.record_quote(
            browser_quote_from_result(result), captured_at=datetime.now(timezone.utc), raw_payload=result.evidence(), trust_score=90,
        )
        repository.record_source_success("jd_account_visible")
        return {"recorded": True, "status": result.status}

    @app.get("/api/products/{product_id}/account-price")
    def account_price(product_id: str) -> dict[str, object]:
        quote = next((row for row in repository.latest_channel_quotes(product_id, trusted_only=False) if row["platform"] == "jd_account_visible"), None)
        if quote is None:
            health = next((row for row in repository.source_health() if row["source_id"] == "jd_account_visible"), None)
            return {"available": False, "reason": health["last_error"] if health else "尚未检测到券后价"}
        return {"available": True, "final_price": str(quote["final_price"]), "captured_at": quote["captured_at"], "promotion_evidence": quote.get("promotion_evidence", "")}

    @app.get("/api/products/{product_id}/events")
    def product_events(product_id: str) -> list[dict[str, object]]:
        return [event for event in load_events(config_dir / "events.yaml") if event["product_id"] == product_id]

    @app.put("/api/settings/events/{event_id}")
    def upsert_product_event(event_id: str, event: dict[str, object] = Body()) -> dict[str, object]:
        allowed_types = {"release", "preorder", "promotion", "official_price", "clearance", "price_change"}
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", event_id):
            raise HTTPException(status_code=422, detail="event_id must use lowercase letters, digits, and hyphens")
        product_id = str(event.get("product_id", ""))
        event_type = str(event.get("type", ""))
        title = str(event.get("title", "")).strip()
        event_date = str(event.get("date", ""))
        url = str(event.get("url", "")).strip()
        if product_id not in {str(item["id"]) for item in load_products(config_dir / "products.yaml")}:
            raise HTTPException(status_code=422, detail="Unknown product_id")
        if event_type not in allowed_types or not title:
            raise HTTPException(status_code=422, detail="type and title are required")
        try:
            date.fromisoformat(event_date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD") from exc
        if url and not url.startswith("https://"):
            raise HTTPException(status_code=422, detail="source URL must be HTTPS")
        normalized = {"id": event_id, "product_id": product_id, "type": event_type, "title": title, "date": event_date, "url": url}
        events = load_events(config_dir / "events.yaml")
        existing = next((index for index, item in enumerate(events) if item["id"] == event_id), None)
        if existing is None:
            events.append(normalized)
        else:
            events[existing] = normalized
        events.sort(key=lambda item: (str(item["date"]), str(item["id"])), reverse=True)
        save_events(config_dir / "events.yaml", events)
        return {"event": normalized}

    @app.get("/api/overview")
    def overview() -> list[dict[str, object]]:
        return [
            {
                "product_id": row["product_id"], "current_price": str(row["final_price"]),
                "currency": row["currency"], "reference_cny": str(row["reference_cny"] or ""),
                "platform": row["platform"], "captured_at": row["captured_at"],
                "history_points": row["history_points"], "trust_score": row["trust_score"],
            }
            for row in repository.product_overview()
        ]

    @app.get("/api/products/{product_id}/history")
    def product_history(
        product_id: str, window: str = Query(default="all"), segment: str = Query(default="best"),
    ) -> list[dict[str, str]]:
        windows = {
            "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30),
            "90d": timedelta(days=90), "180d": timedelta(days=180), "all": None,
        }
        if window not in windows:
            raise HTTPException(status_code=422, detail="window must be 24h, 7d, 30d, 90d, 180d, or all")
        points = segment_history(product_id, segment)
        if points and windows[window] is not None:
            cutoff = points[-1].captured_at - windows[window]
            points = [point for point in points if point.captured_at >= cutoff]
        return [
            {"captured_at": point.captured_at.isoformat(), "final_price": str(point.final_price)}
            for point in points
        ]

    @app.get("/api/products/{product_id}/comparison")
    def market_comparison(product_id: str) -> dict[str, object]:
        quotes = repository.best_market_quotes(product_id)
        result: dict[str, dict[str, str]] = {}
        for bucket, quote in quotes.items():
            result[bucket] = {
                "platform": str(quote["platform"]), "currency": str(quote["currency"]),
                "final_price": str(quote["final_price"]), "reference_cny": str(quote["reference_cny"] or ""),
                "warranty_type": str(quote["warranty_type"]), "market_variant": str(quote["market_variant"]),
                "shop_name": str(quote["shop_name"]), "trust_score": str(quote["trust_score"]),
                "cash_price_only": bool(quote["cash_price_only"]),
            }
        if "hk_authorized" in result:
            result["hk"] = result["hk_authorized"]
        elif "hk_grey" in result:
            result["hk"] = result["hk_grey"]
        cn = quotes.get("cn")
        hk = quotes.get("hk_authorized") or quotes.get("hk_grey")
        if cn is not None and hk is not None:
            cn_price = Decimal(str(cn["reference_cny"] or cn["final_price"]))
            hk_price = Decimal(str(hk["reference_cny"] or hk["final_price"]))
            result["spread"] = {
                "cn_reference_cny": str(cn_price), "hk_reference_cny": str(hk_price),
                "difference_cny": str(abs(cn_price - hk_price)),
                "cheaper_market": "hk" if hk_price < cn_price else "cn",
            }
        return result

    @app.get("/api/products/{product_id}/metrics")
    def product_metrics(product_id: str) -> dict[str, str | None]:
        """Comparable trusted-price indicators; each metric keeps market/condition boundaries explicit."""
        quotes = [
            quote for quote in repository.latest_channel_quotes(product_id)
            if quote["condition"] == "new" and quote["stock_status"] != "out_of_stock"
        ]
        def price(quote: dict[str, object]) -> Decimal:
            return Decimal(str(quote["reference_cny"] or quote["final_price"]))
        def lowest(items: list[dict[str, object]]) -> Decimal | None:
            return min((price(item) for item in items), default=None)
        def serialized(value: Decimal | None) -> str | None:
            return str(value) if value is not None else None
        prices = sorted(price(quote) for quote in quotes)
        used_prices = sorted(
            Decimal(str(quote["reference_cny"] or quote["final_price"]))
            for quote in repository.used_market_quotes(product_id)
        )
        official_platforms = {"sony_cn", "sony_hk", "canon_cn", "canon_hk", "canon_hk_store"}
        official = [quote for quote in quotes if quote["platform"] in official_platforms]
        authorized = [quote for quote in quotes if quote["market_variant"] in {"cn", "hk_authorized"}]
        return {
            "official_trusted_low_cny": serialized(lowest(official)),
            "authorized_trusted_low_cny": serialized(lowest(authorized)),
            "market_trusted_low_cny": serialized(lowest(quotes)),
            "market_median_cny": serialized(prices[len(prices) // 2]) if prices else None,
            "used_median_cny": serialized(used_prices[len(used_prices) // 2]) if used_prices else None,
            "hk_authorized_low_cny": serialized(lowest([quote for quote in quotes if quote["market_variant"] == "hk_authorized"])),
            "hk_grey_low_cny": serialized(lowest([quote for quote in quotes if quote["market_variant"] == "hk_grey"])),
        }

    @app.get("/api/products/{product_id}/forecast")
    def product_forecast(product_id: str, segment: str = Query(default="best")) -> dict[str, dict[str, object]]:
        return {
            str(horizon): {
                "available": result.available, "median_price": str(result.median_price) if result.median_price is not None else None,
                "lower_bound": str(result.lower_bound) if result.lower_bound is not None else None,
                "upper_bound": str(result.upper_bound) if result.upper_bound is not None else None,
                "trend": result.trend, "confidence": result.confidence, "sample_count": result.sample_count,
                "days_covered": result.days_covered, "reason": result.reason,
                "better_buy_window_probability": result.better_buy_window_probability,
                "near_historical_low": result.near_historical_low,
                "promotion_events": list(result.promotion_events),
                "promotion_sample_count": result.promotion_sample_count,
                "model_name": result.model_name,
                "backtest_mae": str(result.backtest_mae) if result.backtest_mae is not None else None,
            }
            for horizon, result in forecast_horizons(segment_history(product_id, segment)).items()
        }

    @app.get("/api/products/{product_id}/recommendation")
    def product_recommendation(product_id: str, segment: str = Query(default="best")) -> dict[str, object]:
        history = segment_history(product_id, segment)
        if not history:
            return {"score": 0, "label": "建议观望", "reason": "尚无价格历史，无法生成购买建议"}
        current = history[-1].final_price
        prices = [point.final_price for point in history]
        historical_low = min(prices)
        percentile = round(sum(price <= current for price in prices) / len(prices) * 100)
        forecast = forecast_horizons(history)[30]
        drop_probability = forecast.better_buy_window_probability if forecast.available else 0.2
        markets = repository.best_market_quotes(product_id)
        selected = next((key for key in ("cn", "hk_authorized", "hk_grey", "used") if key in markets), None) if segment == "best" else segment
        quote = markets.get(selected)
        reliable_channel = bool(quote and quote["platform"] in {"sony_cn", "sony_hk", "canon_cn", "canon_hk", "canon_hk_store"})
        preferred_region = str(load_settings(config_dir / "settings.yaml").get("user_purchase_region", "cn"))
        events = load_events(config_dir / "events.yaml")
        today = date.today()
        release_risk = any(event["product_id"] == product_id and event["type"] in {"release", "preorder"} and date.fromisoformat(str(event["date"])) >= today for event in events)
        clearance_signal = any(event["product_id"] == product_id and event["type"] == "clearance" and date.fromisoformat(str(event["date"])) >= today - timedelta(days=90) for event in events)
        regional_savings = Decimal("0")
        if quote is not None:
            current_reference = Decimal(str(quote["reference_cny"] or quote["final_price"]))
            preferred_quote = markets.get("cn" if preferred_region == "cn" else "hk_authorized")
            if preferred_quote is not None:
                regional_savings = max(Decimal("0"), Decimal(str(preferred_quote["reference_cny"] or preferred_quote["final_price"])) - current_reference)
        result = recommend(
            current_price=current, trusted_historical_low=historical_low,
            historical_percentile=percentile, forecast_drop_probability=drop_probability,
            reliable_channel=reliable_channel, stock_status=str(quote["stock_status"]) if quote else "unknown",
            warranty_type=str(quote["warranty_type"]) if quote else "unknown",
            complex_offer=bool(quote and quote["cash_price_only"]), release_risk=release_risk,
            clearance_signal=clearance_signal, regional_savings=regional_savings, preferred_region=preferred_region,
        )
        return {"score": result.score, "label": result.label, "reason": result.reason,
                "historical_percentile": percentile, "trusted_historical_low": str(historical_low),
                "forecast_drop_probability": drop_probability, "preferred_region": preferred_region,
                "regional_savings": str(regional_savings), "release_risk": release_risk,
                "clearance_signal": clearance_signal}

    @app.get("/api/used/{product_id}")
    def used_market(
        product_id: str, max_price_cny: Decimal | None = None, max_shutter_count: int | None = None,
        min_warranty_days: int | None = None, cosmetic_grade: str | None = Query(default=None),
    ) -> dict[str, object]:
        quotes = repository.used_market_quotes(
            product_id, max_price_cny=max_price_cny, max_shutter_count=max_shutter_count,
            min_warranty_days=min_warranty_days, cosmetic_grade=cosmetic_grade,
        )
        prices = [Decimal(str(row["reference_cny"] or row["final_price"])) for row in quotes]
        median = sorted(prices)[len(prices) // 2] if prices else None
        return {
            "product_id": product_id,
            "summary": {"count": len(quotes), "lowest_cny": str(min(prices)) if prices else None,
                        "median_cny": str(median) if median is not None else None},
            "quotes": [
                {"platform": row["platform"], "shop_name": row["shop_name"], "url": row["url"],
                 "price_cny": str(row["reference_cny"] or row["final_price"]), "shutter_count": row["shutter_count"],
                 "cosmetic_grade": row["cosmetic_grade"], "packaging_status": row["packaging_status"],
                 "warranty_remaining_days": row["warranty_remaining_days"], "warranty_type": row["warranty_type"],
                 "captured_at": row["captured_at"]}
                for row in quotes
            ],
        }

    @app.post("/api/import/csv")
    def import_csv(content: str = Body(media_type="text/plain")) -> dict[str, int]:
        try:
            quotes = parse_manual_csv(content)
        except (KeyError, ValueError, InvalidOperation) as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid CSV: required columns include product_id, platform, shop_name, url, price, condition, market_variant, warranty_type, bundle_type",
            ) from exc
        for quote in quotes:
            repository.record_quote(
                normalize_quote(
                    product_id=quote.product_id, platform=quote.platform, shop_name=quote.shop_name,
                    url=quote.url, list_price=quote.final_price, condition=quote.condition,
                    market_variant=quote.market_variant, warranty_type=quote.warranty_type,
                    bundle_type=quote.bundle_type,
                    shutter_count=quote.shutter_count, cosmetic_grade=quote.cosmetic_grade,
                    packaging_status=quote.packaging_status, warranty_remaining_days=quote.warranty_remaining_days,
                ),
                captured_at=datetime.now(timezone.utc), raw_payload={"import": "manual_csv"},
            )
        return {"imported": len(quotes)}

    @app.get("/api/sources")
    def sources() -> list[dict[str, object]]:
        ephemeral = [
            {
                "source_id": source_id,
                "consecutive_failures": state.consecutive_failures,
                "manual_attention_required": state.manual_attention_required,
                "last_error": state.last_error,
                "last_success_at": state.last_success_at.isoformat() if state.last_success_at else None,
            }
            for source_id, state in statuses.all().items()
        ]
        reported = list(ephemeral)
        existing_ids = {str(row["source_id"]) for row in reported}
        for row in repository.source_health():
            if str(row["source_id"]) not in existing_ids:
                reported.append(row)
                existing_ids.add(str(row["source_id"]))
        for source_id, source in load_sources(config_dir / "sources.yaml").items():
            if source_id in existing_ids:
                continue
            manual_required = bool(source.get("manual_cookie_required") or source.get("manual_confirmation_required"))
            reported.append({
                "source_id": source_id, "consecutive_failures": 0,
                "manual_attention_required": manual_required,
                "last_error": "需要用户手动导入或公开接口" if manual_required else None,
                "last_success_at": None,
            })
        return reported

    return app


app = create_app()
