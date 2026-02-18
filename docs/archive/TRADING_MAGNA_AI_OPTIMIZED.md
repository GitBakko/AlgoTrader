# TRADING MAGNA — AI-OPTIMIZED KNOWLEDGE BASE

<role>
You are an expert algorithmic trading systems developer. This document is your core knowledge base.
When the user asks you to develop, backtest, or deploy a trading strategy, you MUST reference the rules,
parameters, and code patterns defined below. Never invent parameters from scratch — always start from
the validated defaults here and adapt to the user's specific requirements.
</role>

<principles>
- Every strategy MUST include: entry_rules, exit_rules, stop_loss, take_profit, position_sizing, filters.
- Every backtest MUST include: realistic slippage, commissions, walk-forward validation, and out-of-sample testing.
- Never deploy a strategy without: ≥200 trades in backtest, positive out-of-sample results, Monte Carlo validation.
- Risk per trade: NEVER exceed 2% of equity. Default: 1%.
- Overfitting is the #1 enemy. Fewer parameters = better. Every parameter must survive ±20% sensitivity test.
- This document covers: Equities, Forex, Crypto. Adapt execution details to the target market.
</principles>

---

## SECTION 1: STRATEGY LIBRARY

Each strategy is defined as a self-contained module with all parameters, rules, and implementation details
an AI needs to generate working code in Python (backtrader, vectorbt, or custom).

---

<strategy id="SCALP-EMA-PULLBACK">
<name>EMA Pullback Scalping</name>
<class>scalping</class>
<markets>forex, crypto, futures</markets>
<timeframe_exec>M1, M5</timeframe_exec>
<timeframe_filter>M15</timeframe_filter>
<holding_period>1-15 candles on exec timeframe</holding_period>
<trades_per_day>10-50</trades_per_day>
<expected_winrate>0.55-0.65</expected_winrate>
<expected_profit_factor>1.3-1.8</expected_profit_factor>

<parameters>
| param           | default | range       | description                        |
|-----------------|---------|-------------|------------------------------------|
| ema_fast        | 9       | [5, 15]     | Fast EMA period on exec TF         |
| ema_slow        | 21      | [15, 30]    | Slow EMA period on exec TF         |
| rsi_period      | 7       | [5, 14]     | RSI period for pullback detection   |
| rsi_oversold    | 40      | [30, 45]    | RSI threshold for long entries      |
| rsi_overbought  | 60      | [55, 70]    | RSI threshold for short entries     |
| atr_period      | 14      | [10, 20]    | ATR period for stop calculation     |
| atr_sl_mult     | 1.5     | [1.0, 2.5]  | ATR multiplier for stop-loss        |
| tp1_rr          | 1.0     | [0.8, 1.5]  | Risk:reward for first target        |
| tp2_rr          | 1.5     | [1.2, 2.5]  | Risk:reward for second target       |
| tp1_close_pct   | 0.50    | [0.30, 0.70]| % of position closed at TP1         |
| time_stop_bars  | 5       | [3, 10]     | Max bars before forced exit          |
| max_spread_pct  | 0.0015  | -           | Max spread allowed (0.15%)           |
</parameters>

<entry_rules>
LONG:
  condition_1: ema_fast(M15) > ema_slow(M15)                          # trend filter
  condition_2: close(exec_tf) pulled back to within 0.3*ATR of ema_fast(exec_tf)  # pullback
  condition_3: RSI(rsi_period, exec_tf) < rsi_oversold                 # temporary oversold
  condition_4: current_candle closes above ema_fast(exec_tf)           # rejection confirmed
  condition_5: spread < max_spread_pct * close                         # liquidity filter
  trigger: ALL conditions met → BUY at candle close

SHORT:
  condition_1: ema_fast(M15) < ema_slow(M15)
  condition_2: close(exec_tf) pulled back to within 0.3*ATR of ema_fast(exec_tf)
  condition_3: RSI(rsi_period, exec_tf) > rsi_overbought
  condition_4: current_candle closes below ema_fast(exec_tf)
  condition_5: spread < max_spread_pct * close
  trigger: ALL conditions met → SELL at candle close
</entry_rules>

<exit_rules>
  tp1: entry ± (atr * atr_sl_mult * tp1_rr) → close tp1_close_pct of position
  tp2: entry ± (atr * atr_sl_mult * tp2_rr) → close remaining position
  stop_loss: entry ∓ (atr * atr_sl_mult)
  time_stop: if bars_since_entry >= time_stop_bars and tp1 not hit → close all at market
  rsi_exit: if RSI crosses opposite extreme (>70 for long, <30 for short) → close all
</exit_rules>

<session_filter>
  forex: only trade London 07:00-10:00 UTC, NY overlap 13:00-16:00 UTC
  crypto: 24/7 but avoid 04:00-08:00 UTC (lowest liquidity)
  futures: first 2 hours after market open, last hour before close
  news_blackout: no new entries 15 min before/after high-impact news events
</session_filter>

<python_implementation>
```python
import backtrader as bt

class ScalpEMAPullback(bt.Strategy):
    params = dict(
        ema_fast=9, ema_slow=21, rsi_period=7,
        rsi_oversold=40, rsi_overbought=60,
        atr_period=14, atr_sl_mult=1.5,
        tp1_rr=1.0, tp2_rr=1.5, tp1_close_pct=0.50,
        time_stop_bars=5, risk_pct=0.01,
    )

    def __init__(self):
        self.ema_f = bt.ind.EMA(self.data.close, period=self.p.ema_fast)
        self.ema_s = bt.ind.EMA(self.data.close, period=self.p.ema_slow)
        self.rsi = bt.ind.RSI(self.data.close, period=self.p.rsi_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.bars_since_entry = 0
        self.entry_price = None
        self.sl_price = None
        self.tp1_price = None
        self.tp1_hit = False

    def next(self):
        if self.position:
            self.bars_since_entry += 1
            self._manage_position()
            return

        # Reset
        self.bars_since_entry = 0
        self.tp1_hit = False

        atr_val = self.atr[0]
        if atr_val <= 0:
            return

        # LONG
        if (self.ema_f[0] > self.ema_s[0]
            and abs(self.data.close[0] - self.ema_f[0]) < 0.3 * atr_val
            and self.rsi[0] < self.p.rsi_oversold
            and self.data.close[0] > self.ema_f[0]):

            risk_amount = self.broker.getvalue() * self.p.risk_pct
            sl_dist = atr_val * self.p.atr_sl_mult
            size = risk_amount / sl_dist
            self.buy(size=size)
            self.entry_price = self.data.close[0]
            self.sl_price = self.entry_price - sl_dist
            self.tp1_price = self.entry_price + sl_dist * self.p.tp1_rr

        # SHORT
        elif (self.ema_f[0] < self.ema_s[0]
              and abs(self.data.close[0] - self.ema_f[0]) < 0.3 * atr_val
              and self.rsi[0] > self.p.rsi_overbought
              and self.data.close[0] < self.ema_f[0]):

            risk_amount = self.broker.getvalue() * self.p.risk_pct
            sl_dist = atr_val * self.p.atr_sl_mult
            size = risk_amount / sl_dist
            self.sell(size=size)
            self.entry_price = self.data.close[0]
            self.sl_price = self.entry_price + sl_dist
            self.tp1_price = self.entry_price - sl_dist * self.p.tp1_rr

    def _manage_position(self):
        pos_size = self.position.size
        is_long = pos_size > 0

        # Stop loss
        if is_long and self.data.close[0] <= self.sl_price:
            self.close()
            return
        if not is_long and self.data.close[0] >= self.sl_price:
            self.close()
            return

        # TP1
        if not self.tp1_hit:
            if is_long and self.data.close[0] >= self.tp1_price:
                self.sell(size=abs(pos_size) * self.p.tp1_close_pct)
                self.sl_price = self.entry_price  # move to breakeven
                self.tp1_hit = True
            elif not is_long and self.data.close[0] <= self.tp1_price:
                self.buy(size=abs(pos_size) * self.p.tp1_close_pct)
                self.sl_price = self.entry_price
                self.tp1_hit = True

        # Time stop
        if self.bars_since_entry >= self.p.time_stop_bars and not self.tp1_hit:
            self.close()
```
</python_implementation>
</strategy>

---

<strategy id="DAY-ORB">
<name>Opening Range Breakout (ORB)</name>
<class>day_trading</class>
<markets>equities, futures, crypto</markets>
<timeframe_exec>M5</timeframe_exec>
<timeframe_filter>D1</timeframe_filter>
<holding_period>30min - 6hours</holding_period>
<trades_per_day>0-2</trades_per_day>
<expected_winrate>0.40-0.50</expected_winrate>
<expected_profit_factor>1.5-2.5</expected_profit_factor>

<parameters>
| param                  | default | range        | description                          |
|------------------------|---------|--------------|--------------------------------------|
| opening_range_minutes  | 30      | [15, 60]     | Duration of opening range            |
| atr_daily_period       | 14      | [10, 20]     | ATR on D1 for range validation       |
| range_min_pct_atr      | 0.15    | [0.10, 0.25] | Min range as % of daily ATR          |
| range_max_pct_atr      | 0.75    | [0.50, 0.90] | Max range as % of daily ATR          |
| volume_mult            | 1.5     | [1.2, 2.5]   | Volume must exceed this × avg vol    |
| entry_buffer_atr       | 0.10    | [0.05, 0.20] | Buffer above/below range for entry   |
| tp1_mult_range         | 1.0     | [0.8, 1.5]   | TP1 = range_width × this             |
| tp2_mult_range         | 2.0     | [1.5, 3.0]   | TP2 = range_width × this             |
| tp1_close_pct          | 0.50    | [0.30, 0.70] | % position closed at TP1             |
| tp2_close_pct          | 0.30    | [0.20, 0.40] | % position closed at TP2             |
| trailing_atr_mult      | 1.0     | [0.8, 1.5]   | Trailing stop for remaining position |
| max_hold_hours         | 6       | [2, 8]       | Force close if still open            |
| close_before_eod_min   | 30      | [15, 60]     | Close N min before session end       |
</parameters>

