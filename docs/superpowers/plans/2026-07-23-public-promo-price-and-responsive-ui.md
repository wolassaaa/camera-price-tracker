# Public Promo Price and Responsive UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show publicly verifiable promotion prices and make the local dashboard readable at desktop and mobile widths.

**Architecture:** Add a small promotion parser that converts explicit public discounts into normalized quote components without claiming account-specific checkout prices. Keep source adapters responsible for extraction, the existing normalizer responsible for arithmetic, and the dashboard responsible for disclosure. Replace the page's unbounded source list and fixed-width form layout with grouped, responsive CSS grid sections.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, httpx, static HTML/CSS/JavaScript, pytest.

## Global Constraints

- Do not use account Cookie storage, CAPTCHA bypass, checkout automation, or affiliate credentials.
- Persist only publicly verifiable price, discount, source URL, and capture time.
- Mark uncertain promotion eligibility as manual confirmation required; do not use it as a trusted low.
- Keep current public adapters and SQLite migrations backward compatible.
- Support 320px, 768px, and desktop layouts with no horizontal overflow or control overlap.

---

### Task 1: Promotion extraction and normalized price contract

**Files:**
- Create: `src/camera_tracker/adapters/promotion.py`
- Create: `tests/test_promotion_adapter.py`
- Modify: `src/camera_tracker/collector.py`

**Interfaces:**
- Produces: `parse_public_promotion(text: str) -> PublicPromotion | None`.
- Consumes: adapter HTML/text and `normalize_quote(...)`.
- Produces: quote `coupon_discount`, `full_reduction`, `payment_discount`, `final_price`, and `manual_confirmation_required` inputs.

- [ ] **Step 1: Write the failing parser tests**

```python
def test_parse_public_full_reduction() -> None:
    promotion = parse_public_promotion("满10000减500")
    assert promotion.threshold == Decimal("10000")
    assert promotion.discount == Decimal("500")
    assert promotion.requires_account_confirmation is False

def test_parse_account_specific_copy_is_not_trusted() -> None:
    promotion = parse_public_promotion("PLUS会员专享券减500")
    assert promotion.requires_account_confirmation is True
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_promotion_adapter.py -q`

Expected: import failure for `camera_tracker.adapters.promotion`.

- [ ] **Step 3: Implement the minimal parser and collector mapping**

```python
@dataclass(frozen=True)
class PublicPromotion:
    threshold: Decimal | None
    discount: Decimal
    requires_account_confirmation: bool

def parse_public_promotion(text: str) -> PublicPromotion | None:
    match = re.search(r"满\s*(\d+(?:\.\d+)?)\s*减\s*(\d+(?:\.\d+)?)", text)
    if match is None:
        return None
    return PublicPromotion(Decimal(match.group(1)), Decimal(match.group(2)), "会员" in text or "专享" in text)
```

Pass explicit discounts to `normalize_quote`; only apply a threshold discount when the list price meets the threshold.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_promotion_adapter.py tests/test_collector.py -q`

Expected: PASS.

### Task 2: Best-effort public JD and Tmall promotion adapters

**Files:**
- Modify: `src/camera_tracker/adapters/jd.py`
- Create: `src/camera_tracker/adapters/tmall.py`
- Modify: `src/camera_tracker/collector.py`
- Create: `tests/test_tmall_adapter.py`
- Modify: `tests/test_jd_adapter.py`

**Interfaces:**
- Consumes: public JD SKU URL and public Tmall detail URL.
- Produces: `PublicProductQuote` plus explicit promotion text when publicly present.
- Failure behavior: raise `ValueError` containing `public promotion unavailable` for login walls, CAPTCHA pages, or malformed public data.

- [ ] **Step 1: Write failing adapter tests**

```python
def test_tmall_public_payload_parses_base_and_explicit_promotion() -> None:
    quote, promotion = parse_tmall_public_payload(FIXTURE, product_id="canon-r5m2", url=URL)
    assert quote.final_price == Decimal("12999")
    assert promotion.discount == Decimal("500")

