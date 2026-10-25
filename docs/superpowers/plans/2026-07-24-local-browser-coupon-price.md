# Local Browser Coupon-Price Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record JD prices only when the user’s normal Chrome page explicitly shows an account-visible coupon-after price, without exposing browser cookies or changing the cart.

**Architecture:** A Manifest V3 extension receives only JD browser-monitor watches from the local FastAPI app, opens low-frequency background product tabs, and extracts visible DOM text. It posts a small, strict result envelope to localhost. The API validates the URL and status, persists a normalized `jd_account_visible` quote only for an explicit final price, and stores all unavailable/error results as source health rather than inventing a price.

**Tech Stack:** Python 3.11+, FastAPI/Pydantic, SQLite, pytest, plain JavaScript Manifest V3 Chrome extension, Node built-in test runner.

## Global Constraints

- Never read, export, persist, log, or transmit cookies, localStorage, sessionStorage, passwords, OTPs, checkout data, or order data.
- First release supports only `https://*.jd.com/` product pages and an explicit page-visible final price; it does not claim coupons, add items to cart, or open checkout.
- Browser polling interval must be at least 60 minutes per watch. A CAPTCHA, login wall, account-abnormal page, or non-mainland delivery signal pauses the affected watch without a retry loop.
- Do not record a base/list price as a personal coupon-after price. Only `status="available"` with an explicit final price creates a quote.
- Preserve existing public collectors and their tests. Do not change global network/VPN settings.
- Do not stage or commit repository changes unless the user explicitly asks.

## File Structure

- Create: `extension/manifest.json` — local-only extension metadata and minimum host permissions.
- Create: `extension/service-worker.js` — alarm scheduling, background tab lifecycle, localhost calls, no session inspection.
- Create: `extension/content/jd-parser.js` — pure DOM-text parser and stop-signal detector, exported for Node tests.
- Create: `extension/content/jd-content.js` — page bridge which invokes the parser and messages the service worker.
- Create: `extension/test/jd-parser.test.mjs` — Node tests for parser behavior using synthetic DOM-like text.
- Create: `tests/fixtures/jd_account_visible.html` — minimal non-sensitive fixture showing explicit coupon-after price.
- Create: `src/camera_tracker/browser_quotes.py` — strict request models, JD URL validation, DOM-result-to-quote conversion.
- Modify: `src/camera_tracker/repository.py` — migrations for coupon discount/evidence/origin fields.
- Modify: `src/camera_tracker/api.py` — browser-watch feed and browser-result receiver.
- Modify: `src/camera_tracker/web/index.html` — account-visible coupon-price card and paused-state display.
- Modify: `config/sources.yaml` — add disabled-by-default `jd_account_visible` cadence declaration.
- Modify: `README.md` — unpacked-extension install/use/reset instructions and boundaries.
- Create: `tests/test_browser_quotes.py` — model, URL, persistence and unavailable-state tests.
- Modify: `tests/test_api.py` — endpoint and dashboard-data tests.
- Modify: `tests/test_dashboard.py` — static dashboard contract test.

---

### Task 1: Persist auditable account-visible coupon quotes

**Files:**
- Create: `src/camera_tracker/browser_quotes.py`
- Modify: `src/camera_tracker/repository.py`
- Create: `tests/test_browser_quotes.py`

**Interfaces:**
- Produces `BrowserQuoteResult` with `product_id: str`, `url: str`, `status: Literal["available", "unavailable", "paused"]`, `final_price: Decimal | None`, `list_price: Decimal | None`, `promotion_text: str`, `delivery_region: str`, and `reason: str | None`.
- Produces `browser_quote_from_result(result: BrowserQuoteResult) -> NormalizedQuote` only for `status == "available"`.
- Adds `coupon_discount`, `quote_origin`, and `promotion_evidence` columns to `quotes`; old databases migrate without data loss.

- [ ] **Step 1: Write failing conversion and migration tests**

