# MANTIS AI — CURRENT TRADING ARCHITECTURE (Updated 2026-03-11)

## STATUS: Profitability Overhaul COMPLETE, DEMO Trading Active

All 8 profitability improvements deployed. Monitoring for 200+ trades.

## MAIN LOOP & EXECUTION FLOW

**Paper Trading Loop** (`backend/src/trading/paper_loop.py`)
- **Check Interval**: 60s (scalp mode)
- Checks every 60s for new 15-min candles
- Full pipeline: ML prediction → ScalpScore → Risk check → Execute

**Main Iteration Flow** (`_run_iteration()`):
1. Circuit breaker heartbeat
2. Fetch positions async (10s timeout)
3. Detect broker-closed positions
4. Update trailing stops
5. Check stop losses (includes TIME STOP at 12h)
6. Early exit if max positions reached
7. For each epic with new candle:
   - Asset exclusion check (P7: 14-day Sharpe < -0.5)
   - Market hours check
   - ML Prediction
   - Get market data (indicators)
   - ScalpScore Strategy → TradingSignal
   - Risk check
   - MinDealSize validation
   - Execute signal
   - Log meta-label features (P8a)
   - Persist state & alerts

## SCALPSCORE CONFLUENCE VOTING (Primary Strategy)

**6 Vote Groups** (each ±1 or 0):
1. **EMA**: EMA(8) vs EMA(21) cross
2. **RSI**: Overbought/oversold (>70 SELL, <30 BUY)
3. **MACD**: Signal line cross
4. **Volume**: OBV trend
5. **ADX**: Trend strength (>25 = trending)
6. **BB/Keltner**: Squeeze + band position

**3-Tier Confluence (P3)**:
- Kill zone (London 7-10, NY 13-16 UTC): 3/6 votes needed
- Chop zone (16-20 UTC): 5/6 votes needed
- Default: 4/6 votes needed

**Gate Filters**:
- VWAP: buy>VWAP, sell<VWAP (rolling 50-bar)
- Session: hard block off-session
- Dead market (P5): ADX<20 AND BB width<20th percentile → block
- HTF (P6): 1H EMA slope opposes → block
- ML advisory: agrees=full conf, disagree=halved conf (no veto)

**Confidence**: confluence/6, then ML modifier, then tiering:
<0.25→rejected, 0.25-0.40→25%, 0.40-0.55→50%, 0.55-0.65→75%, ≥0.65→100%

## RISK MANAGEMENT (Updated Values)

**Stop-Loss (P1)**:
- Base: 1.5x ATR (was 1.0x)
- Dynamic range: [1.0, 3.0] (configurable via `SCALP_DYNAMIC_SL_MIN/MAX`)
- Formula: `base * (0.5 + 0.5 * atr_ratio)`, clamped

**Trailing Stops 4-Phase (P4)**:
- INITIAL → BREAKEVEN at 0.5R (was 1.0R)
- BREAKEVEN → TP1_LOCK at 1.5R (was 2.0R)
- TP1_LOCK → TRAILING (beyond TP2)

**Time Stop (P2)**: Close after 12h (`SCALP_MAX_HOLD_HOURS`), reason: `TIME`

**Circuit Breakers**: Daily loss 3%, consecutive losses 4-8, max 20 positions

**Kelly Sizer**: Negative Kelly → 50% fixed-fractional fallback (prevents deadlock)

**Equity Curve Filter**: Below SMA(20) → 50% size reduction

**Asset Exclusion (P7)**: `AssetPerformanceTracker` — 14-day rolling Sharpe per asset, exclude if < -0.5 with ≥5 trades

## ML MODEL

- XGBoost 3-class (0=SELL, 1=HOLD, 2=BUY)
- ~205 features (technical + sentiment + macro, NO fibonacci/candlestick)
- F1: 0.53-0.61, isotonic calibration
- 20/20 models retrained 2026-03-08 with Optuna
- Auto-retrain: weekly Sun 16:00 UTC
- Advisory only: never blocks trades, only modifies confidence

## META-LABEL FEATURES (P8a)

Logged with each signal for future binary classifier:
`ml_confluence`, `ml_utc_hour`, `ml_adx`, `ml_rsi`, `ml_atr`, `ml_htf_bias`, `ml_regime`

## KEY CONFIG FIELDS (all in `src/utils/config.py`)

| Field | Default | Env Override |
|-------|---------|-------------|
| scalp_sl_multiplier | 1.5 | SCALP_SL_MULTIPLIER |
| scalp_dynamic_sl_min | 1.0 | SCALP_DYNAMIC_SL_MIN |
| scalp_dynamic_sl_max | 3.0 | SCALP_DYNAMIC_SL_MAX |
| scalp_max_hold_hours | 12.0 | SCALP_MAX_HOLD_HOURS |
| scalp_tp1_risk_multiple | 0.5 | SCALP_TP1_RISK_MULTIPLE |
| scalp_tp2_risk_multiple | 1.5 | SCALP_TP2_RISK_MULTIPLE |
| scalp_chop_zone_min_confluence | 5 | SCALP_CHOP_ZONE_MIN_CONFLUENCE |
| scalp_chop_zone_start | 16 | SCALP_CHOP_ZONE_START |
| scalp_chop_zone_end | 20 | SCALP_CHOP_ZONE_END |
| scalp_dead_market_adx | 20.0 | SCALP_DEAD_MARKET_ADX |
| scalp_dead_market_bb_pctile | 20.0 | SCALP_DEAD_MARKET_BB_PCTILE |
| scalp_htf_gate_enabled | True | SCALP_HTF_GATE_ENABLED |
| scalp_asset_exclusion_enabled | True | SCALP_ASSET_EXCLUSION_ENABLED |
| scalp_asset_exclusion_lookback_days | 14 | SCALP_ASSET_EXCLUSION_LOOKBACK_DAYS |
| scalp_asset_exclusion_min_trades | 5 | SCALP_ASSET_EXCLUSION_MIN_TRADES |
| scalp_asset_exclusion_sharpe_threshold | -0.5 | SCALP_ASSET_EXCLUSION_SHARPE_THRESHOLD |

## NEXT STEPS

1. Monitor DEMO for 200+ trades (target: WR>35%, Sharpe>0)
2. P8b-d: Train meta-label binary XGBoost after data collection
3. When metrics OK → Live Trading
