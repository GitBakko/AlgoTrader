# MANTIS AI - Changelog

All notable changes to this project are documented in this file.

---

## [TP1 Lift QW6] - 2026-05-15 - Trailing partial-close lifted from midpoint to 0.70

- **fix(risk)**: `backend/src/risk/trailing_stop_manager.py` — `TrailingStopConfig.tp1_fraction` new field, default 0.70 (was implicit 0.50 hardcoded). `_derive_tp_levels()` now computes TP1 = entry + tp1_fraction × (TP - entry) for BUY (symmetric for SELL) instead of `(tp2 - entry_price) * 0.5`. TP2 unchanged (still = strategy take_profit). Direction-aware fallback to legacy `tp1_risk_multiple` ladder preserved when `take_profit=None` or wrong-sided. Breakeven offset 0.0 + max_ladder_cycles=2 invariants preserved.
- **feat(config)**: new env `TP1_FRACTION` (range 0.1-1.0, default 0.70) in `utils/config.py` (`tp1_fraction` field). Wired into `TrailingStopConfig` at construction time in `api/main.py:251`.
- **test**: `backend/tests/risk/test_trailing_stop_manager.py` updated. Existing midpoint-anchored tests rewritten for 0.70 expected values + 3 new QW6 cases (BUY entry=100/TP=120→TP1=114, SELL entry=100/TP=80→TP1=86, custom tp1_fraction=0.50 reproduces legacy midpoint).
- **expected impact**: effective realized R on winning trades ~1.25 → ~1.75 (with strategy R:R 2.5). Combined with WR ~42% post-other-QW fixes, projected net edge positive vs prior breakeven.
- **tests**: `pytest tests/risk/` 201 passed / 0 failed in 5.52s.

## [Quick Wins QW2+QW7+CONF] - 2026-05-15 - Diagnostic-driven fixes

Three parallel fixes addressing live 41.7% win-rate causes per `analysis:diagnostic-report-full` (AgentDB).

- **QW7 — ADX neutral zone block (15→22)**: `strategy/schemas.py` `adx_ranging_threshold` default lifted 15.0 → 22.0. Signals with ADX in the 15-22 neutral zone now blocked (was permitted, contributed to noisy entries). New env knob `ADX_MIN_THRESHOLD` in `utils/config.py` (`adx_min_threshold` field, default 22.0). Expected: +2-3 pp WR by removing low-trend-strength signals.
- **QW2 — MAX_OPEN_POSITIONS portfolio hard cap (LATENT BUG FIX)**: env `MAX_TOTAL_OPEN_POSITIONS=5` was already declared in `utils/config.py:453` but NEVER WIRED into `RiskLimits` constructor at `api/dependencies.py:190`. `RiskLimits.max_total_open_positions` schema default was 20 → production was running with cap 20, intended 5. Fix: (a) wire `settings.max_total_open_positions` in `dependencies.py:190` + `routers/strategy.py:108` (PUT /risk-limits preserves env value), (b) align `risk/schemas.py:36` default 20→5 as fail-safe. Expected: -concentrated drawdown, +3 pp WR by capping correlated exposure count.
- **CONF — Confidence threshold calibration**: `backend/data/config/optimal_thresholds.json` — 4 assets lifted to safe floor 0.45+ (3-class baseline=0.333). US500 0.30→0.48, TSLA 0.30→0.48, BNBUSD 0.30→0.48 (all were BELOW random baseline), WTIUSD 0.42→0.50 (marginal Sharpe 0.96). Original OOS values preserved in `_min_confidence_oos_value` field for traceability. Expected: +2-3 pp WR by removing noise signals.

Cumulative expected impact: ~7-9 pp lift on live WR (41.7% → 48-51%). Tests: `pytest tests/risk/ tests/strategy/` 509 passed / 8 skipped / 0 fail.

## [Hygiene] - 2026-05-15 - Ruflo integration + maintenance sprint