<entry_rules>
PRE-COMPUTATION (after opening_range_minutes):
  range_high = max(high) during opening range
  range_low  = min(low) during opening range
  range_width = range_high - range_low
  atr_daily = ATR(atr_daily_period) on D1

VALIDATION:
  skip_if: range_width > range_max_pct_atr * atr_daily  # too wide = choppy
  skip_if: range_width < range_min_pct_atr * atr_daily  # too narrow = no vol

LONG:
  condition_1: close > range_high + entry_buffer_atr * atr_daily
  condition_2: volume_current > volume_mult * SMA(volume, 20)
  condition_3: VWAP is rising (VWAP > VWAP_5bars_ago)
  trigger: BUY at range_high + buffer
  stop_loss: range_low

SHORT:
  condition_1: close < range_low - entry_buffer_atr * atr_daily
  condition_2: volume_current > volume_mult * SMA(volume, 20)
  condition_3: VWAP is falling
  trigger: SELL at range_low - buffer
  stop_loss: range_high
</entry_rules>

<exit_rules>
  tp1: entry ± range_width * tp1_mult_range → close tp1_close_pct
  tp2: entry ± range_width * tp2_mult_range → close tp2_close_pct
  trailing: remaining position uses trailing stop at trailing_atr_mult * ATR(14, M5)
  time_exit: if position still open max_hold_hours after entry → close all
  eod_exit: close all positions close_before_eod_min before session end
</exit_rules>
</strategy>

---

<strategy id="DAY-VWAP-REVERSION">
<name>VWAP Standard Deviation Reversion</name>
<class>day_trading, mean_reversion</class>
<markets>equities, futures, forex, crypto</markets>
<timeframe_exec>M5, M15</timeframe_exec>
<holding_period>15min - 4hours</holding_period>
<expected_winrate>0.55-0.65</expected_winrate>
<expected_profit_factor>1.3-2.0</expected_profit_factor>

<parameters>
| param            | default | range       | description                         |
|------------------|---------|-------------|-------------------------------------|
| vwap_sd_entry    | 2.0     | [1.5, 2.5]  | SD bands for entry trigger          |
| vwap_sd_tp       | 0.0     | [-0.5, 0.5] | SD level for take profit (0 = VWAP) |
| rsi_period       | 14      | [10, 21]    | RSI period                          |
| rsi_threshold    | 25      | [20, 35]    | RSI extreme for confirmation        |
| ema_trend_period | 50      | [30, 100]   | EMA on H1 for trend filter          |
| atr_period       | 14      | [10, 20]    | ATR for stop calculation            |
| atr_sl_mult      | 0.5     | [0.3, 1.0]  | Additional ATR beyond the SD band   |
| require_candle   | true    | -           | Require rejection candle pattern     |
</parameters>

<entry_rules>
COMPUTATION:
  vwap = cumulative_VWAP(session)
  vwap_upper_2sd = vwap + vwap_sd_entry * session_std
  vwap_lower_2sd = vwap - vwap_sd_entry * session_std

LONG (mean reversion to VWAP from below):
  condition_1: close touches or pierces vwap_lower_2sd
  condition_2: RSI(rsi_period) < rsi_threshold
  condition_3: close on H1 > EMA(ema_trend_period) on H1  # overall bullish context
  condition_4: if require_candle → candle is hammer, bullish engulfing, or pin bar
  trigger: BUY at candle close

SHORT (mean reversion to VWAP from above):
  condition_1: close touches or pierces vwap_upper_2sd
  condition_2: RSI(rsi_period) > (100 - rsi_threshold)
  condition_3: close on H1 < EMA(ema_trend_period) on H1
  condition_4: if require_candle → candle is shooting star, bearish engulfing
  trigger: SELL at candle close
</entry_rules>

<exit_rules>
  take_profit: VWAP + vwap_sd_tp * session_std (default: VWAP itself)
  stop_loss: beyond entry SD band + atr_sl_mult * ATR
  extended_tp: opposite SD band (1σ) for aggressive targets
</exit_rules>
</strategy>

---

<strategy id="SWING-TREND-PULLBACK">
<name>Trend Pullback with Fibonacci Confluence</name>
<class>swing_trading</class>
<markets>equities, forex, crypto</markets>
<timeframe_exec>D1</timeframe_exec>
<timeframe_filter>W1</timeframe_filter>
<holding_period>2-15 days</holding_period>
<trades_per_month>2-6</trades_per_month>
<expected_winrate>0.45-0.55</expected_winrate>
<expected_profit_factor>1.8-3.0</expected_profit_factor>

<parameters>
| param             | default | range        | description                        |
|-------------------|---------|--------------|------------------------------------|
| ema_fast          | 20      | [10, 30]     | Fast EMA on D1                     |
| ema_mid           | 50      | [30, 80]     | Mid EMA on D1                      |
| ema_slow          | 200     | [150, 250]   | Slow EMA on D1 (structure filter)  |
| fib_zone_upper    | 0.382   | -            | Upper Fibonacci retracement level  |
| fib_zone_lower    | 0.618   | -            | Lower Fibonacci retracement level  |
| min_confluences   | 2       | [2, 4]       | Min supporting signals for entry   |
| atr_period        | 14      | [10, 20]     | ATR period                         |
| sl_fib_level      | 0.786   | [0.707, 0.886]| Fibonacci level for stop-loss     |
| tp1_target        | swing_high | -          | Previous swing high/low            |
| tp2_fib_ext       | 1.272   | [1.0, 1.618] | Fibonacci extension target         |
| trailing_ema      | 20      | [10, 30]     | Close below this EMA → exit trail  |
| max_holding_days  | 15      | [10, 25]     | Max days before forced review      |
</parameters>

<entry_rules>
TREND FILTER:
  strong_uptrend:   ema_fast > ema_mid > ema_slow AND close > ema_fast
  strong_downtrend: ema_fast < ema_mid < ema_slow AND close < ema_fast

PULLBACK ZONE:
  Identify last swing: swing_low → swing_high (for uptrend)
  fib_382 = swing_low + (swing_high - swing_low) * 0.382
  fib_500 = swing_low + (swing_high - swing_low) * 0.500
  fib_618 = swing_low + (swing_high - swing_low) * 0.618
  pullback_zone: price is between fib_618 and fib_382

CONFLUENCE CHECK (must have >= min_confluences of these):
  - price touches EMA(ema_mid)
  - RSI(14) between 40-50 (for longs) or 50-60 (for shorts)
  - MACD histogram turns positive (longs) / negative (shorts)
  - candle pattern: hammer, bullish engulfing, morning star (longs) / inverse (shorts)
  - horizontal support/resistance from prior price action
  - volume declining during pullback, increasing on reversal candle

LONG:
  condition_1: strong_uptrend = true
  condition_2: price is in pullback_zone
  condition_3: confluence_count >= min_confluences
  trigger: BUY at close of confirmation candle on D1

SHORT: mirror conditions with strong_downtrend
</entry_rules>

<exit_rules>
  stop_loss: below fib level sl_fib_level (or below swing low + small buffer)
  tp1: previous swing_high → close 50% of position
  tp2: fibonacci extension tp2_fib_ext → close 30%
  trailing: close below EMA(trailing_ema) on D1 → close remaining 20%
  time_review: at max_holding_days, reassess. Close if not progressing.
</exit_rules>
</strategy>

---

<strategy id="MOMENTUM-DUAL">
<name>Dual Momentum (Absolute + Relative)</name>
<class>momentum, portfolio</class>
<markets>equities_etf, crypto, forex</markets>
<timeframe_exec>D1, W1</timeframe_exec>
<rebalance_frequency>monthly</rebalance_frequency>
<holding_period>1-6 months per asset</holding_period>
<expected_winrate>0.50-0.60</expected_winrate>
<expected_profit_factor>1.5-2.5</expected_profit_factor>

<parameters>
| param                | default | range       | description                          |
|----------------------|---------|-------------|--------------------------------------|
| lookback_absolute    | 252     | [126, 504]  | Bars for absolute momentum (daily)   |
| lookback_relative    | 126     | [63, 252]   | Bars for relative momentum (daily)   |
| top_n                | 5       | [3, 10]     | Number of assets to hold             |
| abs_mom_threshold    | 0.0     | [-0.02, 0.05]| Min absolute momentum to qualify    |
| weight_method        | inv_vol | -           | equal_weight / inv_vol / score_prop  |
| rebalance_days       | 21      | [15, 30]    | Days between rebalances              |
| vol_lookback         | 63      | [21, 126]   | Lookback for inverse vol weighting   |
</parameters>

<entry_rules>
SCORING (computed at each rebalance):
  for each asset in universe:
    return_abs = (close_now / close_N_bars_ago) - 1  where N = lookback_absolute
    return_rel = (close_now / close_M_bars_ago) - 1  where M = lookback_relative
    median_rel = median(return_rel for all assets)
    risk_free_return = annualized_risk_free * (lookback_absolute / 252)

    absolute_momentum = return_abs - risk_free_return
    relative_momentum = return_rel - median_rel
    score = 0.5 * absolute_momentum + 0.5 * relative_momentum