```python
def test_account_visible_result_records_final_price_and_evidence(tmp_path) -> None:
    result = BrowserQuoteResult(
        product_id="canon-r5m2", url="https://item.jd.com/1001.html",
        status="available", list_price=Decimal("30999"), final_price=Decimal("28499"),
        promotion_text="满10000减500，PLUS券减2000", delivery_region="上海", reason=None,
    )
    quote = browser_quote_from_result(result)
    repository = SqliteRepository(tmp_path / "tracker.db")
    repository.migrate()
    repository.record_quote(quote, captured_at=datetime(2026, 7, 24, tzinfo=timezone.utc), raw_payload=result.evidence())
    latest = repository.latest_channel_quotes("canon-r5m2", trusted_only=False)[0]
    assert latest["final_price"] == "28499"
    assert latest["coupon_discount"] == "2500"
    assert latest["quote_origin"] == "account_visible"
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `python -m pytest tests/test_browser_quotes.py -q`

Expected: FAIL because `camera_tracker.browser_quotes` does not exist.

- [ ] **Step 3: Implement strict models and migration**

```python
class BrowserQuoteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_id: str
    url: AnyHttpUrl
    status: Literal["available", "unavailable", "paused"]
    final_price: Decimal | None = None
    list_price: Decimal | None = None
    promotion_text: str = ""
    delivery_region: str = ""
    reason: str | None = None

    @model_validator(mode="after")
    def validate_price_contract(self) -> "BrowserQuoteResult":
        if self.status == "available" and (self.final_price is None or self.final_price <= 0):
            raise ValueError("available browser quote requires final_price")
        if self.status != "available" and self.final_price is not None:
            raise ValueError("unavailable browser quote must not include final_price")
        return self
```

Add the three columns with `ALTER TABLE` only when absent. `browser_quote_from_result` must reject non-available results, use platform `jd_account_visible`, market `cn`, CNY, shop name `京东（账户可见）`, and `coupon_discount=max(list_price-final_price, Decimal("0"))`.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_browser_quotes.py tests/test_repository.py -q`

Expected: PASS.

### Task 2: Add localhost browser-watch and result APIs

**Files:**
- Modify: `src/camera_tracker/api.py`
- Modify: `config/sources.yaml`
- Modify: `tests/test_api.py`

**Interfaces:**
- `GET /api/browser-watches?platform=jd` returns only watches with `adapter: browser_jd` and source enabled, with `product_id`, `url`, and `interval_minutes`.
- `POST /api/browser-quotes` accepts exactly one `BrowserQuoteResult` and returns `{ "recorded": bool, "status": str }`.

- [ ] **Step 1: Write failing API tests**

```python
def test_browser_watch_feed_excludes_public_jd_watch(tmp_path) -> None:
    client = configured_client(tmp_path, watches=[
        {"product_id": "canon-r5m2", "platform": "jd", "shop_name": "JD", "url": "https://item.jd.com/1.html", "adapter": "jd"},
        {"product_id": "canon-r5m2", "platform": "jd_account_visible", "shop_name": "JD", "url": "https://item.jd.com/2.html", "adapter": "browser_jd"},
    ])
    assert client.get("/api/browser-watches?platform=jd").json() == [{
        "product_id": "canon-r5m2", "url": "https://item.jd.com/2.html", "interval_minutes": 60,
    }]

def test_browser_quote_unavailable_records_health_but_no_price(tmp_path) -> None:
    client, repository = client_and_repository(tmp_path)
    response = client.post("/api/browser-quotes", json={
        "product_id": "canon-r5m2", "url": "https://item.jd.com/2.html", "status": "paused",
        "promotion_text": "", "delivery_region": "", "reason": "账号页面异常",
    })
    assert response.json() == {"recorded": False, "status": "paused"}
    assert repository.price_history("canon-r5m2") == []
    assert repository.source_health()[0]["source_id"] == "jd_account_visible"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m pytest tests/test_api.py -k browser -q`

Expected: FAIL with 404 for both browser routes.