- **chore(tooling)**: integrate `ruflo` MCP server with safe 3-way merge of project configs (commits `92f5d78`, `170c003`). `ruflo init --force` confirmed to clobber `CLAUDE.md`, `.mcp.json`, `.claude/settings.json` regardless of `--skip-claude`/`--minimal`/`--no-global`/`--preset` flags in both v3.7.0-alpha.14 AND .38 — merge procedure documented in `memory/project_ruflo_integration_2026-05-15.md`.
- **chore(planning)**: sync HANDOFF state + gitignore `.playwright-mcp/`, `openapi_tmp.json`, `*_tmp.json` (commit `3840de9`).
- **ci**: fix `.github/workflows/ci.yml` branch trigger `master` → `main` (default branch renamed 2026-04-23).
- **docs**: refresh CHANGELOG.md with 3 months of post-2026-02-19 work.

## [Entry-Drift Handler] - 2026-05-13 - Stale-candle vs broker-mid drift gate

- **fix(risk)**: `paper_loop` drift handler shifts entry or rejects trade when stale candle diverges from broker mid by configured band (commit `132ea74`). Closes META sub-min TP root cause. Bands 0.10-1/2%.

## [LIVE-Deploy Gate Cleared] - 2026-05-06 - RR floor + Binance plan + clean baseline

- **fix(risk)**: `RiskManager.check_trade` step 4-ter — `MIN_SIGNAL_RR_THRESHOLD=0.40` REJECT floor (no widening). Closes TSLA hard-blocker.
- **feat**: `docs/evolutive/BINANCE_MIGRATION_WAVE_PLAN.md` delivered, replaces Bybit migration plan.
- **test**: pytest baseline cleared 16 → 0 failures; coverage 70.59% > CI 70%. Global autouse disables MR/ML primaries.
- **feat**: trailing ladder cap `max_ladder_cycles=2`; tz residuals fixed; `prediction_service` docstring hardened.

## [BTCUSD Partial-Close Loop Fix] - 2026-05-04 - SL/TP trigger source rule

- **fix(critical)**: `prediction_service.get_market_data().current_price` returns 1h candle close (NOT live mid). Using it as SL/TP trigger source caused BTCUSD partial-close runaway. Hard rule: ONLY `broker.get_market_details().snapshot` for SL/TP triggers.

## [Audit Drawer Overhaul] - 2026-04-30 - Idempotent CLOSE + GOING/TP/SL badge

- **feat**: SignalAuditDrawer Audit/History tabs + outcome badge GOING/TP/SL (commits `1c32dc4`, `6578cc1`, `1cdd48f`, `dea2a29`).
- **fix(critical)**: idempotent CLOSE Trade row — SELECT-then-INSERT on `(position_id, trade_type='CLOSE')` (commit `ce2c3e1`). First writer wins, second caller skips insert but still commits Position update. Prevents duplicate audit rows when v1+v2 close detectors and dealId-rotation paths each fire `_finalize_close` for same disappeared position. DELETE 677 historical duplicates.
- **fix(frontend)**: `livePosition` lookups match by `deal_id` NOT `epic` (post bug `dea2a29` — epic-only matching falsely flagged closed audits as GOING).

## [Forex Pip-Aware Sizing + Reconciler Split + Trailing Anchored + R:R Inversion Fix] - 2026-04-29