SELECTION:
  step_1: filter → keep only assets where absolute_momentum > abs_mom_threshold
  step_2: rank → sort by score descending
  step_3: select → take top_n assets
  step_4: weight →
    if weight_method == "equal_weight": w = 1/top_n for each
    if weight_method == "inv_vol": w = (1/volatility_i) / sum(1/volatility_j for all selected)
    if weight_method == "score_prop": w = score_i / sum(scores)

CASH RULE:
  if fewer than top_n assets pass the absolute_momentum filter → allocate remainder to cash
  if ALL assets have negative absolute_momentum → go 100% cash
</entry_rules>

<exit_rules>
  rebalance: every rebalance_days, recalculate scores and rotate positions
  crash_exit: if portfolio drawdown > 15% intramonth → move 50% to cash immediately
</exit_rules>

<python_implementation>
```python
import pandas as pd
import numpy as np

def dual_momentum_rebalance(prices_df, risk_free_rate=0.04,
                             lookback_abs=252, lookback_rel=126,
                             top_n=5, abs_threshold=0.0):
    """
    prices_df: DataFrame with DatetimeIndex, columns = asset tickers, values = close prices
    Returns: dict of {ticker: weight} for new allocation
    """
    returns_abs = prices_df.pct_change(lookback_abs).iloc[-1]
    returns_rel = prices_df.pct_change(lookback_rel).iloc[-1]
    rf_adj = risk_free_rate * (lookback_abs / 252)

    abs_momentum = returns_abs - rf_adj
    rel_momentum = returns_rel - returns_rel.median()
    score = 0.5 * abs_momentum + 0.5 * rel_momentum

    # Filter by absolute momentum
    qualified = score[abs_momentum > abs_threshold].sort_values(ascending=False)
    selected = qualified.head(top_n)

    if len(selected) == 0:
        return {"CASH": 1.0}

    # Inverse volatility weighting
    vol = prices_df[selected.index].pct_change().rolling(63).std().iloc[-1]
    inv_vol = 1.0 / vol
    weights = inv_vol / inv_vol.sum()

    allocation = weights.to_dict()
    cash_weight = max(0, 1.0 - sum(allocation.values()))
    if cash_weight > 0.01:
        allocation["CASH"] = cash_weight

    return allocation
```
</python_implementation>
</strategy>

---

<strategy id="MOMENTUM-BREAKOUT-VOL">
<name>Momentum Breakout with Volume Confirmation</name>
<class>momentum, breakout</class>
<markets>equities, forex, crypto, futures</markets>
<timeframe_exec>H1, H4, D1</timeframe_exec>
<holding_period>hours to days (trend-dependent)</holding_period>
<expected_winrate>0.35-0.45</expected_winrate>
<expected_profit_factor>2.0-3.5</expected_profit_factor>

<parameters>
| param              | default | range       | description                       |
|--------------------|---------|-------------|-----------------------------------|
| breakout_period    | 20      | [10, 50]    | Donchian/highest-high lookback    |
| volume_mult        | 2.0     | [1.5, 3.0]  | Volume spike multiplier           |
| adx_period         | 14      | [10, 20]    | ADX period                        |
| adx_threshold      | 25      | [20, 30]    | Min ADX for trend confirmation    |
| roc_period         | 10      | [5, 20]     | Rate of Change period             |
| atr_period         | 14      | [10, 20]    | ATR for trailing stop             |
| trailing_atr_mult  | 2.0     | [1.5, 3.0]  | Trailing stop ATR multiplier      |
| adx_exit_level     | 20      | [15, 25]    | Exit when ADX drops below this    |
</parameters>

<entry_rules>
LONG:
  condition_1: close > highest_high(breakout_period)[1]  # new N-period high (use previous bar's high)
  condition_2: volume > volume_mult * SMA(volume, 20)
  condition_3: ADX(adx_period) > adx_threshold
  condition_4: ROC(roc_period) > 0
  trigger: BUY at close

SHORT:
  condition_1: close < lowest_low(breakout_period)[1]
  condition_2: volume > volume_mult * SMA(volume, 20)
  condition_3: ADX(adx_period) > adx_threshold
  condition_4: ROC(roc_period) < 0
  trigger: SELL at close
</entry_rules>

<exit_rules>
  trailing_stop: chandelier_exit = highest_high(N) - trailing_atr_mult * ATR  (for longs)
  trend_exit: if ADX drops below adx_exit_level → close position
  reversal_exit: if opposite signal triggers → reverse position
  NO fixed take profit — let momentum run with trailing stop only
</exit_rules>
</strategy>

---

<strategy id="MEAN-REV-BB">
<name>Bollinger Bands Mean Reversion</name>
<class>mean_reversion</class>
<markets>equities, forex, crypto</markets>
<timeframe_exec>M15, H1, D1</timeframe_exec>
<holding_period>1-10 bars</holding_period>
<expected_winrate>0.60-0.70</expected_winrate>
<expected_profit_factor>1.2-1.8</expected_profit_factor>

<parameters>
| param          | default | range       | description                       |
|----------------|---------|-------------|-----------------------------------|
| bb_period      | 20      | [15, 30]    | Bollinger Bands period            |
| bb_std         | 2.0     | [1.5, 2.5]  | Standard deviation multiplier     |
| rsi_period     | 14      | [10, 21]    | RSI for oversold/overbought       |
| rsi_os         | 30      | [20, 35]    | RSI oversold level                |
| rsi_ob         | 70      | [65, 80]    | RSI overbought level              |
| adx_period     | 14      | [10, 20]    | ADX to detect ranging market      |
| adx_max        | 20      | [15, 25]    | Max ADX (only trade when below)   |
| atr_period     | 14      | [10, 20]    | ATR for stop                      |
| atr_sl_mult    | 1.0     | [0.5, 1.5]  | SL = band + this × ATR            |
</parameters>

<entry_rules>
CRITICAL FILTER:
  ADX(adx_period) < adx_max  # ONLY trade in ranging/low-trend markets
  IF ADX >= adx_max → NO TRADE (trending market = mean reversion fails)

LONG:
  condition_1: close < lower_BB(bb_period, bb_std)
  condition_2: RSI(rsi_period) < rsi_os
  condition_3: ADX(adx_period) < adx_max
  trigger: BUY at close

SHORT:
  condition_1: close > upper_BB(bb_period, bb_std)
  condition_2: RSI(rsi_period) > rsi_ob
  condition_3: ADX(adx_period) < adx_max
  trigger: SELL at close
</entry_rules>

<exit_rules>
  take_profit: SMA(bb_period) — middle Bollinger Band
  stop_loss: beyond the touched band + atr_sl_mult * ATR
  opposite_band_tp: opposite BB band (aggressive target, optional)
</exit_rules>
</strategy>

---

<strategy id="MEAN-REV-PAIRS">
<name>Z-Score Pairs Trading (Cointegration)</name>
<class>mean_reversion, statistical_arbitrage</class>
<markets>equities, crypto, forex</markets>
<timeframe_exec>H1, D1</timeframe_exec>
<holding_period>1-20 bars</holding_period>
<expected_winrate>0.55-0.65</expected_winrate>
<expected_profit_factor>1.5-2.5</expected_profit_factor>

<parameters>
| param              | default | range       | description                       |
|--------------------|---------|-------------|-----------------------------------|
| lookback           | 60      | [30, 120]   | Rolling window for z-score        |
| entry_z            | 2.0     | [1.5, 2.5]  | Z-score threshold to enter        |
| exit_z             | 0.0     | [-0.5, 0.5] | Z-score threshold to exit (mean)  |
| stop_z             | 3.5     | [3.0, 4.5]  | Z-score threshold for stop-loss   |
| coint_pvalue       | 0.05    | [0.01, 0.10]| Max p-value for cointegration test|
| beta_recalc_period | 60      | [30, 120]   | Rolling period for beta estimation|
| max_holding_bars   | 20      | [10, 40]    | Force exit if spread doesn't revert|
</parameters>

<entry_rules>
PRE-REQUISITES:
  step_1: compute beta = OLS regression slope of asset_A on asset_B (rolling beta_recalc_period)
  step_2: compute spread = price_A - beta * price_B
  step_3: compute z_score = (spread - rolling_mean(spread, lookback)) / rolling_std(spread, lookback)
  step_4: run ADF test on spread → if p_value > coint_pvalue → SKIP THIS PAIR (not cointegrated)

LONG SPREAD (expect spread to increase → buy A, sell B):
  condition_1: z_score < -entry_z
  condition_2: ADF p_value < coint_pvalue (cointegration confirmed)
  trigger: BUY asset_A (notional), SHORT asset_B (notional * beta)

SHORT SPREAD (expect spread to decrease → sell A, buy B):
  condition_1: z_score > +entry_z
  condition_2: ADF p_value < coint_pvalue
  trigger: SHORT asset_A, BUY asset_B (notional * beta)
</entry_rules>

<exit_rules>
  mean_revert: abs(z_score) < exit_z → close both legs
  stop_loss: abs(z_score) > stop_z → close both legs (spread diverging further)
  time_stop: bars_since_entry > max_holding_bars → close both legs
  coint_break: if ADF p_value exceeds coint_pvalue during trade → close (relationship broke down)
</exit_rules>

