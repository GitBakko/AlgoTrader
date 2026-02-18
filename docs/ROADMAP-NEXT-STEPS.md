# MANTIS AI - Roadmap & Next Steps

> Current status: P4 complete (2026-02-18). 1136 tests, 0 errors. Production readiness ~99%.
> ML models: 20/20 tradable assets have trained XGBoost models (EURUSD excluded — ATR too small).
> Infrastructure: CI/CD (GitHub Actions), JSON logging, Prometheus/Grafana, security headers, Docker prod override.
> DEMO readiness: partial_close fix, Telegram alerts, AlertManager wired, emergency kill switch, max_total_exposure.

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

- [ ] Switch `EXECUTION_MODE=DEMO` and run 2+ weeks on Capital.com demo
- [ ] Configure Telegram alerts (`ALERT_TELEGRAM_ENABLED=true`)
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
| **P5** | **Live trading (2+ weeks demo first)** | **2+ weeks** | **Revenue generation** | **NEXT** |