def test_tmall_login_wall_is_not_reported_as_price() -> None:
    with pytest.raises(ValueError, match="public promotion unavailable"):
        parse_tmall_public_payload("请登录后继续", product_id="canon-r5m2", url=URL)
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_tmall_adapter.py tests/test_jd_adapter.py -q`

Expected: import failure for `camera_tracker.adapters.tmall`.

- [ ] **Step 3: Implement public-only extraction**

```python
def extract_tmall_item_id(url: str) -> str:
    match = re.search(r"[?&]id=(\d+)", url)
    if match is None:
        raise ValueError("Tmall watch URL must include item id")
    return match.group(1)
```

Fetch only the declared public item page and parse JSON-LD or clearly embedded public price/promotion text. Do not send Cookie, create browser sessions, or retry access challenges. Register `tmall` in `run_watch` and record a normal source failure when no public data is available.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_tmall_adapter.py tests/test_jd_adapter.py tests/test_collector.py -q`

Expected: PASS.

### Task 3: Historical-import metadata and API disclosure

**Files:**
- Modify: `src/camera_tracker/repository.py`
- Modify: `src/camera_tracker/api.py`
- Modify: `src/camera_tracker/adapters/manual_import.py`
- Modify: `tests/test_repository.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- `POST /api/import/csv` accepts optional `captured_at` and `evidence_url` columns.
- `GET /api/products/{product_id}/history` returns only persisted records and preserves capture timestamps.

- [ ] **Step 1: Write failing import test**

```python
def test_csv_import_preserves_public_historical_capture_time(tmp_path) -> None:
    csv = "product_id,platform,shop_name,url,price,condition,market_variant,warranty_type,bundle_type,captured_at\nsony-a1,jd,JD,https://item.jd.com/1.html,9999,new,cn,merchant,body_only,2025-06-18T09:00:00+00:00\n"
    response = TestClient(create_app(SqliteRepository(tmp_path / "tracker.db"))).post("/api/import/csv", content=csv)
    assert response.status_code == 200
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_api.py::test_csv_import_preserves_public_historical_capture_time -q`

Expected: FAIL because the importer ignores `captured_at`.

- [ ] **Step 3: Implement optional timestamp validation**

Parse ISO-8601 `captured_at` when supplied; reject invalid timestamps with 422. Use the supplied timestamp in `repository.record_quote`; otherwise keep current capture time. Store evidence in the existing quote URL and raw snapshot fields.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_api.py tests/test_repository.py -q`

Expected: PASS.

### Task 4: Responsive dashboard and grouped source presentation

**Files:**
- Modify: `src/camera_tracker/web/index.html`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Uses existing `/api/overview`, `/api/sources`, `/api/products/{id}/history`, and comparison endpoints.
- Produces: grouped source details with merchant rows collapsed by default and a promotion-status card for the selected product.

- [ ] **Step 1: Write failing static UI contract tests**

```python
def test_dashboard_has_responsive_grid_and_grouped_sources() -> None:
    content = DASHBOARD.read_text(encoding="utf-8")
    assert "@media (max-width: 900px)" in content
    assert "source-group" in content
    assert "minmax(0," in content
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_dashboard.py::test_dashboard_has_responsive_grid_and_grouped_sources -q`

Expected: FAIL because the current page renders all source rows in one unbounded list.

- [ ] **Step 3: Implement responsive layout and source grouping**

Use CSS variables, `grid-template-columns: repeat(auto-fit, minmax(0, 1fr))`, `overflow-wrap:anywhere`, and a 900px media query that changes forms to one column and makes action buttons full width. In `drawSources`, group `price_com_hk:<merchant>` records under a `<details class="source-group">` element while showing platform health at the top level.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_dashboard.py -q`

Expected: PASS.

### Task 5: Container verification

**Files:**
- Modify: `README.md`
- Test: Docker Compose runtime

- [ ] **Step 1: Document public-promotion limits and historical CSV columns**

Add a concise section stating that public promotions are not personal checkout prices and list `captured_at` for verified historical imports.

- [ ] **Step 2: Run all checks**

Run: `python -m pytest -q; python -m compileall -q src; git diff --check`

Expected: all tests pass.

- [ ] **Step 3: Rebuild and test running containers**

Run: `docker compose up -d --build` followed by `curl.exe -sS -o NUL -w "%{http_code}" http://127.0.0.1:8000/`.

Expected: `200`; manually inspect 320px, 768px, and desktop viewports for horizontal overflow and overlapping controls.