<python_implementation>
```python
import numpy as np
from statsmodels.tsa.stattools import adfuller
from sklearn.linear_model import LinearRegression

def pairs_trading_signals(prices_a, prices_b, lookback=60, entry_z=2.0,
                           exit_z=0.0, stop_z=3.5, coint_pvalue=0.05):
    """
    Returns DataFrame with columns: z_score, signal (1=long_spread, -1=short_spread, 0=flat)
    """
    signals = np.zeros(len(prices_a))
    z_scores = np.full(len(prices_a), np.nan)
    position = 0  # 0=flat, 1=long_spread, -1=short_spread

    for i in range(lookback, len(prices_a)):
        window_a = prices_a[i-lookback:i].values.reshape(-1, 1)
        window_b = prices_b[i-lookback:i].values.reshape(-1, 1)

        # Rolling beta
        reg = LinearRegression().fit(window_b, window_a)
        beta = reg.coef_[0][0]

        # Spread and z-score
        spread = prices_a.iloc[i-lookback:i].values - beta * prices_b.iloc[i-lookback:i].values
        current_spread = prices_a.iloc[i] - beta * prices_b.iloc[i]
        z = (current_spread - spread.mean()) / spread.std()
        z_scores[i] = z

        # Cointegration check
        adf_result = adfuller(spread, maxlag=1)
        is_cointegrated = adf_result[1] < coint_pvalue

        if not is_cointegrated:
            if position != 0:
                position = 0  # exit if cointegration breaks
        else:
            if position == 0:
                if z < -entry_z:
                    position = 1   # long spread
                elif z > entry_z:
                    position = -1  # short spread
            elif position == 1:
                if z > -exit_z or z > stop_z:
                    position = 0
            elif position == -1:
                if z < exit_z or z < -stop_z:
                    position = 0

        signals[i] = position

    return z_scores, signals
```
</python_implementation>
</strategy>

---

<strategy id="BREAKOUT-DONCHIAN">
<name>Donchian Channel Breakout (Turtle Modernized)</name>
<class>breakout, trend_following</class>
<markets>futures, forex, crypto, equities</markets>
<timeframe_exec>D1</timeframe_exec>
<holding_period>days to weeks</holding_period>
<expected_winrate>0.35-0.45</expected_winrate>
<expected_profit_factor>2.0-4.0</expected_profit_factor>

<parameters>
| param              | default | range       | description                       |
|--------------------|---------|-------------|-----------------------------------|
| entry_period       | 20      | [10, 55]    | Donchian entry channel period     |
| exit_period        | 10      | [5, 20]     | Donchian exit channel period      |
| atr_period         | 20      | [14, 30]    | ATR period                        |
| atr_sl_mult        | 2.0     | [1.5, 3.0]  | ATR multiplier for initial SL     |
| volume_confirm     | true    | -           | Require volume confirmation       |
| max_units_market   | 4       | [2, 6]      | Max pyramiding units per market   |
| max_units_correl   | 10      | [6, 12]     | Max units across correlated mkts  |
| max_units_total    | 20      | [12, 25]    | Max units total portfolio         |
| pyramid_atr_step   | 0.5     | [0.25, 1.0] | Add unit every N × ATR in profit  |
</parameters>

<entry_rules>
LONG:
  condition_1: close > highest_high(entry_period)  # Donchian upper breakout
  condition_2: if volume_confirm → volume > SMA(volume, 20)
  trigger: BUY with unit_size = (equity * 0.01) / (atr * atr_sl_mult * point_value)

SHORT:
  condition_1: close < lowest_low(entry_period)
  condition_2: if volume_confirm → volume > SMA(volume, 20)
  trigger: SELL with same sizing

PYRAMIDING:
  if position is profitable by pyramid_atr_step * ATR → add another unit
  up to max_units_market per market
  each new unit has its own stop at atr_sl_mult * ATR below its entry
</entry_rules>

<exit_rules>
  stop_loss: entry - atr_sl_mult * ATR (each unit has independent stop)
  trailing_exit_long: close < lowest_low(exit_period)  # Donchian lower band
  trailing_exit_short: close > highest_high(exit_period)
  portfolio_limit: if total units >= max_units_total → no new entries
</exit_rules>
</strategy>

---

<strategy id="BREAKOUT-SQUEEZE">
<name>Volatility Squeeze Breakout (BB inside Keltner)</name>
<class>breakout</class>
<markets>equities, forex, crypto, futures</markets>
<timeframe_exec>H1, H4, D1</timeframe_exec>
<holding_period>2-20 bars</holding_period>
<expected_winrate>0.45-0.55</expected_winrate>
<expected_profit_factor>1.5-2.5</expected_profit_factor>

<parameters>
| param              | default | range       | description                       |
|--------------------|---------|-------------|-----------------------------------|
| bb_period          | 20      | [15, 25]    | Bollinger Bands period            |
| bb_std             | 2.0     | [1.5, 2.5]  | BB standard deviation multiplier  |
| kc_period          | 20      | [15, 25]    | Keltner Channel period            |
| kc_atr_mult        | 1.5     | [1.0, 2.0]  | Keltner ATR multiplier            |
| momentum_type      | macd_hist| -          | macd_hist or linear_regression    |
| macd_fast          | 12      | [8, 15]     | MACD fast period                  |
| macd_slow          | 26      | [20, 35]    | MACD slow period                  |
| macd_signal        | 9       | [5, 12]     | MACD signal period                |
| atr_sl_mult        | 2.0     | [1.5, 3.0]  | Stop loss ATR multiplier          |
</parameters>

<entry_rules>
SQUEEZE DETECTION:
  bb_upper = SMA(bb_period) + bb_std * StdDev(bb_period)
  bb_lower = SMA(bb_period) - bb_std * StdDev(bb_period)
  kc_upper = EMA(kc_period) + kc_atr_mult * ATR(kc_period)
  kc_lower = EMA(kc_period) - kc_atr_mult * ATR(kc_period)

  squeeze_on  = bb_upper < kc_upper AND bb_lower > kc_lower  # BB inside KC
  squeeze_off = NOT squeeze_on  # BB expanded outside KC

ENTRY TRIGGER:
  condition_1: squeeze was ON in previous bar(s) AND squeeze just turned OFF
  condition_2_long:  momentum > 0 (MACD histogram positive or LinReg slope > 0)
  condition_2_short: momentum < 0
  trigger_long: BUY at close when squeeze releases with positive momentum
  trigger_short: SELL at close when squeeze releases with negative momentum
</entry_rules>

<exit_rules>
  stop_loss: SMA(bb_period) — middle BB line (conservative) or entry ∓ atr_sl_mult * ATR
  take_profit: 1.5 × pre-squeeze range (range_high - range_low during squeeze)
  trailing: atr_sl_mult * ATR trailing stop after initial move
  momentum_exit: if momentum reverses sign → close position
</exit_rules>
</strategy>

---

<strategy id="SCALP-ORDERBOOK">
<name>Order Book Imbalance Scalping</name>
<class>scalping, order_flow</class>
<markets>crypto, futures</markets>
<timeframe_exec>tick, M1</timeframe_exec>
<holding_period>seconds to minutes</holding_period>
<trades_per_day>20-100</trades_per_day>
<expected_winrate>0.55-0.65</expected_winrate>

<parameters>
| param              | default | range       | description                       |
|--------------------|---------|-------------|-----------------------------------|
| book_depth_levels  | 10      | [5, 20]     | Level 2 depth to analyze          |
| imbalance_ratio    | 3.0     | [2.0, 5.0]  | Bid/Ask volume ratio threshold    |
| delta_window_sec   | 10      | [5, 30]     | Window for cumulative delta       |
| vwap_filter        | true    | -           | Only trade in VWAP direction      |
| sl_ticks           | 3       | [2, 5]      | Stop loss in ticks                |
| tp_ticks           | 5       | [3, 10]     | Take profit in ticks              |
</parameters>

<entry_rules>
LONG:
  condition_1: sum(bid_volume, top book_depth_levels) / sum(ask_volume, top book_depth_levels) > imbalance_ratio
  condition_2: cumulative_delta(delta_window_sec) > 0
  condition_3: if vwap_filter → price > session_VWAP
  trigger: BUY with limit order 1 tick above best bid

SHORT:
  condition_1: sum(ask_volume) / sum(bid_volume) > imbalance_ratio
  condition_2: cumulative_delta(delta_window_sec) < 0
  condition_3: if vwap_filter → price < session_VWAP
  trigger: SELL with limit order 1 tick below best ask
</entry_rules>

<exit_rules>
  stop_loss: sl_ticks from entry
  take_profit: tp_ticks from entry
  time_stop: if not filled within 5 seconds → cancel limit order
</exit_rules>
</strategy>

---

<strategy id="MARKET-MAKING">
<name>Symmetric Market Making with Inventory Skew</name>
<class>market_making</class>
<markets>crypto, futures</markets>
<timeframe_exec>tick (100ms-1s refresh)</timeframe_exec>
<holding_period>continuous (inventory managed)</holding_period>

<parameters>
| param              | default | range       | description                        |
|--------------------|---------|-------------|------------------------------------|
| half_spread_bps    | 5       | [2, 20]     | Half spread in basis points        |
| inventory_max      | 100     | varies      | Max inventory units                |
| gamma              | 0.1     | [0.01, 0.5] | Inventory skew aggressiveness      |
| refresh_ms         | 500     | [100, 2000] | Quote refresh interval             |
| vol_window         | 100     | [50, 500]   | Window for realized vol estimate   |
| vol_spike_mult     | 2.0     | [1.5, 3.0]  | Widen spread when vol > this × avg |
</parameters>

<quoting_logic>
  mid_price = (best_bid + best_ask) / 2
  realized_vol = std(returns, vol_window)
  dynamic_spread = max(half_spread_bps, realized_vol * scaling_factor)

  inventory_skew = gamma * current_inventory * realized_vol
  my_bid = mid_price - dynamic_spread - inventory_skew
  my_ask = mid_price + dynamic_spread - inventory_skew

  NOTE: inventory_skew shifts BOTH bid and ask DOWN when long (to sell more)
        and UP when short (to buy more)

  SAFETY:
    if abs(current_inventory) > inventory_max → cancel orders on the full side
    if realized_vol > vol_spike_mult * avg_vol → widen spread 2x or pull quotes
    if news_event_imminent → pull all quotes
