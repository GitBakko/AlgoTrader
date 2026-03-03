# MANTIS AI — Scalp Hybrid Strategy Design

**Date**: 2026-03-03
**Status**: Approved
**Author**: Claude + User

---

## Problem Statement

The current swing trading system (1H candles, ML-only signals) is failing catastrophically:

| Metric | Value | Target |
|--------|-------|--------|
| Win Rate | 15.4% | >40% |
| Profit Factor | 0.44 | >1.0 |
| Total P&L | -$600+ | Positive |
| Avg Trade Duration | 53 hours | <2 hours |
| Total Trades | 311 | — |

**Root causes**:
1. ML model (XGBoost 3-class on 1H) predicts worse than random
2. 2× ATR stops on 1H candles expose positions for days
3. Model buys into downtrends despite regime detection

## Solution: Hybrid Scalp + ML Boost

Switch from ML-driven swing trading to **technical indicator scoring on 15-min candles**, with ML as a confirmation/boost layer (not the primary signal).

---

## Architecture

### Signal Flow (New)

```
15-min candle detected
    │
    ├── ScalpScoreStrategy computes score 0-100
    │     ├── EMA Trend (9/21):  20 pts
    │     ├── RSI (14):          18 pts
    │     ├── MACD:              18 pts
    │     ├── Volume:            12 pts
    │     ├── ADX:               18 pts
    │     └── BB Squeeze:        14 pts
    │
    ├── Score < 60 → HOLD (no trade)
    │
    ├── Score 60-74 → entry with 0.5x size
    ├── Score 75-100 → entry with 1.0x size
    │
    └── ML Boost Layer (existing XGBoost)
          ├── ML agrees (same direction, conf > 0.40) → keep size
          ├── ML neutral (HOLD, conf < 0.40) → size × 0.5
          └── ML disagrees (opposite, conf > 0.50) → SKIP trade
```

### ScalpScoreStrategy — Indicator Scoring

| Indicator | Weight | BUY Logic | SELL Logic |
|-----------|--------|-----------|------------|
| **EMA Trend** (9/21) | 20 | EMA9 > EMA21 + positive slope | EMA9 < EMA21 + negative slope |
| **RSI** (14) | 18 | RSI in 30-45 (oversold bounce) | RSI in 55-70 (overbought rejection) |
| **MACD** | 18 | Histogram > 0 + recent crossover | Histogram < 0 + recent crossover |
| **Volume** | 12 | Volume > 1.2× SMA(20) | Volume > 1.2× SMA(20) |
| **ADX** | 18 | ADX > 20 (trend present) | ADX > 20 (trend present) |
| **BB Squeeze** | 14 | BB width < Keltner width + upward breakout | BB width < Keltner width + downward breakout |

**Scoring rules**:
- Each indicator gives 0 to its max weight based on strength
- Partial points for partial conditions (e.g., EMA cross but weak slope = 12/20)
- Direction must be consistent — mixed signals reduce score

### Risk Management Changes

| Parameter | Current (Swing) | New (Scalp) | Rationale |
|-----------|----------------|-------------|-----------|
| SL base multiplier | 2.0 ATR | **1.0 ATR** | Tight stops, cut losses fast |
| SL dynamic range | [1.5, 4.0] | **[0.7, 2.0]** | Proportional scaling |
| TP risk-reward | 2.5 | **2.0** | Achievable on 15-min moves |
| Max risk per trade | 2% | **1%** | More trades, smaller each |
| Max open positions | 5 | **3** | Less simultaneous exposure |
| CB consecutive losses | 8 | **4** | Stop faster on bad streaks |
| TP1 (partial close) | 1:1 RR | **1:1 RR** | Unchanged |
| Trailing stops | 4-phase | **2-phase** | Simplified for scalp speed |

**Trailing stops simplified**:
- Phase 1: Entry → TP1 — fixed SL, no trail
- Phase 2: Beyond TP1 — trail at 0.75 ATR, lock profit

### Paper Loop Changes

| What | Current | New |
|------|---------|-----|
| CHECK_INTERVAL | 300s (5 min) | **60s** (1 min) |
| Candle resolution | `"1h"` | **`"15min"`** (configurable) |
| Signal dedup window | 60s | **900s** (1 candle period) |

### Feature Engineering

No changes to the feature builder itself — all indicators (EMA, RSI, MACD, BB, ADX, ATR, Volume) already work on any timeframe. They'll compute on 15-min candles automatically.

**One adjustment**: Rolling z-score normalization window: 252 → **100** (faster adaptation for shorter timeframe).

### ML Boost Layer

Existing XGBoost models (trained on 1H) kept temporarily as a filter:

```
Technical score >= 60 → generates BUY/SELL signal
  ├─ ML agrees (same direction, confidence > 0.40) → full size (1.0×)
  ├─ ML says HOLD (confidence < 0.40) → half size (0.5×)
  └─ ML disagrees (opposite direction, confidence > 0.50) → SKIP
```

**Note**: Models will be retrained on 15-min candles later. For now, they act as a conservative veto on strong disagreement.

---

## Files to Create

| File | Purpose |
|------|---------|
| `backend/src/strategy/scalp_score_strategy.py` | New ScalpScoreStrategy implementing BaseStrategy |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/src/trading/paper_loop.py` | CHECK_INTERVAL → 60s, candle resolution → configurable, dedup window → 900s |
| `backend/src/risk/risk_manager.py` | SL multiplier 2.0→1.0, TP RR 2.5→2.0, max positions 5→3, sizing tiers |
| `backend/src/risk/stop_manager.py` | Dynamic range [1.5,4.0]→[0.7,2.0] |
| `backend/src/strategy/strategy_router.py` | Route to ScalpScoreStrategy as primary, ML as boost |
| `backend/src/strategy/signal_generator.py` | Add ML boost logic (agree/neutral/disagree) |
| `backend/src/utils/config.py` | New config params (SCALP_CANDLE_RESOLUTION, SCALP_SCORE_THRESHOLD, etc.) |
| `backend/.env` | New default values |

## No Changes

- Frontend (OFF LIMITS per CLAUDE.md)
- Feature builder (works on any timeframe)
- Execution engine
- Circuit breakers (structure unchanged, just stricter params)
- Database schema
- API endpoints

---

## Expected Outcomes

| Metric | Current | Expected | Reasoning |
|--------|---------|----------|-----------|
| Win Rate | 15.4% | 35-45% | Technical signals more reliable than broken ML |
| Avg Duration | 53 hours | 30-90 min | 15-min candles + tight SL |
| Trades/day | ~8 | 20-40 | More opportunities, shorter holds |
| SL hits | 85% of closes | <60% | Tighter stops + better entries |
| Profit Factor | 0.44 | >1.0 | Better WR + maintained RR |

## Risks

1. **Spread costs**: 15-min scalping on Capital.com demo — tight SL may get eaten by spread
2. **Model mismatch**: 1H-trained XGBoost on 15-min data won't be optimal (but it's just a filter)
3. **Overtrading**: More frequent signals may lead to excessive trading
4. **Data availability**: Need sufficient 15-min historical data for proper feature calculation

## Mitigation

1. Min SL distance floor (e.g., 2× spread) to avoid spread-eaten stops
2. ML boost is conservative — only vetoes strong disagreement
3. Circuit breaker at 4 consecutive losses + max 3 positions
4. Use existing historical data download at 15-min resolution (already configured in HISTORICAL_DATA_TIMEFRAMES)
