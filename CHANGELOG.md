# MANTIS AI - Changelog

All notable changes to this project are documented in this file.

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

Last updated: 2026-02-19 (Phase 18d)
