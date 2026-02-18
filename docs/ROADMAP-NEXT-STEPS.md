# MANTIS AI - Roadmap & Next Steps

> Current status: P2 complete. 1110 tests, 0 errors. Production readiness ~98%.
> ML models: 20/20 tradable assets have trained XGBoost models (EURUSD excluded — ATR too small).

---

## Recently Completed

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

### P1 Step 7 — Regime Detection Fix [COMPLETE]

- [x] Fixed `PredictionService.get_market_data()`: added `regime` and `rsi` to returned dict
- [x] Increased `limit=30` -> `limit=300` for EMA-50 stabilization
- [x] Added `RegimeDetector().detect(df)` call in prediction pipeline
- [x] Paper loop now logs regime per asset (`trending_up`, `trending_down`, `ranging`)
- [x] `_regime_counts` tracking + `regime_distribution` in `get_status()`
- [x] 2 new tests for regime/rsi in market data

### P1 Step 6 — Walk-Forward OOS Scorecard [COMPLETE]

- [x] Created `backend/src/backtest/scorecard.py`: `WalkForwardResult`, `AssetScorecard` dataclasses
- [x] Created `backend/scripts/batch_oos_scorecard.py`: batch runner for all 20 assets
- [x] Decision framework: KEEP / REVIEW / EXCLUDE based on 6 criteria (Sharpe, win rate, max DD, MC p-value, risk of ruin, total trades)
- [x] Refactored `walk_forward_backtest.py`: 9 -> 20 assets, returns `WalkForwardResult`
- [x] `StrategyManager.from_optimal_thresholds()`: loads per-asset thresholds from `optimal_thresholds.json`
- [x] Wired in `dependencies.py` as default factory
- [x] 16 new tests for scorecard + strategy manager

### P1 Step 8 — Sentiment & News + Macro Features [COMPLETE]

- [x] Created `backend/src/external/ticker_mapping.py`: epic -> Finnhub/Marketaux mapping for all 20 assets
- [x] Fixed `asyncio.run()` bug in `builder.py`: separated async fetch from sync application
- [x] Tier-based sentiment: Tier 1 (NVDA/TSLA) = 5 features, Tier 2 (all others) = `news_sentiment_avg` + 4 placeholders
- [x] Created `backend/src/external/macro_client.py`: VIX/DXY/10Y yield via yfinance with Parquet caching
- [x] Macro features via asof join: 6 daily columns aligned to hourly bars (backward strategy)
- [x] Fixed `train_sentiment_models.py`: `save_model()` now constructs proper `ModelMetadata` objects
- [x] 29 new tests (ticker_mapping, macro_client, builder sentiment/macro integration)

---

## P2 — UX/UI Polish [COMPLETE]

### Toast Notifications

- [x] Trade executed, circuit breaker activated, SL/TP hit, broker error
- [x] Integrate with WebSocket trade events (`connectTrades()` + `effect()`)

### Loading Skeletons

- [x] Dashboard: skeleton cards for KPI, skeleton price blocks
- [x] Positions: skeleton table rows
- [x] Markets: skeleton price cards

### Token Refresh

- [x] Refresh token rotation (localStorage, 7-day expiry, RefreshToken model)
- [x] Frontend: intercept 401, refresh token, retry request (BehaviorSubject pattern)
- [x] Backend: `POST /api/auth/refresh` + `POST /api/auth/logout` endpoints

### Error Interceptor

- [x] User-friendly Italian toast messages for 4xx/5xx errors
- [x] Retry with exponential backoff for network errors (max 3)

### Mobile UX

- [x] Stacked KPI cards on mobile
- [x] Card-based position layout on mobile (`d-block d-md-none`)

---

## P3 — Infrastructure & DevOps (Long-term)

### Documentation & Cleanup

- [ ] Archive obsolete docs to `docs/archive/`
- [ ] Create `docs/09-BACKTEST-RESULTS.md` with walk-forward results

### CI/CD & Containerization

- [ ] GitHub Actions pipeline (lint, test, build, deploy)
- [ ] Multi-stage Docker build
- [ ] Pre-commit hooks (ruff, prettier)

### Performance & Monitoring

- [ ] Prometheus metrics endpoint (`GET /metrics`)
- [ ] Structured JSON logging
- [ ] Database composite indexes migration

### Security Hardening

- [ ] HttpOnly cookie auth (replace localStorage JWT)
- [ ] Content Security Policy (CSP) headers
- [ ] CORS strict origin whitelist in production

### Advanced Models (Research)

- [ ] Evaluate LSTM integration (currently F1 ~0.17 — likely not worth it)
- [ ] Ensemble stacking only if improves Sharpe on OOS backtest

---

## P4 — Toward Live Trading (Future)

### Demo Trading on Capital.com
- [ ] Switch from PAPER to DEMO (real broker, fake money)
- [ ] Test latency, slippage, order rejections
- [ ] Minimum 2 weeks profitable demo trading

### Live Preparation
- [ ] 0.5% risk per trade, 5% max total exposure
- [ ] Email/Slack alerts for every trade and circuit breaker
- [ ] Emergency kill switch (frontend + API)
- [ ] Gradual position size increase based on live performance

---

## Priority Matrix

| Priority | Phase | Effort | Impact | Status |
|----------|-------|--------|--------|--------|
| P0 | Log cleanup + Kelly + asset centralization | 4h | Baseline | **COMPLETE** |
| P0 | Data download + model training (20 assets) | 6h | Critical | **COMPLETE** |
| P0 | First real paper trading session | 4h | End-to-end validation | **COMPLETE** |
| P1 | Regime detection fix | 1h | Activates dormant pipeline | **COMPLETE** |
| P1 | Walk-forward OOS scorecard | 3h+4h run | Per-asset thresholds | **COMPLETE** |
| P1 | Sentiment + macro features | 4h+4h val | +10 ML features | **COMPLETE** |
| P2 | Toast + skeletons + mobile UX | 8h | UX polish | **COMPLETE** |
| P2 | Token refresh + error interceptor | 5h | UX reliability | **COMPLETE** |
| **P3** | **CI/CD + Docker + monitoring** | **1 week** | **DevOps maturity** | **NEXT** |
| P4 | Demo -> live trading | 2+ weeks | Revenue generation | FUTURE |