- [ ] **Step 3: Implement the routes and source configuration**

Add this source configuration:

```yaml
  jd_account_visible:
    enabled: true
    interval_minutes: 60
    jitter_seconds: 180
    browser_only: true
```

The watch route must use `load_watches`, filter `adapter == "browser_jd"`, and never return a password, cookie, headers, source-health error text, or any user data. The post route must call `validate_jd_product_url`, reject a non-JD host with 422, record `available` quotes with `trust_score=90`, and record `paused`/`unavailable` via `repository.record_source_failure("jd_account_visible", reason)` without writing a quote.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_api.py tests/test_browser_quotes.py -q`

Expected: PASS.

### Task 3: Implement the local-only JD extension parser and scheduler

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/service-worker.js`
- Create: `extension/content/jd-parser.js`
- Create: `extension/content/jd-content.js`
- Create: `extension/test/jd-parser.test.mjs`
- Create: `tests/fixtures/jd_account_visible.html`

**Interfaces:**
- `parseJdPage(text: string, url: string): { status, finalPrice, listPrice, promotionText, deliveryRegion, reason }`.
- Content script sends `{type: "JD_PAGE_RESULT", result}` to the service worker.
- Service worker fetches only `http://localhost:8000/api/browser-watches?platform=jd` and posts only parser results to `http://localhost:8000/api/browser-quotes`.

- [ ] **Step 1: Write parser tests first**

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseJdPage } from '../content/jd-parser.js';

test('extracts explicit estimated final price', () => {
  const result = parseJdPage('配送至 上海 促销 满10000减500 预计到手价 ¥28499.00', 'https://item.jd.com/2.html');
  assert.deepEqual(result, {
    status: 'available', finalPrice: '28499.00', listPrice: null,
    promotionText: '满10000减500', deliveryRegion: '上海', reason: null,
  });
});

test('pauses on an account-abnormal page', () => {
  assert.equal(parseJdPage('当前页面异常 请刷新或切换账户', 'https://item.jd.com/2.html').status, 'paused');
});
```

- [ ] **Step 2: Run parser tests to verify they fail**

Run: `node --test extension/test/jd-parser.test.mjs`

Expected: FAIL because the parser module does not exist.

- [ ] **Step 3: Create the manifest with minimum permissions**

```json
{
  "manifest_version": 3,
  "name": "本地券后价助手",
  "version": "0.1.0",
  "permissions": ["alarms", "tabs", "scripting"],
  "host_permissions": ["https://*.jd.com/*", "http://localhost:8000/*"],
  "background": {"service_worker": "service-worker.js", "type": "module"},
  "content_scripts": [{"matches": ["https://*.jd.com/*"], "js": ["content/jd-content.js"], "run_at": "document_idle"}]
}
```

Do not request `cookies`, `webRequest`, `debugger`, `storage`, clipboard, or broad `*://*/*` permissions.

- [ ] **Step 4: Implement parser and service worker**

The parser must inspect only `document.body.innerText`, cap evidence text at 500 characters, and recognize stop signals before price extraction: `当前页面异常`, `请登录`, `滑块`, `验证码`, and `配送至 香港`. Price extraction must only accept text explicitly adjacent to `预计到手价` or `到手价`; a standalone `¥` price yields `unavailable`. The service worker must use one `chrome.alarms` alarm, deduplicate by URL, wait at most 20 seconds for a content result, close its own background tab, and schedule the next run no sooner than 60 minutes. On a paused result it must call the post endpoint once and remove that URL from the current run; it must not retry.

- [ ] **Step 5: Run extension tests**

Run: `node --test extension/test/jd-parser.test.mjs`

Expected: PASS.

### Task 4: Surface account-visible price state in the dashboard

**Files:**
- Modify: `src/camera_tracker/api.py`
- Modify: `src/camera_tracker/web/index.html`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- `GET /api/products/{product_id}/account-price` returns `available`, `final_price`, `promotion_evidence`, `captured_at`, `delivery_region`, and `reason` from the newest `jd_account_visible` result.
- Dashboard function `drawAccountPrice(productId)` renders either a green amount, a neutral unavailable state, or an amber paused state.