- **fix(critical)**: SL/TP paired-pair rule (commit `745f2ee`). When `TradingSignal` carries BOTH `suggested_stop` and `suggested_tp`, `RiskManager.check_trade` MUST use the pair as-is. Production was at R:R 0.13-0.30 due to `min`/`max` flip + unconditional TP override. Restored to strategy-calibrated ≥0.75.
- **fix**: `MIN_NOTIONAL_USD=$200` floor in PositionSizer/KellySizer; `MIN_RISK_AMOUNT_USD=$5` post-sizing floor in `RiskManager.check_trade` step 7-bis via pip-aware `_compute_risk_usd(epic, entry, sl, size)` (USDJPY base / EURUSD quote / non-forex). Cap-blocked path approves at residual risk (`lift_bounded_by_cap=true`) instead of rejecting. Commits `e6efede`, `b9f31ba`, `9723dfc`.
- **fix**: `FOREX_USD_BASE_SIZE_MULTIPLIER=30` cap multiplier for USDJPY/USDCHF/USDCAD — without it, cap blocked at ~14 units producing $0.02 risk per SL hit.
- **feat**: Reconciler split — dedicated 15s asyncio task for `_detect_broker_closed` + `_update_trailing_stops` + `_check_stop_losses` when `RECONCILER_DEDICATED_ENABLED=true` (default). Cuts close-detection lag from 20min → <30s. Commits `5c2e7da`, `10fdd8c`, `9a1f16c`, `5233bbe`.
- **feat**: Trailing strategy-anchored — `TrailingStopManager.register_position` accepts optional `take_profit`. TP1 = midpoint(entry, TP), TP2 = TP (was `risk_multiple × risk_distance`). Without anchor, tight-R:R signals had trailing TP1 BELOW strategy TP. Commits `8288cad`, `971907d`.
- **fix**: `breakeven_offset_pct` default flipped `0.001` → `0.0` (pure breakeven). 0.1% profit lock chopped post-TP1 buffer to sub-spread on tight-stop assets.

## [Phase 0/2/3/5 Evolutive Validation] - 2026-04-28

- **Phase 0 PASS**: walk-forward OOS validation gate; 10 KEEP / 3 REVIEW / 5 EXCLUDE (ICPUSD, NATGAS, EURUSD, DOGUSD, GBPUSD auto-cut).
- **Phase 2 FAIL**: regime gate not productive at current Sharpe/DD; `REGIME_GATE_ENABLED=false`. Detectors saved.
- **Phase 3 PASS**: realistic spreads (ETH 4.2× / BNB 7.5× under-priced fixed). Mean Sharpe 4.35 (-7.8%); BNB hit hardest 3.62→1.95 but still KEEP.
- **Phase 5 PoC FAIL**: PPO concordance ensemble harms Sharpe -54% BTC / -85% SOL. Defer Phase 5-bis until sizing soak + 500K samples + position-aware reward.

## [USDJPY Micro-Position Fix] - 2026-04-27 - Forex sizing floor

- **fix(risk)**: `MR_MIN_TP_PCT` / `MR_MIN_TP_PCT_FOREX` + `MIN_NOTIONAL_USD` floors active (commit `90dd85c`).

## [Paper Trading v2 Cockpit + 60s P&L Snapshot + Logo Service] - 2026-04-27