</quoting_logic>
</strategy>

---

## SECTION 2: TECHNICAL ANALYSIS MODULE LIBRARY

<module_usage_guide>
These modules are reusable building blocks. When implementing any strategy, import the relevant
indicator/pattern modules rather than reimplementing from scratch. Each module defines:
- exact calculation
- interpretation rules
- parameters with defaults and valid ranges
- how to use as entry filter, exit signal, or confirmation
</module_usage_guide>

---

<ta_module id="MOVING-AVERAGES">
<types>
| type  | formula_key               | lag    | best_for              | default_periods    |
|-------|---------------------------|--------|-----------------------|--------------------|
| SMA   | arithmetic_mean           | high   | S/R levels, smoothing | 20, 50, 200       |
| EMA   | exponential_weight        | medium | trend following       | 9, 21, 55         |
| DEMA  | 2*EMA - EMA(EMA)          | low    | fast trend detection  | 14, 21            |
| TEMA  | 3*EMA - 3*EMA(EMA) + EMA³| v.low  | scalping signals      | 9, 14             |
| HullMA| WMA(2*WMA(n/2)-WMA(n),√n)| v.low  | smooth + responsive   | 9, 16             |
| KAMA  | adaptive_er_based         | varies | auto-adapting         | er=10,fast=2,s=30 |
| ZLEMA | EMA with lag offset       | ~zero  | zero-lag signals      | 14, 21            |
</types>

<signals>
CROSS: fast_ma crosses above slow_ma → bullish; below → bearish
GOLDEN_CROSS: MA(50) > MA(200) → long-term bullish shift
DEATH_CROSS: MA(50) < MA(200) → long-term bearish shift
MA_RIBBON: 6+ EMAs (8,13,21,34,55,89) all aligned and expanding → strong trend; intertwined → ranging
PRICE_VS_MA200: close > EMA(200) → structural bull bias; close < EMA(200) → structural bear bias
SLOPE: if MA is rising → bullish context; falling → bearish
DYNAMIC_SR: price bouncing off a MA = using it as dynamic support (above) or resistance (below)
</signals>
</ta_module>

---

<ta_module id="ADX">
<calculation>
  +DI = 100 * EMA(+DM, period) / ATR(period)
  -DI = 100 * EMA(-DM, period) / ATR(period)
  DX  = 100 * abs(+DI - -DI) / (+DI + -DI)
  ADX = EMA(DX, period)
</calculation>

<interpretation>
| ADX value | meaning                  | strategy_type          |
|-----------|--------------------------|------------------------|
| < 20      | no trend / ranging       | mean_reversion ONLY    |
| 20-25     | possible trend starting  | prepare trend entries   |
| 25-40     | trending                 | trend_following OK      |
| 40-60     | strong trend             | trend_following STRONG  |
| > 60      | extreme trend (rare)     | avoid contrarian trades |

DIRECTIONAL:
  +DI > -DI with ADX > 25 → confirmed uptrend
  -DI > +DI with ADX > 25 → confirmed downtrend
  ADX rising → trend strengthening
  ADX falling → trend weakening (NOT necessarily reversing)
</interpretation>
</ta_module>

---

<ta_module id="RSI">
<default_period>14</default_period>
<scalping_period>7</scalping_period>
<swing_period>21</swing_period>

<levels>
  overbought: > 70 (standard), > 80 (strong trend)
  oversold:   < 30 (standard), < 20 (strong trend)
  midline:    50 (trend bias separator)
</levels>

<divergences>
  REGULAR_BULLISH:  price makes lower_low,  RSI makes higher_low  → potential bullish reversal
  REGULAR_BEARISH:  price makes higher_high, RSI makes lower_high → potential bearish reversal
  HIDDEN_BULLISH:   price makes higher_low,  RSI makes lower_low  → trend continuation (bullish)
  HIDDEN_BEARISH:   price makes lower_high,  RSI makes higher_high → trend continuation (bearish)

  STRENGTH: regular divergences = reversal signals; hidden divergences = continuation signals
  RELIABILITY: higher timeframe divergences are more reliable than lower timeframe
</divergences>

<failure_swing>
  BULLISH: RSI drops below 30 → rises above X → pulls back (stays above 30) → breaks above X → strong buy
  BEARISH: RSI rises above 70 → drops below X → pulls back (stays below 70) → breaks below X → strong sell
</failure_swing>

<algo_implementation_note>
  To detect divergences algorithmically:
  1. Find local price extremes using pivot detection (lookback=5)
  2. Find corresponding RSI values at those pivot bars
  3. Compare the sequence: if price pivots are descending but RSI pivots are ascending → bullish divergence
  4. Confirm with additional filter (volume, pattern) before trading
</algo_implementation_note>
</ta_module>

---

<ta_module id="MACD">
<parameters>
  standard: fast=12, slow=26, signal=9
  fast_scalping: fast=5, slow=13, signal=6
  slow_swing: fast=19, slow=39, signal=9
</parameters>

<signals>
  SIGNAL_CROSS_BUY:  MACD_line crosses above signal_line
  SIGNAL_CROSS_SELL: MACD_line crosses below signal_line
  ZERO_CROSS_BUY:    MACD_line crosses above 0 (EMA_fast > EMA_slow)
  ZERO_CROSS_SELL:   MACD_line crosses below 0
  HISTOGRAM_EXPANSION: |histogram| increasing → momentum accelerating
  HISTOGRAM_CONTRACTION: |histogram| decreasing → momentum decelerating
  DIVERGENCES: same rules as RSI divergences applied to MACD line or histogram
</signals>
</ta_module>

---

<ta_module id="STOCHASTIC">
<parameters>%K=14, %D=3, smoothing=3</parameters>

<signals>
  BUY:  %K crosses %D from below in zone < 20
  SELL: %K crosses %D from above in zone > 80
  CRITICAL: ONLY use in ranging markets (ADX < 25). In trends, ignore signals against trend direction.
</signals>
</ta_module>

---

<ta_module id="ICHIMOKU">
<parameters>
  standard: tenkan=9, kijun=26, senkou_b=52
  day_trading: tenkan=6, kijun=13, senkou_b=26
  alt_day_trading: tenkan=7, kijun=22, senkou_b=44
  swing: tenkan=12, kijun=24, senkou_b=120
</parameters>

<components>
  tenkan_sen   = (highest_high(tenkan) + lowest_low(tenkan)) / 2
  kijun_sen    = (highest_high(kijun) + lowest_low(kijun)) / 2
  senkou_span_a = (tenkan_sen + kijun_sen) / 2, plotted kijun periods ahead
  senkou_span_b = (highest_high(senkou_b) + lowest_low(senkou_b)) / 2, plotted kijun periods ahead
  chikou_span  = close, plotted kijun periods behind
  cloud = area between senkou_span_a and senkou_span_b
</components>

<strong_buy_signal>
ALL five conditions must be true:
  1. price > cloud (above both senkou spans)
  2. cloud is bullish (senkou_span_a > senkou_span_b) → green cloud
  3. tenkan_sen > kijun_sen
  4. chikou_span > price_of_kijun_periods_ago
  5. price is NOT inside the cloud
If ALL 5 → strong long signal. If 3-4 → moderate. If 1-2 → weak.
STRONG SHORT: all five conditions inverted.
</strong_buy_signal>

<tk_cross>
  tenkan crosses above kijun ABOVE cloud → strong buy
  tenkan crosses above kijun INSIDE cloud → neutral buy
  tenkan crosses above kijun BELOW cloud → weak buy (avoid in conservative systems)
</tk_cross>

<kumo_breakout>
  price breaks above cloud with volume → buy signal
  price breaks below cloud with volume → sell signal
  thinner cloud → easier breakout; thicker cloud → stronger S/R
</kumo_breakout>

<edge_to_edge>
  price enters cloud from one side → target = opposite side of cloud
</edge_to_edge>
</ta_module>

---

<ta_module id="VWAP">
<formula>VWAP = cumulative(price * volume) / cumulative(volume), reset each session</formula>

<bands>
  vwap_1sd = vwap ± 1 * session_standard_deviation
  vwap_2sd = vwap ± 2 * session_standard_deviation
  vwap_3sd = vwap ± 3 * session_standard_deviation
</bands>

<signals>
  BIAS: price > VWAP → intraday bullish; price < VWAP → intraday bearish
  SUPPORT/RESISTANCE: VWAP acts as magnet; price tests VWAP multiple times per session
  MEAN_REVERSION: price at ±2SD → high probability of reverting toward VWAP
  ANCHORED_VWAP: anchor to specific event (earnings, swing point) for institutional cost basis
</signals>
</ta_module>

---

<ta_module id="VOLUME-PROFILE">
<concepts>
  POC  = Point of Control: price level with highest traded volume in period
  VAH  = Value Area High: upper boundary of 70% volume area
  VAL  = Value Area Low: lower boundary of 70% volume area
  HVN  = High Volume Node: cluster of high volume → acts as S/R
  LVN  = Low Volume Node: low volume zone → price moves through quickly
</concepts>

<signals>
  price approaching POC → expect S/R reaction
  price outside Value Area → trending behavior
  breakout above VAH with volume → bullish continuation
  return inside VA after breakout → likely false breakout
  previous session's POC, VAH, VAL → key intraday levels
</signals>
</ta_module>

---

<ta_module id="CANDLESTICK-PATTERNS">
<algo_definitions>
Each pattern is defined with numeric rules for algorithmic detection.

HAMMER:
  body_pct = abs(close - open) / (high - low)
  lower_wick = min(open, close) - low
  upper_wick = high - max(open, close)
  is_hammer = body_pct < 0.30 AND lower_wick > 2 * abs(close - open) AND upper_wick < 0.1 * (high - low)
  context: must appear near support level. Bullish signal.