- [ ] **Step 1: Write failing API and dashboard assertions**

```python
def test_account_price_endpoint_returns_newest_browser_quote(tmp_path) -> None:
    repository = seeded_account_visible_repository(tmp_path)
    response = TestClient(create_app(repository)).get('/api/products/canon-r5m2/account-price')
    assert response.json()["final_price"] == "28499"
    assert response.json()["available"] is True

def test_dashboard_has_account_visible_coupon_price_card() -> None:
    content = Path('src/camera_tracker/web/index.html').read_text(encoding='utf-8')
    assert '账户可见券后价' in content
    assert 'drawAccountPrice' in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -k account_price tests/test_dashboard.py -q`

Expected: FAIL because the endpoint and renderer do not exist.

- [ ] **Step 3: Implement the endpoint and responsive card**

Use `repository.latest_channel_quotes(product_id, trusted_only=False)` and select platform `jd_account_visible`. Do not calculate a price when no quote exists; instead combine the source-health row into `{available: false, reason: <last_error or "尚未检测到券后价">}`. Insert this card beside the existing metrics, use `escapeHtml` for every browser-provided string, and keep it inside the existing responsive grid.

- [ ] **Step 4: Run focused UI/API tests**

Run: `python -m pytest tests/test_api.py tests/test_dashboard.py -q`

Expected: PASS.

### Task 5: Document, package, and verify the end-to-end flow

**Files:**
- Modify: `README.md`
- Modify: `docker-compose.yml` only if the current localhost binding prevents extension access; otherwise leave unchanged.
- Modify: `docs/acceptance-audit.md`

- [ ] **Step 1: Write the installation and behavior contract**

Add a README section containing these exact user steps:

```text
1. Keep JD on a stable mainland-direct network and log in through normal Chrome.
2. Open chrome://extensions, enable Developer mode, choose Load unpacked, and select this repository's extension folder.
3. In the dashboard add an exact JD SKU URL with adapter browser_jd.
4. Keep Chrome running. The extension checks at most once per hour per product.
5. If the dashboard says paused, open JD yourself and resolve the visible issue; do not export cookies or repeatedly restart the extension.
```

State explicitly that the extension is local-only, does not request Cookie permission, cannot claim coupons/add cart/pay, and treats an absent visible final price as unavailable.

- [ ] **Step 2: Run the complete automated suite**

Run: `python -m pytest -q && node --test extension/test/jd-parser.test.mjs`

Expected: all Python tests pass and both Node parser tests pass.

- [ ] **Step 3: Build and verify the local image**

Run: `$env:DOCKER_BUILDKIT='0'; docker build -t camera-price-tracker-camera-price-tracker .; docker compose up -d --no-build --force-recreate`

Expected: both application and worker containers report `Up`; `curl http://localhost:8000/api/health` returns `{"status":"ok"}`.

- [ ] **Step 4: Perform the manual extension acceptance check**

Load the unpacked extension in normal Chrome, add one exact `browser_jd` watch, and inspect `http://localhost:8000` after the first alarm or a manually-created extension alarm. Verify either an explicit account-visible price/evidence or a paused/unavailable state. Do not invoke checkout or account-recovery controls.

## Plan Self-Review

- Spec coverage: Tasks 1–2 provide safe persistence/API, Task 3 provides low-frequency normal-Chrome monitoring and stop signals, Task 4 makes status visible, and Task 5 covers local installation and end-to-end checks.
- No Cookie/export gap: the manifest forbids the `cookies` permission; API models forbid extra fields; extension code is limited to DOM text and localhost result payloads.
- Type consistency: `BrowserQuoteResult` is defined in Task 1 and consumed by Task 2; parser result field names map to the API model’s snake_case at the content-script bridge.
- Scope: PDD/Taobao and cart checkout are intentionally excluded from this independently testable JD first release.