- **feat**: Paper Trading v2 cockpit revamp shipped (PR #8/9/10/11 stacked on `main`).
- **feat**: 60s P&L snapshot system — `PnlSnapshotScheduler` writes `paper_pnl_snapshots` (global) + `position_pnl_snapshots` (per deal) every 60s + 04:30 UTC prune. Live mid-price via WS quote cache (`broker_ws._quote_listeners` fan-out) → REST `get_market_details(epic).snapshot` → UPL reconstruction. Endpoints: `/api/trading/pnl-history`, `/api/trading/positions/{deal_id}/pnl-history`. Migration `c3d8e9f0a1b2`.
- **feat**: `LogoService.getLogoUrls(epic): string[]` returns static URL chain (no API calls). `EpicLogoComponent` walks chain via `<img onerror>`. Final fallback inline SVG `data:` URI. Cache `mantis-logos-v2`.
- **rule**: "NO MOCK DATA NELLE MASCHERE" invariant — synthetic ramps, in-memory ws-only ring buffers, fake placeholders forbidden. Charts/KPIs must source from persisted backend tables (`paperPnlHistory()`, `positionPnlHistory()[deal_id]`).

## [Style Bible Audit + Dashboard v2 Phase 1-4 + Close-Detection v2 Authoritative] - 2026-04-23..2026-04-25

- **feat**: All 14 frontend pages audited and CONFORMI to `STYLE_BIBLE.md` §3 Top 12 Violazioni (commits per page documented).
- **feat**: Dashboard v2 cockpit — mock fidelity Phase 1-3 (Calmar/DD/Live-P&L/overnight-swap/going-counter, 429-row cascade DB cleanup, commit `25444fd`). Phase 4 — `/performance/delta` + `/swap-accum` endpoints, Win-Rate delta in cockpit, 14 new tests (commit `d1f804a`).
- **feat**: Close-detection v2 promoted authoritative fallback (v1 Strategy 1+2 miss → v2 activity-SoT) + `to_dt` clamp. 6 UNRECONCILED rows backfilled (commit `81062fe`).
- **feat**: Full token layer + SCSS split (`_palette.scss` + themed partials) + `/design-system` route + ~99.7% compliance (master→main rename).
- **feat**: PR #7 persist-close triple-fallback upsert closes pre-close dealId rotation bug (commit `e9b6c2f`).

## [Close-Detection v2 Build] - 2026-04-21..2026-04-22

- **feat**: PR #2 — 3-tier close detection (primary Transaction API with 3 match strategies → deferred 10min retry → UNRECONCILED with pnl=NULL + dedicated alert + CLI recovery). `Position.deal_reference` persisted at open (migration `284b174b7dc0`). Backfill executed on prod DB (4 rows reconciled, 0 UNRECONCILED residual).
- **discovery**: Capital.com emits NEW dealId (pos+1 hex) on TP/SL closes — exact-match fails; use `/history/activity` openPrice match.

## [Critical P&L Bug Resolution] - 2026-03-31

- **fix(critical)**: P&L resolved twice. Use broker `Transaction.size` (TRADE row = realized P&L string) or `Position.upl`. Legacy `(exit-entry)*size` fallback REMOVED. No code path invents P&L.
- **feat**: Correlation Intelligence deployed (3 levels: cross-asset features L1, regime detection L2, dynamic correlation guard L3).
- **feat**: Spread filter `MAX_SPREAD_PCT=15%` blocks high-spread epics (DOGUSD, ETHUSD).

## [Sentiment Pipeline Fix + Sizing Relaxed for DEMO] - 2026-03-20..2026-03-24

- **fix**: SIL sentiment pipeline fix.
- **chore**: 3 risk params relaxed for DEMO trading. MUST revert before LIVE production.
- **fix**: Recurring circuit breaker silent halt issues addressed.

---

## [Phase 18d] - 2026-02-19 - Broker-Closed Position Detection

- **fix**: Detect positions closed by Capital.com (SL/TP hit on broker side) and persist to DB
- `PaperTradingLoop._detect_broker_closed()` compares positions between iterations
- Infers close reason (SL/TP/EXTERNAL) from price vs stop/profit levels
- Wired into `_run_iteration()` right after position fetch

## [Phase 18c] - 2026-02-19 - LoadingButtonComponent

- **feat**: Reusable `<app-loading-button>` shared component (inline spinner + disabled during async)
- Integrated in: positions close, paper trading start/stop, emergency stop buttons
- Prevents duplicate API calls from rapid clicks

## [Phase 18b] - 2026-02-19 - Critical Bug Fixes (DEMO Trading)

- **fix**: Timezone mismatch — `.replace(tzinfo=None)` for all datetimes going to PostgreSQL (asyncpg rejects tz-aware)
- **fix**: Toast showing "UNKNOWN" — `PositionTracker.get_position()` now falls back to broker API in DEMO mode
- **fix**: Duplicate toasts (3-4 on close) — single source via `NotificationService`
- **fix**: `ExecutionEngine` without DB access in DEMO — added `db_session_factory` parameter

## [Phase 18] - 2026-02-19 - Positions History + Performance + P&L Fix

### Backend

- `GET /api/positions/closed` — paginated closed positions with filters (date, epic, close_reason) + aggregates
- `GET /api/trading/performance` — win rate, profit factor, P&L by asset, equity curve
- Dashboard P&L fix: `realized_pnl` from DB (sum of closed positions), not equity delta
- Position persistence: `_persist_position_open()` + `_persist_position_close()` in PaperTradingLoop
- Close reason normalization: `STOP_LOSS_HIT→SL`, `TAKE_PROFIT_HIT→TP`, `MANUAL`, `EXTERNAL`

### Frontend

- Tab-based positions: "Aperte" (open) + "Storico" (history)
- History: filter bar (asset, close_reason, date range), KPI summary, pagination
- Close reason badges: SL (red), TP (green), MANUAL (cyan), EXTERNAL (amber)
- Dashboard performance: KPI cards + P&L per asset horizontal bars

## [P4] - 2026-02-18 - DEMO Trading Readiness

- **feat**: Fix `partial_close()` for DEMO/LIVE — close-then-reopen pattern (Capital.com has no partial close API)
- **feat**: Telegram alert channel + AlertManager wired via TradeLogger hooks
- **feat**: Emergency kill switch `POST /api/trading/emergency-stop` + frontend button
- **feat**: `max_total_exposure` portfolio-level exposure cap in RiskLimits
- All alert code guarded by `ALERTS_ENABLED=false` (default off)

## [P3] - 2026-02-17 - Infrastructure & DevOps

- CI pipeline: pip-based (not Poetry), lint (ruff+black) → test (pytest 80%) → docker build
- JSON structured logging (`logs/mantis.json.log`, loguru `serialize=True`)
- Request correlation IDs (`X-Request-ID` header)
- Prometheus metrics + Grafana dashboards (`docker-compose --profile monitoring`)
- Security headers middleware (CSP, X-Frame-Options, HSTS, Permissions-Policy)
- Hardened CORS, production docker-compose override
- Composite DB indexes migration

## [P2] - 2026-02-16 - UX/UI Polish

- Toast notifications (trade events, circuit breakers, errors) — Italian locale
- Loading skeletons (dashboard, positions, markets) with wave animation
- Token refresh rotation (7-day, interceptor retry with BehaviorSubject pattern)
- Error interceptor (Italian toasts, exponential backoff, configurable retry)
- Mobile UX: bottom nav, stacked KPI cards, card-based positions, 44px touch targets
- Auth pages: split-screen glassmorphism, animated gradients, password strength meter
- Avatar system: upload (drag-drop, 5MB max, 256x256 resize), display in dropdown/profile

## [P1] - 2026-02-16 - ML Pipeline Hardening

- Regime detection fix (PredictionService + RegimeDetector)
- Walk-forward OOS scorecard (20 assets, per-asset thresholds, `optimal_thresholds.json`)
- Sentiment features: FinBERT + Finnhub/Marketaux news (5 features for Tier 1, news for Tier 2)
- Macro features: VIX, DXY, 10Y yield via yfinance (6 features, daily asof-join)

## [Phase 17b] - 2026-02-18 - First Real Paper Trading Session

- Downloaded fresh data for all 21 assets (through 2026-02-18)
- Trained NAS100 XGBoost model — all 20/20 tradable assets have models
- **2 real trades on Capital.com demo**: BTCUSD BUY @$68,406, XAGUSD BUY @$75.75
- Real ML confidence: 0.397-0.751 (calibrated), risk management verified

## [Phase 17a] - 2026-02-17 - Make Real Trading Work (P0)

- Log cleanup, test isolation (conftest auto-redirect to temp dirs)
- Kelly sizing enabled (was `None`), centralized asset list (`constants.py`)
- Rate limiter fallback (Redis → in-memory), heartbeat fix for 21 epics
- State recovery fixes (6 bugs: SQL columns, strategy_name, attribute errors)

## [Phase 14-16] - 2026-02-14 to 2026-02-16

### Phase 16: Best Practices and Documentation

- CLAUDE.md design system (colors, typography, spacing, component patterns)
- Pre-commit hooks, code style enforcement

### Phase 15: UI/UX and Avatar System

- MANTIS AI dark theme refinement (6-level surface elevation)
- Glassmorphism dashboard, glass header, auth page redesign
- Avatar upload component (drag-drop, resize, backend handler)

### Phase 14: State Recovery System

- `StateRecoveryService`: PAPER to PostgreSQL, DEMO/LIVE to Broker API+DB fallback
- Repositories: `TrailingStopRepository`, `RiskStateRepository`, `TradeRepository`
- Exponential backoff retry, auto-persistence hooks, reconciliation on startup

## [Phase 12-13] - 2026-02-14 - Portfolio Expansion + ML Training

### Phase 12: 21-Asset Expansion

- Portfolio expanded from 9 to 21 assets (+133%)
- 6 Crypto, 3 Commodities, 2 Forex, 1 Index added
- 218,724 historical candles downloaded (730 days, 3 timeframes)
- Broker mappings: DOGUSD to DOGEUSD, NATGAS to NATURALGAS, NAS100 to QTEC
- WebSocket: 21/40 subscriptions (52% capacity)

### Phase 13: ML Training (All Assets)

- 11 new XGBoost models trained in 46 minutes (vs 6-8h estimate)
- OOS F1 range: 0.5182 (ICPUSD) to 0.5716 (NATGAS)
- Average OOS F1: 0.5340 (+6.8% above baseline)
- Isotonic calibration: ECE improved 30-64% per asset
- Excluded: EURUSD (OOS -99%), NAS100 (insufficient data at time, later trained)

## [Phase 11-11.5] - 2026-02-14 - UX Enhancements + Monitoring

- News widget, epic selector, market status indicators (open/closed + countdown)
- Smart polling: 12s open, 5min closed — 70% API call reduction
- Structured logging: TradeLogger + LogAnalyzer + 4 monitoring API endpoints
- System Logs page with health score (0-100), signal/trade/risk stats

## [Phase 10] - 2026-02-13 - MANTIS AI Branding

- Rebranded from "AlgoTrader AI" to **MANTIS AI**
- Neon green #39FF14 primary, dark theme #0d1117
- SVG mantis logo, CoreUI CSS variable overrides
- All components: `ChangeDetectionStrategy.OnPush`
- TradingView Lightweight Charts with mantis palette

## [Phase 7-9] - 2026-02-12 - Paper Trading + TRADING MAGNA AI

### Phase 7: Paper Trading Dashboard

- Real-time KPIs, signal history, live position tracking via WebSocket

### Phase 8: TRADING MAGNA AI (15 Improvements)

- Pairs trading (Gold-BTC cointegration)
- 4-phase trailing stop, partial close (TP1 50% / TP2 100%)
- Kelly Criterion sizing, equity curve filter, 6 circuit breakers
- Strategy router (regime-based), candlestick patterns, Fibonacci levels
- Market structure detection, Keltner channels, VWAP bands

### Phase 9: Integration and Coverage

- 865 tests passing, 80% coverage, end-to-end data flow verified

## [Phase 6] - 2026-02-11 - ML Optimization

- XGBoost 3-class (LONG/SHORT/HOLD), Optuna auto-tuning (200 trials)
- Multi-timeframe ensemble (1h + 4h + 1d), isotonic calibration
- Walk-forward OOS: BTCUSD +56% Sharpe 1.8, XAUUSD +13% Sharpe 1.2

## [Phase 1-5] - 2026-02-10 - Foundation

- FastAPI backend, Capital.com REST+WS integration, session management
- PostgreSQL + DuckDB + Redis (all optional, graceful degradation)
- 220+ feature engineering (Polars/numpy, no ta-lib)
- Data pipeline: Parquet storage, multi-timeframe, DuckDB analytics
- Angular 21 + CoreUI frontend scaffold

---

Last updated: 2026-05-15 (Hygiene + Ruflo integration)