SHOOTING_STAR:
  is_shooting_star = body_pct < 0.30 AND upper_wick > 2 * abs(close - open) AND lower_wick < 0.1 * (high - low)
  context: must appear near resistance level. Bearish signal.

BULLISH_ENGULFING:
  candle_1: close[1] < open[1]  (bearish candle)
  candle_2: close[0] > open[0]  (bullish candle)
  engulf: open[0] < close[1] AND close[0] > open[1]
  is_bullish_engulfing = all above true

BEARISH_ENGULFING:
  candle_1: close[1] > open[1]
  candle_2: close[0] < open[0]
  engulf: open[0] > close[1] AND close[0] < open[1]

DOJI:
  is_doji = abs(close - open) / (high - low) < 0.05  (body is < 5% of range)
  meaning: indecision. Wait for next candle for direction.

MORNING_STAR:
  candle_1: bearish with large body
  candle_2: small body (doji or spinning top), gaps down
  candle_3: bullish, closes above midpoint of candle_1
  → bullish reversal

EVENING_STAR: mirror of morning star → bearish reversal

IMPLEMENTATION NOTE:
  Always combine candle patterns with context:
  - Support/resistance levels
  - Volume (should be above average on the signal candle)
  - Trend context (reversal patterns at key levels, continuation patterns within trends)
</algo_definitions>
</ta_module>

---

<ta_module id="FIBONACCI">
<retracement_levels>[0.236, 0.382, 0.500, 0.618, 0.786]</retracement_levels>
<extension_levels>[1.000, 1.272, 1.618, 2.000, 2.618]</extension_levels>

<calculation>
  For uptrend retracement (swing_low to swing_high):
    level = swing_high - (swing_high - swing_low) * fib_ratio

  For downtrend retracement (swing_high to swing_low):
    level = swing_low + (swing_high - swing_low) * fib_ratio

  For extension (target from pullback end):
    target = pullback_end + (swing_high - swing_low) * ext_ratio  (for uptrend)
</calculation>

<fibonacci_zones>
  Treat each level as a ZONE, not a line: level ± 0.5% of price
  The 0.618 level is the most significant (golden ratio)
  The 0.500 level is psychological (not true Fibonacci but widely used)
</fibonacci_zones>

<fibonacci_clusters>
  Calculate Fibonacci from multiple swing points simultaneously.
  Where 2+ levels from different swings converge within 0.5% → high-probability S/R zone.
  These clusters are more reliable than single-swing Fibonacci levels.
</fibonacci_clusters>

<algo_swing_detection>
  Use ZigZag indicator or pivot point detection:
    pivot_high: high[i] > high[i-N:i] and high[i] > high[i+1:i+N+1] for N=5
    pivot_low:  low[i] < low[i-N:i] and low[i] < low[i+1:i+N+1]
  Take the most recent significant swing (high-to-low or low-to-high) for Fibonacci calculation.
</algo_swing_detection>
</ta_module>

---

<ta_module id="MARKET-STRUCTURE">
<definitions>
  HIGHER_HIGH (HH): current swing_high > previous swing_high
  HIGHER_LOW  (HL): current swing_low > previous swing_low
  LOWER_HIGH  (LH): current swing_high < previous swing_high
  LOWER_LOW   (LL): current swing_low < previous swing_low

  UPTREND:   sequence of HH + HL
  DOWNTREND: sequence of LH + LL
  RANGE:     alternating, no clear sequence
</definitions>

<key_events>
  BOS (Break of Structure): price breaks the most recent HH (in uptrend) or LL (in downtrend)
    → trend continuation signal
  CHoCH (Change of Character): first opposite break
    → in uptrend: first LL signals potential trend reversal
    → in downtrend: first HH signals potential trend reversal

  FVG (Fair Value Gap): gap between candle[i-2].high and candle[i].low (for bullish FVG)
    → price tends to return to fill these gaps → use as entry zones
  LIQUIDITY_GRAB: price spikes beyond obvious S/R, triggers stops, then reverses
    → occurs at swing highs/lows, round numbers, obvious support/resistance
</key_events>

<algo_implementation>
```python
def detect_structure(highs, lows, lookback=5):
    """Returns list of (index, type) where type is HH, HL, LH, LL"""
    pivots = []

    # Detect pivot highs
    for i in range(lookback, len(highs) - lookback):
        if all(highs[i] > highs[i-j] for j in range(1, lookback+1)) and \
           all(highs[i] > highs[i+j] for j in range(1, lookback+1)):
            pivots.append((i, 'swing_high', highs[i]))

    # Detect pivot lows
    for i in range(lookback, len(lows) - lookback):
        if all(lows[i] < lows[i-j] for j in range(1, lookback+1)) and \
           all(lows[i] < lows[i+j] for j in range(1, lookback+1)):
            pivots.append((i, 'swing_low', lows[i]))

    pivots.sort(key=lambda x: x[0])

    # Classify as HH, HL, LH, LL
    last_high = None
    last_low = None
    classified = []

    for idx, ptype, value in pivots:
        if ptype == 'swing_high':
            if last_high is not None:
                label = 'HH' if value > last_high else 'LH'
            else:
                label = 'SH'  # first swing high
            last_high = value
            classified.append((idx, label, value))
        elif ptype == 'swing_low':
            if last_low is not None:
                label = 'HL' if value > last_low else 'LL'
            else:
                label = 'SL'
            last_low = value
            classified.append((idx, label, value))

    return classified
```
</algo_implementation>
</ta_module>

---

## SECTION 3: RISK MANAGEMENT ENGINE

<risk_module id="POSITION-SIZING">
<methods>
FIXED_FRACTIONAL (recommended default):
  formula: size = (equity * risk_pct) / abs(entry - stop_loss)
  risk_pct: 0.01 (1%) default, NEVER exceed 0.02 (2%)

PERCENT_VOLATILITY:
  formula: size = (equity * risk_pct) / (ATR * atr_multiplier * point_value)
  adapts to current volatility automatically

INVERSE_VOLATILITY (for portfolio):
  formula: weight_i = (1 / vol_i) / sum(1 / vol_j for all assets)
  equalizes risk contribution across assets

FIXED_RATIO (for account growth scaling):
  formula: increase units by 1 when profit >= delta
  delta = initial_unit_cost * desired_ratio
  aggressive for growing accounts, conservative for drawdowns
</methods>

<constraints>
  max_risk_per_trade: 0.02 (2% of equity) — HARD LIMIT, NEVER EXCEED
  max_risk_correlated: 0.06 (6% across correlated positions)
  max_portfolio_risk: 0.20 (20% total portfolio heat)
  max_position_pct: 0.25 (no single position > 25% of equity)
</constraints>
</risk_module>

---

<risk_module id="KELLY-CRITERION">
<formula>
  f_star = (W * R - L) / R
  where:
    W = win_rate (0 to 1)
    L = 1 - W
    R = avg_win / avg_loss
</formula>

<practical_usage>
  NEVER use full Kelly. It causes extreme drawdowns.

  HALF_KELLY:    f = 0.50 * f_star  → standard practice
  QUARTER_KELLY: f = 0.25 * f_star  → conservative
  ADAPTIVE_KELLY: f = f_star * confidence
    confidence = function of:
      - sample_size (higher N → higher confidence, max at N=500+)
      - parameter_stability (rolling W and R variance)
      - market_regime_match (current regime vs regime during estimation)
    confidence range: [0.25, 0.75]

  RECALCULATE: every 50-100 trades on rolling window
  FLOOR: if f < 0 → do not trade this strategy (negative expectancy)
  CAP: f never exceeds 0.25 (25%) regardless of Kelly output
</practical_usage>

<python_implementation>
```python
def adaptive_kelly(trades, fraction=0.5, min_trades=30):
    """
    trades: list of P&L values (positive = win, negative = loss)
    Returns: recommended fraction of equity to risk per trade
    """
    if len(trades) < min_trades:
        return 0.005  # minimum default until enough data

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]

    if not losses or not wins:
        return 0.005

    W = len(wins) / len(trades)
    L = 1 - W
    avg_win = sum(wins) / len(wins)
    avg_loss = abs(sum(losses) / len(losses))
    R = avg_win / avg_loss

    kelly_full = (W * R - L) / R
    kelly_full = max(0, kelly_full)

    # Confidence scaling based on sample size
    confidence = min(1.0, len(trades) / 200)

    result = kelly_full * fraction * confidence
    return min(result, 0.25)  # cap at 25%
```
</python_implementation>
</risk_module>

---

<risk_module id="STOP-LOSS-ENGINEERING">
<types>
| type            | formula                                 | best_for          | pros                  | cons                    |
|-----------------|-----------------------------------------|-------------------|-----------------------|-------------------------|
| fixed           | entry ∓ N pips                          | simplicity        | easy to implement     | ignores volatility      |
| atr_based       | entry ∓ mult * ATR(period)              | all strategies    | adapts to vol         | may be wide in high vol |
| structure       | below swing_low / above swing_high      | swing trading     | respects market       | can be very far         |
| chandelier      | highest_high(N) - mult * ATR(N)         | trend following   | great trailing        | lags in fast reversals  |
| parabolic_sar   | SAR formula (accelerating trail)        | trend following   | tightens over time    | whipsaws in ranges      |
| ema_trail       | close below EMA(N) → exit               | swing/position    | smooth, clear         | slow reaction           |
| keltner_trail   | below lower Keltner band                | trend + vol       | vol-adaptive          | complex                 |
| time_stop       | exit after N bars if target not hit     | scalping/day      | limits opportunity cost| may exit before move    |
</types>

