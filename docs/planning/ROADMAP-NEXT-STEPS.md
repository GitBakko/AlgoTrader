# MANTIS AI - Roadmap & Next Steps

> Current status: Phase 22 complete (2026-02-20). ~1191 tests, 0 errors. Production readiness ~99%.
> ML models: 20/20 tradable assets have trained XGBoost models (EURUSD excluded — ATR too small).
> Infrastructure: CI/CD (GitHub Actions), JSON logging, Prometheus/Grafana, security headers, Docker prod override.
> DEMO readiness: partial_close fix, Telegram alerts, AlertManager wired, emergency kill switch, max_total_exposure.
> Trading history: Closed positions persisted to PostgreSQL, performance analytics, dashboard P&L fix.
> UX/UI Polish: Trade Journal notes, CSV export, Light theme, filter bar redesign.
> Trading robustness: MinDealSize pre-fetch & validation, position history dates, broker error parser, Telegram Markdown fix.
> Notification Center: InAppChannel (always-on), bell dropdown, /notifications page, WS real-time push.
> Analytics: Correlation matrix, risk-adjusted metrics (Sharpe/Sortino/Calmar), Performance page, backtest comparison.
> Bug fixes: Timezone mismatch (asyncpg), UNKNOWN toast, duplicate toast, ExecutionEngine DB, broker-closed detection, negative durations.

---

## Recently Completed

### Phase 22 — Analytics & Observability [COMPLETE]

> Correlation matrix, risk-adjusted metrics, performance page, notification preferences, backtest comparison.

- [x] Backend: `GET /api/analytics/correlation-matrix` — Polars-based Pearson correlation for asset returns
- [x] Risk-adjusted metrics in `PositionRepository.get_performance_stats()` — Sharpe, Sortino, Calmar ratios (numpy)
- [x] Frontend: Performance Analytics page (`/performance`) — equity curve, KPI cards, monthly breakdown, drawdown
- [x] Notification preferences: alert type filtering with localStorage persistence
- [x] Dashboard notification widget: last 5 alerts with emoji + relative time
- [x] Backtest comparison view: checkbox select (max 4), lazy-loaded details, side-by-side metrics table
- [x] Settings: alert type toggles (trade_opened, trade_closed, circuit_breaker, drawdown, etc.)

**Bugfix: Negative Position Durations**

- [x] Root cause: broker `createdDate` in CET timezone, `.replace(tzinfo=None)` stripped tz without converting to UTC
- [x] Fix: `.astimezone(timezone.utc)` before `.replace(tzinfo=None)` in `_persist_position_close()`
- [x] Defensive: `max(0, duration)` guard in positions API + `opened_at > closed_at` guards with correction

### Phase 21 — Notification Center [COMPLETE]

> In-app notification system with persistence, WS real-time push, header bell dropdown.

- [x] `notifications` DB table + Alembic migration + `NotificationRepository` CRUD
- [x] `InAppChannel` — always-on AlertManager channel (persists + WS broadcast, independent of `ALERTS_ENABLED`)
- [x] API: `GET/PATCH/DELETE /api/notifications` + `POST /api/notifications/mark-all-read` + `WS /ws/notifications`
- [x] Frontend: `NotificationCenterService` (REST + WS reconnection), header bell dropdown
- [x] Full `/notifications` page with filters (type, read/unread, date range)
- [x] Telegram alert emojis: type-specific `ALERT_EMOJI` + `ALERT_ICON` dicts

### Phase 20 — Trading Robustness [COMPLETE]

> MinDealSize pre-fetch, position history dates, broker error parser, Telegram alert fix.

**MinDealSize Pre-fetch & Validation:**

- [x] `MarketSpec` DB model + Alembic migration (`market_specs` table, unique epic+environment)
- [x] `MarketSpecRepository` — get_by_epic, get_all_for_environment, upsert, bulk_upsert
- [x] `market_spec_prefetch.py` — `prefetch_market_specs()` (batch 5 parallel, 0.6s delay) + `load_market_specs_from_db()`
- [x] Startup integration: instant DB load → background broker pre-fetch → `seed_min_deal_sizes()`
- [x] `PaperTradingLoop._min_deal_size_cache` + 3-level fallback: market_info_cache → min_deal_size_cache → None
- [x] Pre-order validation in `_process_epic()`: rejects orders below minDealSize with structured error
- [x] `get_status()` includes `"min_deal_sizes_cached"` count

