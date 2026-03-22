# Risk Management & Trade Execution Pipeline — Updated 2026-03-11

## Overview

Complete risk pipeline with 8 profitability improvements deployed. All values updated.

## RISK MANAGER ORCHESTRATION (`risk_manager.py`)

### Pipeline Order
1. Circuit Breaker Checks
2. Max Positions / Exposure Caps
3. Drawdown Limits
4. Stop-Loss Calculation (dynamic, from config)
5. Take-Profit Calculation
6. Correlation Checks
7. Position Sizing (Kelly or fixed-fractional)
8. Equity Curve Filter
9. Multi-Target TP1/TP2

### Current Parameters (Post-Overhaul)

| Component | Parameter | Value | Notes |
|-----------|-----------|-------|-------|
| Stop-Loss | Base Multiplier | 1.5 ATR | Was 1.0, configurable |
| | Dynamic Range | [1.0, 3.0] ATR | Was [0.7, 2.0] |
| | Formula | `base * (0.5 + 0.5 * ratio)` | Vol-adjusted |
| Take-Profit | TP1 | 0.5x risk | Was 1.0x, breakeven level |
| | TP2 | 1.5x risk | Was 2.0x, lock level |
| Position Sizing | Max Risk/Trade | 2% | Unchanged |
| | Confidence Mult | 0.5 to 1.5x | Kelly-adjusted |
| Equity Curve | SMA Window | 20 trades | Unchanged |
| | Reduction Factor | 50% if below SMA | Unchanged |

## TRAILING STOPS 4-PHASE (Updated)

- **INITIAL**: SL at calculated level (1.5x ATR from entry)
- **BREAKEVEN**: When price hits TP1 (0.5R from entry), SL moves to entry
- **TP1_LOCK**: When price hits TP2 (1.5R from entry), SL locks at TP1 level
- **TRAILING**: Beyond TP2, dynamic trailing with ATR * 1.5

Config wired from `get_settings()` in `main.py` lifespan.

## TIME-BASED STOP (P2 — NEW)

In `_check_stop_losses()`:
- Parses `opened_at` ISO string from position
- Calculates `age_hours = (now - opened_at).total_seconds() / 3600`
- Closes if `age_hours >= SCALP_MAX_HOLD_HOURS` (default 12.0)
- Close reason: `TIME_STOP` → normalized to `TIME`

## ASSET PERFORMANCE TRACKER (P7 — NEW)

File: `src/risk/asset_performance_tracker.py`
- `record_trade(epic, pnl)`: Stores (timestamp, pnl) per asset
- `is_excluded(epic)`: Returns (bool, sharpe) — excluded if Sharpe < threshold AND >= min_trades
- Sharpe: `mean/std * sqrt(252)` annualized
- Integrated in `_process_epic()` — checked before ML prediction

Config: `SCALP_ASSET_EXCLUSION_ENABLED`, `_LOOKBACK_DAYS=14`, `_MIN_TRADES=5`, `_SHARPE_THRESHOLD=-0.5`

## CIRCUIT BREAKERS

| Breaker | Threshold | Auto-Reset |
|---------|-----------|-----------|
| DAILY_LOSS | -3% | Manual |
| CONSECUTIVE_LOSSES | 4-8 | Auto on win |
| MAX_POSITIONS | 20 | Auto |
| VOLATILITY_SPIKE | 5.0x baseline | 60min cooldown |
| HEARTBEAT_TIMEOUT | 30s | Auto on heartbeat |
| SLIPPAGE_ANOMALY | avg >0.5% (5-trade) | Manual/60min |

Reset endpoint: `POST /api/trading/reset-risk-state`

## KELLY SIZER

- min_trades: 30 before Kelly activates
- lookback: 100 trades, max_kelly: 25%, half-kelly by default
- **CRITICAL**: Negative Kelly → 50% fixed-fractional fallback (NOT zero/block)
- This prevents deadlock when win rate drops below breakeven

## EXECUTION FLOW (Complete)

```
TradingSignal → RiskManager.check_trade() → RiskCheckResult
  → MinDealSize check (3-level fallback: fresh cache → startup cache → skip)
  → ExecutionEngine.execute_signal()
    → PAPER: instant fill
    → DEMO/LIVE: broker.create_position()
  → Register trailing stop
  → Persist position to DB
  → Log meta-label features
  → Fire alerts (InApp always, others if enabled)
```

## MINDEALSZ 3-LEVEL FALLBACK

1. `_market_info_cache` (fresh, from broker API during trading)
2. `_min_deal_size_cache` (startup + DB-backed via `market_specs` table)
3. None (skip validation, let broker reject)

Pre-fetch: startup loads from DB (instant) → background broker fetch (3s) → seed into loop.