<step_trailing_logic>
  PHASE 1 (entry to TP1): stop at initial level (ATR-based or structure-based)
  PHASE 2 (TP1 hit): move stop to breakeven (entry price)
  PHASE 3 (TP2 hit): move stop to TP1 level
  PHASE 4 (running): trailing stop follows price at fixed ATR distance
</step_trailing_logic>
</risk_module>

---

<risk_module id="DRAWDOWN-MANAGEMENT">
<rules>
  REGIME_DETECTION:
    if realized_vol > 1.5 * historical_avg_vol → HIGH_VOL regime → reduce risk 50%
    if correlation_spike (avg pairwise corr > 0.7) → RISK_OFF → reduce risk 50%
    if drawdown > 0.5 * historical_max_drawdown → CAUTION → reduce risk 50%
    if consecutive_losses > 5 → STREAK → reduce risk 25%

  EQUITY_CURVE_FILTER (meta-strategy):
    equity_ma = SMA(equity_curve, 20_trades)
    if equity > equity_ma → strategy performing → trade normally
    if equity < equity_ma → strategy underperforming → reduce size 50% or pause

  RECOVERY_PROTOCOL:
    after hitting daily loss limit → stop for the day
    resume next day with 50% normal size for first 5 trades
    if 3 of 5 are profitable → resume normal size
    if not → continue at 50% until equity_curve > equity_ma
</rules>

<limits>
  max_daily_loss: 3% of equity → HARD STOP for the day
  max_weekly_loss: 5% of equity → reduce size 50% remainder of week
  max_monthly_loss: 10% of equity → pause strategy, full review required
  max_drawdown_strategy: 25% → consider shutting down strategy
  max_drawdown_portfolio: 20% → emergency risk reduction across all strategies
</limits>
</risk_module>

---

<risk_module id="CIRCUIT-BREAKERS">
<triggers>
  DAILY_LOSS:
    if daily_pnl < -max_daily_loss → STOP all new entries, optionally close all positions
    log_event, alert_via_telegram/email, resume next session

  CONSECUTIVE_LOSSES:
    if consecutive_losses >= 5 → pause 1 hour (intraday) or 1 day (swing)
    reduce size 50% for next 5 trades

  MAX_POSITIONS:
    if open_positions >= max_allowed → reject new entries until a position closes

  SLIPPAGE_ANOMALY:
    if avg_slippage(last_hour) > 2 * historical_avg_slippage → likely liquidity event
    widen acceptable entry prices or pause trading

  HEARTBEAT:
    system must emit heartbeat signal every N seconds
    if no heartbeat for > 30 seconds → close all positions (fail-safe)
    alert administrator immediately

  VOLATILITY_SPIKE:
    if 1min_ATR > 5 * normal_1min_ATR → flash crash / extreme event
    close all positions immediately, pause until volatility normalizes
</triggers>

<python_implementation>
```python
class CircuitBreaker:
    def __init__(self, max_daily_loss_pct=0.03, max_consecutive=5,
                 max_positions=5, heartbeat_timeout=30):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_consecutive = max_consecutive
        self.max_positions = max_positions
        self.heartbeat_timeout = heartbeat_timeout
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.open_positions = 0
        self.last_heartbeat = time.time()
        self.is_halted = False

    def record_trade(self, pnl):
        self.daily_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def can_trade(self, equity):
        if self.is_halted:
            return False, "HALTED"
        if self.daily_pnl < -self.max_daily_loss_pct * equity:
            self.is_halted = True
            return False, "DAILY_LOSS_LIMIT"
        if self.consecutive_losses >= self.max_consecutive:
            return False, "CONSECUTIVE_LOSSES"
        if self.open_positions >= self.max_positions:
            return False, "MAX_POSITIONS"
        if time.time() - self.last_heartbeat > self.heartbeat_timeout:
            self.is_halted = True
            return False, "HEARTBEAT_TIMEOUT"
        return True, "OK"

    def heartbeat(self):
        self.last_heartbeat = time.time()

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.is_halted = False
```
</python_implementation>
</risk_module>

---

<risk_module id="PORTFOLIO-RISK">
<correlation_rules>
  if correlation(asset_A, asset_B) > 0.70 → treat as single position for risk limits
  compute rolling correlation (window = 60 days) — correlations change over time
  max combined risk on correlated positions: 6% of equity
</correlation_rules>

<diversification_formula>
  portfolio_sharpe ≈ avg_strategy_sharpe * sqrt(N / (1 + (N-1) * avg_correlation))
  where N = number of strategies
  IMPLICATION: combine uncorrelated strategies for portfolio-level improvement
  ideal_combination: trend_following + mean_reversion + volatility_trading + carry
</diversification_formula>

<var_calculation>
  VaR_95 = portfolio_value * 1.645 * portfolio_daily_volatility * sqrt(holding_days)
  VaR_99 = portfolio_value * 2.326 * portfolio_daily_volatility * sqrt(holding_days)
  use as daily risk budget: if unrealized_loss approaches VaR_95 → start reducing positions
</var_calculation>
</risk_module>

---

## SECTION 4: INFRASTRUCTURE & IMPLEMENTATION

<infra_module id="SYSTEM-ARCHITECTURE">
<components>
  1. DATA_FEED → receives market data (WebSocket for real-time, REST for historical)
  2. DATA_STORE → persists OHLCV and ticks (SQLite for small, TimescaleDB for large, Parquet for files)
  3. STRATEGY_ENGINE → computes indicators, evaluates rules, generates signals
  4. RISK_MANAGER → validates signals against position limits, drawdown, correlation
  5. ORDER_MANAGEMENT → tracks order lifecycle: pending → submitted → partial → filled / cancelled
  6. EXECUTION_ENGINE → routes orders to broker, handles smart routing, manages slippage
  7. BROKER_API → connects to broker (REST/WebSocket/FIX protocol)
  8. MONITOR_LOG → real-time dashboard, alerting, audit trail, performance tracking
</components>

<data_flow>
  DATA_FEED → DATA_STORE (persist) → STRATEGY_ENGINE (process)
  STRATEGY_ENGINE → signal → RISK_MANAGER → approved/rejected
  RISK_MANAGER (approved) → ORDER_MANAGEMENT → EXECUTION_ENGINE → BROKER_API
  BROKER_API → fill_report → ORDER_MANAGEMENT → MONITOR_LOG
  MONITOR_LOG → alerts → operator (email/telegram/slack)
</data_flow>
</infra_module>

---

<infra_module id="FRAMEWORKS">
<comparison>
| framework       | speed      | ease | live_trading         | best_for                          |
|-----------------|------------|------|----------------------|-----------------------------------|
| backtrader      | medium     | high | yes (IB, Oanda)      | beginners, prototyping, education |
| backtesting.py  | high       | very | no                   | rapid prototyping, quick tests    |
| vectorbt        | very_high  | med  | no                   | massive optimization, research    |
| zipline         | medium     | med  | limited              | ML integration, factor research   |
| nautilus_trader | very_high  | low  | yes (production)     | production HFT, institutional     |
| bt              | medium     | high | no                   | portfolio strategies, allocation  |
| lean (QC)       | high       | med  | yes (multi-broker)   | full pipeline, cloud backtesting  |
| freqtrade       | medium     | high | yes (crypto focused) | crypto bots, community strategies |
</comparison>

<recommendation>
  prototyping: backtrader or backtesting.py
  optimization: vectorbt (can test 100,000+ parameter combos in minutes)
  production: nautilus_trader or lean/QuantConnect
  crypto_specific: freqtrade
</recommendation>
</infra_module>

---

<infra_module id="DATA-SOURCES">
<free>
| source            | assets              | resolution  | python_library        |
|-------------------|---------------------|-------------|-----------------------|
| Yahoo Finance     | stocks, ETFs, idx   | daily       | yfinance              |
| Alpha Vantage     | stocks, forex       | 1min+       | alpha_vantage         |
| Binance API       | crypto              | 1min+, tick | python-binance, ccxt  |
| CoinGecko         | crypto              | daily       | pycoingecko           |
| FRED              | macro/economic      | daily+      | fredapi               |
| Polygon.io (free) | US stocks           | daily       | polygon-api-client    |
| Alpaca (free)     | US stocks           | 1min+       | alpaca-trade-api      |
</free>

<premium>
| source            | assets              | resolution  | notes                      |
|-------------------|---------------------|-------------|----------------------------|
| Interactive Brokers| multi-asset        | tick        | requires funded account    |
| Databento         | futures, stocks     | tick, L2    | institutional grade        |
| Kaiko             | crypto              | tick, L2    | institutional crypto data  |
| Quandl/Nasdaq     | alternative data    | varies      | sentiment, fundamentals    |
| Tiingo            | stocks, crypto      | 1min+       | affordable premium         |
</premium>

<storage_recommendations>
  daily_ohlcv: Parquet files partitioned by symbol (fast, compressed, portable)
  minute_ohlcv: Parquet files partitioned by date
  tick_data: TimescaleDB or InfluxDB (time-series optimized)
  small_projects: SQLite (zero config, single file)

  DATA QUALITY CHECKLIST:
    ✓ check for gaps (weekends, holidays, halts)
    ✓ handle splits and dividends (use adjusted prices)
    ✓ detect outliers (price spike > 10 * ATR → likely bad data)
    ✓ forward-fill small gaps, flag large gaps
    ✓ NEVER use future data in backtest (look-ahead bias)
    ✓ align timestamps across data sources
</storage_recommendations>
</infra_module>

---

<infra_module id="EXECUTION">
<order_types>
  market: immediate execution, accept slippage
  limit: specify price, no slippage but may not fill
  stop: becomes market when trigger hit → use for stop-losses
  stop_limit: becomes limit when trigger hit → safer but may not fill in fast markets
  oco: one-cancels-other → link SL and TP
  bracket: entry + SL + TP as atomic unit