**Position History Date Fix:**

- [x] `_persist_position_close()` accepts `opened_at: datetime | None` parameter
- [x] Both callers (`_detect_broker_closed`, `_check_stop_losses`) pass actual `opened_at` from position dict
- [x] Fallback Position creation uses real `opened_at` (handles ISO strings, tz-aware datetimes)
- [x] Frontend: "Aperta" column added to history table

**Broker Error Parser Improvements:**

- [x] Enhanced `error.invalid.size.minvalue` pattern detection in `parse_broker_error()`
- [x] Added Capital.com `errorCode` field extraction from rejection responses
- [x] Enriched rejection error details with order parameters (epic, size, direction, SL, TP)
- [x] Trade Journal: tooltip + inline display for execution failures

**Telegram Alert Fix:**

- [x] `Alert._escape_telegram_md()` escapes `_`, `*`, `` ` ``, `[` for Telegram Markdown v1
- [x] `format_markdown()` applies escaping to title, message, detail keys
- [x] `TelegramChannel.send()` retries as plain text if Markdown rejected by API
- [x] Alert error log bumped from `logger.debug` to `logger.warning`

**Dashboard KPI Enhancements:**

- [x] Win count displayed on Best Trade KPI card
- [x] Loss count displayed on Worst Trade KPI card

### Phase 19 — UX/UI Polish [COMPLETE]

> Trade Journal notes, CSV export, Light theme, filter panel redesign.

**Trade Journal Notes:**

- [x] `TradeJournalNote` DB model + Alembic migration (`trade_journal_notes` table)
- [x] `TradeJournalNoteRepository` — get_by_signal, upsert_note, delete_note, get_all_notes
- [x] API endpoints: `PUT/GET/DELETE /api/trading/signals/notes`
- [x] Frontend: pencil icon per signal, note modal (textarea, 2000 chars max, save/cancel)
- [x] `TradingService.signalNotes` signal + `loadSignalNotes()` / `updateSignalNote()`

**Export CSV:**

- [x] Backend: `GET /api/export/positions/csv` — StreamingResponse with filters (date, epic, close_reason)
- [x] Frontend Trade Journal: client-side CSV from `filteredSignals()` with BOM for Excel
- [x] Frontend Positions (Storico): server-side CSV download via `getBlob()`
- [x] `ApiService.getBlob()` method for binary responses

**Light Theme:**

- [x] `frontend/src/scss/_light-theme.scss` — full `[data-coreui-theme="light"]` variable set
- [x] 9 component SCSS files fixed: replaced hardcoded dark colors with CSS custom properties
- [x] `index.html` loading screen adapts to `prefers-color-scheme: light`
- [x] Auth pages remain dark-only (pragmatic decision)

**Bugfixes (Phase 19 follow-up):**

- [x] Missing Alembic migration for `trade_journal_notes` (manually created — autogenerate was dangerous)
- [x] CoreUI `cFormSelect` → `cSelect` (correct directive selector)
- [x] Trade Journal filter panel redesigned to inline flex layout (matching Positions pattern)
- [x] Defensive try/except on `GET /signals/notes` endpoint

### Phase 18d — Broker-Closed Position Detection [COMPLETE]

> Detect positions closed by Capital.com (SL/TP hit on broker side) and persist them to history.

- [x] `PaperTradingLoop._detect_broker_closed()` — compares positions between iterations
- [x] When a position disappears from broker, infers SL/TP/EXTERNAL from price vs levels
- [x] Persists closure to DB, records in trade history, logs trade event
- [x] Wired into `_run_iteration()` right after position fetch

### Phase 18c — LoadingButtonComponent [COMPLETE]

> Reusable shared component to prevent duplicate API calls from rapid button clicks.

- [x] `LoadingButtonComponent` — inline `<c-spinner>` + disabled state during async operations
- [x] Inputs: `loading`, `disabled`, `color`, `size`, `variant`, `type` + `(clicked)` output
- [x] Integrated in positions close button (tracks `closingDealId` signal per position)
- [x] Integrated in paper trading Start/Stop + EMERGENCY STOP buttons
- [x] Removed manual spinner patterns from `paper-trading.component.ts`

### Phase 18b — Critical Bug Fixes (Timezone + Toast + DB Persistence) [COMPLETE]

> Fixed 4 critical bugs discovered during live DEMO trading on Capital.com.

**Bug 1: Position persistence silently failing (timezone mismatch)**

- **Root cause**: `datetime.now(timezone.utc)` produces timezone-aware datetimes, but PostgreSQL columns are `TIMESTAMP WITHOUT TIME ZONE`. asyncpg strictly rejects the mismatch with `DataError: can't subtract offset-naive and offset-aware datetimes`. All persistence methods caught the exception silently.
- **Fix**: Added `.replace(tzinfo=None)` to all datetime values going into PostgreSQL
- **Files**: `models.py` (16 occurrences), `paper_loop.py` (6), `execution_engine.py` (4), `position_repository.py` (2)

**Bug 2: Toast showing "UNKNOWN UNKNOWN - P&L 0.00"**

- **Root cause**: `execution_engine.close_position()` used `position_tracker.get_position()` which in DEMO mode only checked in-memory `_paper_positions` dict — empty after restart. No fallback to broker API or DB.
- **Fix**: `PositionTracker.get_position()` now queries broker API as fallback in DEMO/LIVE mode. Plus `ExecutionEngine._persist_close_to_db()` resolves epic/direction/pnl from DB.

**Bug 3: Duplicate toasts (3-4 on position close)**

- **Root cause**: Three separate toast sources listened to the same `lastTrade()` signal: (1) `positions.component.ts`, (2) `default-layout.component.ts`, (3) `notification.service.ts`
- **Fix**: Removed toast from `positions.component.ts` and entire `effect()` block from `default-layout.component.ts`. Single source: `NotificationService`.

**Bug 4: ExecutionEngine without DB access in DEMO mode**

- **Root cause**: `main.py` created `ExecutionEngine(broker=broker, mode=mode)` without passing `position_repository`/`trade_repository` (they're request-scoped). Engine had no DB access for closing positions.
- **Fix**: Added `db_session_factory` parameter to `ExecutionEngine`. Creates own sessions per-operation (same pattern as `PaperTradingLoop`). Wired in `main.py` lifespan.

### Phase 18 — Positions History + Performance + P&L Fix [COMPLETE]

> Full closed-positions history, performance analytics, dashboard P&L fix, and position DB persistence.

**Backend — New Endpoints & Queries:**

- [x] `GET /api/positions/closed` — paginated closed positions with filters (date, epic, close_reason)
- [x] `GET /api/trading/performance` — trading performance stats (win rate, profit factor, P&L by asset, equity curve)
- [x] `PositionRepository.get_closed_positions()` — filtered, paginated query with aggregates
- [x] `PositionRepository.get_performance_stats()` — win/loss rates, profit factor, best/worst trade, P&L by epic
- [x] `PositionRepository.get_closed_in_period()` — period-based P&L summation

**Backend — Dashboard P&L Fix:**

- [x] Fix `total_pnl` in `GET /api/dashboard/overview`: now uses `realized_pnl` from DB (sum of closed positions P&L), fallback to `paper_loop._trade_history`
- [x] Fix `GET /api/dashboard/equity-curve`: now uses `position_repo.get_performance_stats()` for cumulative equity curve

**Backend — Position Persistence (Critical Bug Fix):**

- [x] `PaperTradingLoop._persist_position_open()` — saves positions to PostgreSQL when opened
- [x] `PaperTradingLoop._persist_position_close()` — updates positions to CLOSED when SL/TP hit or manual close
- [x] Close reason normalization: `STOP_LOSS_HIT→SL`, `TAKE_PROFIT_HIT→TP`, `TP1_HIT→TP`, `API close request→MANUAL`
- [x] Idempotent open (check existing deal_id), fallback close (create if never persisted)
- [x] Trade records created for both OPEN and CLOSE events

**Frontend — Positions History Tab:**

- [x] Tab-based positions view: "Aperte" (open) + "Storico" (history)
- [x] History tab: filter bar (asset, close_reason, date range), KPI summary (total P&L, win rate, avg win/loss)
- [x] Close reason badges: SL (red), TP (green), MANUAL (cyan), EXTERNAL (amber)
- [x] Pagination support for large position histories
- [x] New models: `ClosedPosition`, `PositionAggregates`, `TradingPerformance`
- [x] `TradingService`: `closedPositions`, `closedAggregates`, `performance` signals + load methods

**Frontend — Dashboard Performance Section:**

- [x] Performance KPI cards: Win Rate, Profit Factor, Total P&L, Best/Worst Trade
- [x] P&L per Asset: horizontal bar visualization (green profit / red loss)
- [x] Performance data loaded from `/api/trading/performance`

### Phase 17a (P0) — Make Real Trading Work [COMPLETE]

- [x] **Log cleanup**: Cleared polluted test data from production logs, added `source` field to all log entries
- [x] **Test isolation**: Conftest auto-redirects TradeLogger singleton to temp dirs
- [x] **Kelly sizing enabled**: `AdaptiveKellySizer()` injected into RiskManager (was `None`)
- [x] **Centralized asset list**: `src/utils/constants.py` — single source of truth for all 21 assets
- [x] **Rate limiter fallback**: Redis -> in-memory graceful degradation
- [x] **Empty file handling**: Log analyzer handles empty JSONL files without crashing
- [x] **Heartbeat fix**: Per-epic heartbeat refresh in paper_loop (21 epics can exceed 30s)
- [x] **Kelly sizer null check**: `_get_kelly_stats()` returns None when kelly_sizer is None
- [x] **State recovery fixes**: 6 bugs fixed (SQL column names, strategy_name, attribute errors)

### Phase 17b (P0) — First Real Paper Trading Session [COMPLETE]

- [x] Downloaded fresh data for all 21 assets (through 2026-02-18)
- [x] Trained NAS100 XGBoost model (was missing) — all 20/20 tradable assets have models
- [x] Fixed NAS100 limited-hours bars/day (5 bars/day vs default 24)
- [x] Fixed max_open_positions: 6 -> 20 for 20-asset coverage
- [x] Fixed EquityCurveFilter attribute name (`_equity_points` not `equity_curve`)
- [x] **2 real trades executed on Capital.com demo**: BTCUSD BUY @$68,406, XAGUSD BUY @$75.75
- [x] Real ML confidence: 0.397-0.751 (variable, calibrated), not fake 0.85
- [x] Risk management verified: SL/TP calculated, correlation guard active, circuit breakers working

---

## P1 — ML Pipeline Hardening [COMPLETE]

- [x] Regime detection fix (PredictionService + RegimeDetector)
- [x] Walk-forward OOS scorecard (20 assets, per-asset thresholds)
- [x] Sentiment & news + macro features (FinBERT, VIX/DXY/10Y)

## P2 — UX/UI Polish [COMPLETE]

- [x] Toast notifications (trade events, circuit breakers, errors)
- [x] Loading skeletons (dashboard, positions, markets)
- [x] Token refresh rotation (7-day, interceptor retry)
- [x] Error interceptor (Italian toasts, exponential backoff)
- [x] Mobile UX (stacked KPI cards, card-based positions)

## P3 — Infrastructure & DevOps [COMPLETE]

- [x] Fixed `pyproject.toml` target versions (py312), removed ta-lib
- [x] Generated `requirements.txt` + `requirements-dev.txt` (pinned from venv)
- [x] CI pipeline: replaced Poetry with pip, added lint jobs (ruff+black), fixed coverage threshold (80%)
- [x] JSON structured logging (`logs/mantis.json.log`, loguru `serialize=True`)
- [x] Request correlation IDs (`X-Request-ID` header, `logger.contextualize`)
- [x] MetricsCollector wired into trading pipeline (signals, executions, predictions, circuit breakers)
- [x] Composite DB indexes migration (`positions(epic,status)`, `signals(epic,generated_at)`)
- [x] Security headers middleware (CSP, X-Frame-Options, HSTS, Permissions-Policy)
- [x] Hardened CORS (`allow_methods`/`allow_headers` explicit lists)
- [x] Prometheus + Grafana in Docker Compose (`--profile monitoring`)
- [x] Production docker-compose override (`docker-compose.prod.yml`)
- [x] Nginx security headers (CSP, Referrer-Policy, Permissions-Policy)
- [x] Archived 8 obsolete docs to `docs/archive/`

---

## P4 — DEMO Trading Readiness [COMPLETE]

- [x] **Fix partial_close() for DEMO/LIVE**: Close-then-reopen pattern (Capital.com has no partial close API)
- [x] **Telegram alert channel**: New `TelegramChannel` class + `TRADE_OPENED`, `TRADE_CLOSED`, `SIGNAL_GENERATED` AlertTypes
- [x] **Wire AlertManager**: TradeLogger hooks fire alerts in DEMO/LIVE mode; `source` field dynamic per execution mode
- [x] **Emergency kill switch**: `POST /api/trading/emergency-stop` endpoint + frontend button with Italian confirmation
- [x] **max_total_exposure risk limit**: Portfolio-level exposure cap in `RiskLimits` (default 1.0 = no cap, backward-compatible)
- [x] All alert code guarded by `ALERTS_ENABLED=false` (default off) + `try/except` wrappers
- [x] 1136 tests passing, 0 failures

---

## P5 — Live Trading (Future)

### Demo Validation

- [x] Switch `EXECUTION_MODE=DEMO` and run on Capital.com demo (in progress)
- [x] Configure Telegram alerts (`ALERT_TELEGRAM_ENABLED=true`) — configured and fixed
- [ ] Monitor partial_close reopen pattern in real market conditions
- [ ] Test latency, slippage, order rejections
- [ ] Tune `MAX_TOTAL_EXPOSURE` (start at 0.30 = 30% of equity)

### Live Preparation

- [ ] 0.5% risk per trade, gradual increase based on demo performance
- [ ] Review all circuit breaker thresholds for live conditions
- [ ] Emergency kill switch stress test
- [ ] Gradual position size increase based on live Sharpe ratio

### Advanced Models (Research)

- [ ] Evaluate LSTM integration (currently F1 ~0.17 — likely not worth it)
- [ ] Ensemble stacking only if improves Sharpe on OOS backtest

---

## Priority Matrix

| Priority | Phase | Effort | Impact | Status |
|----------|-------|--------|--------|--------|
| P0 | Log cleanup + Kelly + asset centralization | 4h | Baseline | **COMPLETE** |
| P0 | Data download + model training (20 assets) | 6h | Critical | **COMPLETE** |
| P0 | First real paper trading session | 4h | End-to-end validation | **COMPLETE** |
| P1 | Regime detection + scorecard + sentiment | 12h | ML hardening | **COMPLETE** |
| P2 | Toast + skeletons + token refresh + mobile | 13h | UX polish | **COMPLETE** |
| P3 | CI/CD + logging + metrics + security + Docker | 8h | DevOps maturity | **COMPLETE** |
| P4 | DEMO readiness (partial_close, alerts, kill switch) | 6h | DEMO trading | **COMPLETE** |
| -- | Phase 18: Positions history + performance + P&L fix | 8h | Trading analytics | **COMPLETE** |
| -- | Phase 18c: LoadingButton + UX anti-spam | 1h | UX safety | **COMPLETE** |
| -- | Phase 18d: Broker-closed position detection | 1h | Trading integrity | **COMPLETE** |
| -- | Phase 19: UX/UI Polish (notes, CSV, light theme) | 6h | User experience | **COMPLETE** |
| -- | Phase 20: Trading Robustness (minDealSize, dates, Telegram) | 4h | Trading integrity | **COMPLETE** |
| -- | Phase 21: Notification Center (InApp, bell, WS, /notifications) | 6h | User experience | **COMPLETE** |
| -- | Phase 22: Analytics & Observability (metrics, performance, comparison) | 4h | Trading analytics | **COMPLETE** |
| **P5** | **Live trading (2+ weeks demo first)** | **2+ weeks** | **Revenue generation** | **NEXT** |
