"""SQLite persistence for normalized quotes and source snapshots."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from camera_tracker.normalization import NormalizedQuote
from camera_tracker.exchange_rates import HkdRate


@dataclass(frozen=True)
class PricePoint:
    captured_at: datetime
    final_price: Decimal


class SqliteRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, platform TEXT NOT NULL,
                    shop_name TEXT NOT NULL, url TEXT NOT NULL, captured_at TEXT NOT NULL,
                    final_price TEXT NOT NULL, currency TEXT NOT NULL, reference_cny TEXT,
                    condition TEXT NOT NULL, market_variant TEXT NOT NULL,
                    warranty_type TEXT NOT NULL, bundle_type TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS raw_snapshots (
                    id INTEGER PRIMARY KEY, quote_id INTEGER NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(quote_id) REFERENCES quotes(id)
                );
                CREATE TABLE IF NOT EXISTS source_health (
                    source_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT, last_success_at TEXT
                );
                CREATE TABLE IF NOT EXISTS exchange_rates (
                    currency TEXT NOT NULL, rate_date TEXT NOT NULL, cny_per_unit TEXT NOT NULL,
                    source TEXT NOT NULL, PRIMARY KEY(currency, rate_date)
                );
                CREATE TABLE IF NOT EXISTS notification_state (
                    product_id TEXT NOT NULL, event TEXT NOT NULL, last_sent_at TEXT NOT NULL,
                    PRIMARY KEY(product_id, event)
                );
            """)
            existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(quotes)")}
            for name, column_type in {
                "member_price": "TEXT", "coupon_discount": "TEXT NOT NULL DEFAULT '0'", "payment_discount": "TEXT NOT NULL DEFAULT '0'",
                "full_reduction": "TEXT NOT NULL DEFAULT '0'", "tax": "TEXT NOT NULL DEFAULT '0'",
                "gift_value": "TEXT NOT NULL DEFAULT '0'", "stock_status": "TEXT NOT NULL DEFAULT 'unknown'",
                "shutter_count": "INTEGER", "cosmetic_grade": "TEXT", "packaging_status": "TEXT",
                "warranty_remaining_days": "INTEGER", "trust_score": "INTEGER NOT NULL DEFAULT 70",
                "manual_confirmation_required": "INTEGER NOT NULL DEFAULT 0",
                "cash_price_only": "INTEGER NOT NULL DEFAULT 0", "quote_origin": "TEXT NOT NULL DEFAULT 'public'",
                "promotion_evidence": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in existing_columns:
                    connection.execute(f"ALTER TABLE quotes ADD COLUMN {name} {column_type}")

    def record_quote(
        self, quote: NormalizedQuote, *, captured_at: datetime, raw_payload: dict[str, object],
        trust_score: int = 70, manual_confirmation_required: bool = False,
    ) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO quotes(product_id, platform, shop_name, url, captured_at, final_price,
                   currency, reference_cny, condition, market_variant, warranty_type, bundle_type,
                   member_price, coupon_discount, payment_discount, full_reduction, tax, gift_value, stock_status,
                   shutter_count, cosmetic_grade, packaging_status, warranty_remaining_days, trust_score,
                   manual_confirmation_required, cash_price_only, quote_origin, promotion_evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (quote.product_id, quote.platform, quote.shop_name, quote.url, captured_at.isoformat(),
                 str(quote.final_price), quote.currency, str(quote.reference_cny) if quote.reference_cny is not None else None,
                 quote.condition, quote.market_variant, quote.warranty_type, quote.bundle_type,
                 str(quote.member_price) if quote.member_price is not None else None, str(quote.coupon_discount), str(quote.payment_discount),
                 str(quote.full_reduction), str(quote.tax), str(quote.gift_value), quote.stock_status,
                 quote.shutter_count, quote.cosmetic_grade, quote.packaging_status, quote.warranty_remaining_days,
                 trust_score, int(manual_confirmation_required), int(quote.cash_price_only),
                 str(raw_payload.get("quote_origin", "account_visible" if quote.platform == "jd_account_visible" else "public")),
                 str(raw_payload.get("promotion_text", ""))[:500]),
            )
            connection.execute("INSERT INTO raw_snapshots(quote_id, payload) VALUES (?, ?)", (cursor.lastrowid, json.dumps(raw_payload)))

    def price_history(self, product_id: str) -> list[PricePoint]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT captured_at, final_price FROM quotes WHERE product_id = ? ORDER BY captured_at", (product_id,)
            ).fetchall()
        return [PricePoint(datetime.fromisoformat(row["captured_at"]), Decimal(row["final_price"])) for row in rows]

    def cny_reference_history(
        self, product_id: str, *, trusted_only: bool = True, market_variant: str | None = None,
        condition: str | None = None,
    ) -> list[PricePoint]:
        """Comparable history for charts and forecasts, expressed in CNY reference prices."""
        clauses = ["product_id = ?", "(? = 0 OR (manual_confirmation_required = 0 AND trust_score >= 70))"]
        parameters: list[object] = [product_id, int(trusted_only)]
        if market_variant is not None:
            clauses.append("market_variant = ?")
            parameters.append(market_variant)
        if condition is not None:
            clauses.append("condition = ?")
            parameters.append(condition)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT captured_at, COALESCE(reference_cny, final_price) AS price
                    FROM quotes WHERE {' AND '.join(clauses)} ORDER BY captured_at""",
                parameters,
            ).fetchall()
        return [PricePoint(datetime.fromisoformat(row["captured_at"]), Decimal(row["price"])) for row in rows]

    def comparable_price_history(self, *, product_id: str, platform: str, market_variant: str) -> list[PricePoint]:
        """Prices comparable with a new quote; do not mix regions or channels."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT captured_at, final_price FROM quotes
                   WHERE product_id = ? AND platform = ? AND market_variant = ? AND condition = 'new'
                   ORDER BY captured_at""",
                (product_id, platform, market_variant),
            ).fetchall()
        return [PricePoint(datetime.fromisoformat(row["captured_at"]), Decimal(row["final_price"])) for row in rows]

    def latest_comparable_quote(self, *, product_id: str, platform: str, market_variant: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM quotes WHERE product_id = ? AND platform = ? AND market_variant = ?
                   ORDER BY id DESC LIMIT 1""",
                (product_id, platform, market_variant),
            ).fetchone()
        return dict(row) if row is not None else None

    def latest_market_quotes(self, product_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT q.* FROM quotes q
                   JOIN (SELECT platform, MAX(id) AS latest_id FROM quotes WHERE product_id = ? GROUP BY platform) latest
                   ON q.id = latest.latest_id ORDER BY q.platform""",
                (product_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_channel_quotes(self, product_id: str, *, trusted_only: bool = True) -> list[dict[str, object]]:
        """One latest quote per platform/store/market variant, preserving Price.com merchants."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT q.* FROM quotes q
                   JOIN (
                       SELECT platform, shop_name, market_variant, MAX(id) AS latest_id
                       FROM quotes WHERE product_id = ? GROUP BY platform, shop_name, market_variant
                   ) latest ON q.id = latest.latest_id
                   WHERE (? = 0 OR (q.manual_confirmation_required = 0 AND q.trust_score >= 70))
                   ORDER BY q.platform, q.shop_name""",
                (product_id, int(trusted_only)),
            ).fetchall()
        return [dict(row) for row in rows]

    def best_market_quotes(self, product_id: str) -> dict[str, dict[str, object]]:
        """Lowest trusted, in-stock/unknown quote in each non-interchangeable market segment."""
        segments: dict[str, list[dict[str, object]]] = {"cn": [], "hk_authorized": [], "hk_grey": [], "used": []}
        for quote in self.latest_channel_quotes(product_id):
            if quote["stock_status"] == "out_of_stock":
                continue
            if quote["condition"] != "new":
                segments["used"].append(quote)
            elif quote["market_variant"] == "cn":
                segments["cn"].append(quote)
            elif quote["market_variant"] == "hk_authorized":
                segments["hk_authorized"].append(quote)
            elif quote["market_variant"] == "hk_grey":
                segments["hk_grey"].append(quote)
        result: dict[str, dict[str, object]] = {}
        for segment, quotes in segments.items():
            if quotes:
                result[segment] = min(
                    quotes,
                    key=lambda quote: Decimal(str(quote["reference_cny"] or quote["final_price"])),
                )
        return result

    def used_market_quotes(
        self, product_id: str, *, max_price_cny: Decimal | None = None,
        max_shutter_count: int | None = None, min_warranty_days: int | None = None,
        cosmetic_grade: str | None = None,
    ) -> list[dict[str, object]]:
        """Latest manually collected used listings, with their condition metadata intact."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT q.* FROM quotes q
                   JOIN (
                       SELECT platform, shop_name, url, MAX(id) AS latest_id
                       FROM quotes WHERE product_id = ? AND condition = 'used'
                       GROUP BY platform, shop_name, url
                   ) latest ON q.id = latest.latest_id
                   WHERE q.manual_confirmation_required = 0
                   ORDER BY COALESCE(q.reference_cny, q.final_price) ASC""",
                (product_id,),
            ).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            quote = dict(row)
            price = Decimal(str(quote["reference_cny"] or quote["final_price"]))
            if max_price_cny is not None and price > max_price_cny:
                continue
            if max_shutter_count is not None and (quote["shutter_count"] is None or quote["shutter_count"] > max_shutter_count):
                continue
            if min_warranty_days is not None and (quote["warranty_remaining_days"] is None or quote["warranty_remaining_days"] < min_warranty_days):
                continue
            if cosmetic_grade is not None and quote["cosmetic_grade"] != cosmetic_grade:
                continue
            result.append(quote)
        return result

    def product_overview(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT q.product_id, q.final_price, q.currency, q.reference_cny, q.platform, q.captured_at, q.trust_score,
                   counts.history_points
                   FROM quotes q
                   JOIN (SELECT product_id, MAX(id) latest_id, COUNT(*) history_points FROM quotes GROUP BY product_id) counts
                   ON q.id = counts.latest_id ORDER BY q.product_id"""
            ).fetchall()
        return [dict(row) for row in rows]

    def raw_snapshot_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM raw_snapshots").fetchone()[0])

    def prune_raw_snapshots(self, *, before: datetime) -> int:
        """Remove only snapshots linked to quotes older than the retention threshold."""
        with self._connect() as connection:
            cursor = connection.execute(
                """DELETE FROM raw_snapshots WHERE quote_id IN (
                   SELECT id FROM quotes WHERE captured_at < ?
                )""",
                (before.isoformat(),),
            )
            return cursor.rowcount

    def record_source_failure(self, source_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO source_health(source_id, consecutive_failures, last_error)
                   VALUES (?, 1, ?)
                   ON CONFLICT(source_id) DO UPDATE SET consecutive_failures = consecutive_failures + 1, last_error = excluded.last_error""",
                (source_id, error),
            )

    def record_source_success(self, source_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO source_health(source_id, consecutive_failures, last_success_at)
                   VALUES (?, 0, ?)
                   ON CONFLICT(source_id) DO UPDATE SET consecutive_failures = 0, last_error = NULL, last_success_at = excluded.last_success_at""",
                (source_id, datetime.now().astimezone().isoformat()),
            )

    def source_health(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT source_id, consecutive_failures, last_error, last_success_at FROM source_health ORDER BY source_id").fetchall()
        return [dict(row) for row in rows]

    def source_failure_count(self, source_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT consecutive_failures FROM source_health WHERE source_id = ?", (source_id,)).fetchone()
        return int(row["consecutive_failures"]) if row is not None else 0

    def notification_due(self, *, product_id: str, event: str, now: datetime, cooldown_seconds: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT last_sent_at FROM notification_state WHERE product_id = ? AND event = ?", (product_id, event),
            ).fetchone()
        if row is None:
            return True
        previous = datetime.fromisoformat(row["last_sent_at"])
        return (now - previous).total_seconds() >= cooldown_seconds

    def mark_notification_sent(self, *, product_id: str, event: str, now: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO notification_state(product_id, event, last_sent_at) VALUES (?, ?, ?)
                   ON CONFLICT(product_id, event) DO UPDATE SET last_sent_at = excluded.last_sent_at""",
                (product_id, event, now.isoformat()),
            )

    def reset_notification_state(self, *, product_id: str, event: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM notification_state WHERE product_id = ? AND event = ?", (product_id, event))

    def save_exchange_rate(self, rate: HkdRate) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO exchange_rates(currency, rate_date, cny_per_unit, source)
                   VALUES ('HKD', ?, ?, ?)
                   ON CONFLICT(currency, rate_date) DO UPDATE SET cny_per_unit = excluded.cny_per_unit, source = excluded.source""",
                (rate.rate_date.isoformat(), str(rate.cny_per_hkd), rate.source),
            )

    def exchange_rate(self, currency: str, rate_date: datetime.date) -> HkdRate:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT rate_date, cny_per_unit, source FROM exchange_rates WHERE currency = ? AND rate_date = ?",
                (currency, rate_date.isoformat()),
            ).fetchone()
        if row is None:
            raise LookupError(f"No {currency} exchange rate for {rate_date}")
        return HkdRate(datetime.fromisoformat(row["rate_date"]).date(), Decimal(row["cny_per_unit"]), row["source"])