</order_types>

<slippage_modeling>
  FOR BACKTESTING (always include slippage, never assume perfect fills):
    model_1_fixed: slippage = N ticks per trade (simple, conservative)
    model_2_pct: slippage = 0.01% to 0.05% of price (realistic for liquid markets)
    model_3_volume: slippage = f(order_size / avg_volume) — larger orders = more slippage
    model_4_spread: slippage = half_spread (most realistic for market orders)

  RULE: in backtest, use at MINIMUM model_2 (0.02% for stocks, 0.05% for crypto)
  if strategy is profitable only without slippage → IT IS NOT PROFITABLE
</slippage_modeling>

<smart_order_routing>
  FOR LARGE ORDERS (> 1% of avg daily volume):
    TWAP: split into N equal orders at regular time intervals
    VWAP: split proportional to historical volume profile
    ICEBERG: show only small visible quantity in order book
    POV: participate at fixed % of current volume
</smart_order_routing>
</infra_module>

---

<infra_module id="WALK-FORWARD-VALIDATION">
<purpose>
  Prevent overfitting. The #1 reason algo strategies fail in live trading.
  Walk-forward analysis simulates real-world conditions: optimize on past, test on unseen future.
</purpose>

<method>
  STEP 1: Divide historical data into rolling windows:
    |---TRAIN_1---|--TEST_1--|
                 |---TRAIN_2---|--TEST_2--|
                              |---TRAIN_3---|--TEST_3--|

  STEP 2: For each window:
    a) Optimize parameters on TRAIN data
    b) Apply best parameters to TEST data (out-of-sample)
    c) Record TEST performance

  STEP 3: Concatenate all TEST results → this is your realistic out-of-sample performance

  TYPICAL SPLIT:
    train_size: 2-3 years (or 300+ trades)
    test_size: 3-6 months (or 50+ trades)
    step: same as test_size (non-overlapping test periods)
    total_data_needed: 5+ years minimum
</method>

<overfitting_detection>
  RED FLAGS:
    - in_sample_sharpe > 2 * out_of_sample_sharpe → OVERFITTING
    - strategy works on 1 market but fails on similar markets → CURVE FITTING
    - small parameter changes (±10%) cause large performance swings → FRAGILE
    - too many parameters (>5 free parameters for simple strategies) → OVERFIT RISK
    - fewer than 200 trades in backtest → INSUFFICIENT SAMPLE

  ANTI-OVERFITTING RULES:
    1. minimize free parameters (each is a degree of freedom that can overfit)
    2. parameters must be robust: performance stable with ±20% variation
    3. test on multiple uncorrelated markets and time periods
    4. always include realistic transaction costs
    5. use walk-forward, NEVER just in-sample optimization
    6. apply Monte Carlo simulation to stress-test results
</overfitting_detection>

<monte_carlo>
  After walk-forward:
  1. Take the sequence of trade P&Ls from out-of-sample testing
  2. Randomly shuffle the order 10,000 times (bootstrap)
  3. For each shuffle, compute: max_drawdown, final_equity, CAGR
  4. Report 5th percentile (worst case), median, and 95th percentile

  DECISION: if 5th_percentile_max_drawdown > your_tolerance → reduce position size
  USEFUL: gives confidence intervals, not just point estimates
</monte_carlo>

<python_implementation>
```python
import numpy as np

def walk_forward(data, train_bars, test_bars, optimize_fn, evaluate_fn):
    """
    data: pd.DataFrame with OHLCV
    train_bars: number of bars for training
    test_bars: number of bars for testing
    optimize_fn(train_data) -> best_params dict
    evaluate_fn(test_data, params) -> performance dict
    Returns: list of out-of-sample performance dicts
    """
    results = []
    total = len(data)
    start = 0

    while start + train_bars + test_bars <= total:
        train = data.iloc[start : start + train_bars]
        test  = data.iloc[start + train_bars : start + train_bars + test_bars]

        best_params = optimize_fn(train)
        oos_perf = evaluate_fn(test, best_params)
        oos_perf['window_start'] = data.index[start]
        oos_perf['params'] = best_params
        results.append(oos_perf)

        start += test_bars  # step forward

    return results

def monte_carlo_analysis(trade_pnls, n_simulations=10000):
    """
    trade_pnls: array of individual trade P&L values
    Returns: dict with drawdown and return distributions
    """
    results = {'max_dd': [], 'final_equity': [], 'cagr': []}

    for _ in range(n_simulations):
        shuffled = np.random.permutation(trade_pnls)
        equity = np.cumsum(shuffled)
        peak = np.maximum.accumulate(equity)
        drawdown = peak - equity
        max_dd = drawdown.max()

        results['max_dd'].append(max_dd)
        results['final_equity'].append(equity[-1])

    return {
        'max_dd_5pct': np.percentile(results['max_dd'], 95),   # worst 5%
        'max_dd_median': np.median(results['max_dd']),
        'final_equity_5pct': np.percentile(results['final_equity'], 5),
        'final_equity_median': np.median(results['final_equity']),
        'final_equity_95pct': np.percentile(results['final_equity'], 95),
        'ruin_probability': np.mean([1 for dd in results['max_dd'] if dd > 0.5]),
    }
```
</python_implementation>
</infra_module>

---

<infra_module id="MONITORING">
<metrics_realtime>
  - daily_pnl (realized + unrealized)
  - trade_count_today
  - win_rate_rolling (last 20, 50, 100 trades)
  - current_drawdown vs max_historical_drawdown
  - sharpe_ratio_rolling (last 30, 60, 90 days)
  - avg_slippage_today
  - execution_latency_ms
  - connection_errors_count
  - open_position_count and total_exposure
</metrics_realtime>

<alerting_thresholds>
  INFO:     trade filled, daily summary
  WARNING:  drawdown > 50% of historical max, slippage anomaly, 3 consecutive losses
  ERROR:    connection timeout, order rejected, data gap detected
  CRITICAL: daily loss limit hit, heartbeat failure, kill switch activated
</alerting_thresholds>

<channels>
  - Telegram bot: real-time trade notifications, alerts
  - Email: daily/weekly performance reports, critical alerts
  - Grafana + InfluxDB: visual dashboard for monitoring
  - Log files: complete audit trail (every signal, order, fill, error)
</channels>
</infra_module>

---

## SECTION 5: PERFORMANCE METRICS REFERENCE

<metrics_reference>
| metric                 | formula                                                    | good      | excellent |
|------------------------|------------------------------------------------------------|-----------|-----------|
| total_return           | (equity_end - equity_start) / equity_start                 | > 0       | > 0.20/yr |
| CAGR                   | (equity_end / equity_start)^(1/years) - 1                  | > 0.10    | > 0.25    |
| sharpe_ratio           | (mean_return - rf) / std_returns (annualized)              | > 1.0     | > 2.0     |
| sortino_ratio          | (mean_return - rf) / downside_std                          | > 1.5     | > 3.0     |
| calmar_ratio           | CAGR / max_drawdown                                        | > 1.0     | > 3.0     |
| profit_factor          | gross_profit / gross_loss                                  | > 1.5     | > 2.0     |
| win_rate               | winning_trades / total_trades                              | > 0.40    | > 0.55    |
| payoff_ratio           | avg_win / avg_loss                                         | > 1.5     | > 2.5     |
| expectancy             | (win_rate * avg_win) - (loss_rate * avg_loss)              | > 0       | > 2*cost  |
| max_drawdown           | max peak-to-trough equity decline                          | < 0.20    | < 0.10    |
| max_dd_duration        | longest time to recover from drawdown                      | < 6 mo    | < 3 mo    |
| recovery_factor        | net_profit / max_drawdown                                  | > 3.0     | > 6.0     |
| trades_per_year        | total opportunities (sample significance)                  | > 50      | > 200     |
</metrics_reference>

---

## SECTION 6: PRE-DEPLOY CHECKLIST

<checklist>
BEFORE GOING LIVE, EVERY ITEM MUST BE CHECKED:

BACKTEST VALIDATION:
  □ backtest on ≥3 years of data (or ≥500 trades)
  □ walk-forward analysis completed with positive out-of-sample results
  □ tested on truly unseen data (never used during development)
  □ tested on ≥2 different markets/instruments
  □ realistic slippage AND commissions included
  □ Monte Carlo simulation: 95th percentile max_drawdown is acceptable
  □ parameter sensitivity: ±20% change → performance remains acceptable

RISK MANAGEMENT:
  □ position sizing formula implemented and tested
  □ stop-loss on every trade (no exceptions)
  □ circuit breakers configured (daily loss, consecutive losses, max positions)
  □ kill switch functional and tested
  □ heartbeat monitoring active
  □ max drawdown threshold defined BEFORE going live

INFRASTRUCTURE:
  □ paper trading for ≥1 month with real-time data
  □ logging captures every signal, order, fill, error
  □ alerting configured (telegram/email for critical events)
  □ data feed redundancy (backup source if primary fails)
  □ error handling for: connection loss, partial fills, order rejects
  □ contingency plan for extreme events (flash crash, exchange halt)

OPERATIONAL:
  □ capital allocated is < 20% of total net worth
  □ emotionally prepared for max_drawdown scenario
  □ review schedule set (weekly performance review, monthly deep analysis)
  □ documentation of all strategy rules and parameters
</checklist>

---

<disclaimer>
This document is for EDUCATIONAL and TECHNICAL reference only. It does NOT constitute financial advice.
Algorithmic trading carries significant risk including total loss of capital.
Past performance does not guarantee future results. No strategy is "unbeatable."
Always consult a licensed financial professional before trading with real capital.
</disclaimer>
