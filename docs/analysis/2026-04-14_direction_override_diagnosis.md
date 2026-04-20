# Direction Override Diagnosis — MR vs ML (2026-04-14)

## The Smoking Gun

File: `backend/src/strategy/strategy_manager.py`, lines 166-168:

```python
# Direction from MR rules, not from XGBoost
direction = (
    SignalDirection.BUY if mr_signal.direction == "BUY" else SignalDirection.SELL
)
```

**The ML model never decides direction. Ever. Not even as a tiebreaker.**

---

## How the Pipeline Actually Works

```
1. MR strategy computes z-score from VWAP/BB deviation
   → Decides: BUY (price below mean) / SELL (price above mean) / HOLD (not extreme enough)

2. If HOLD → no trade. Done.

3. If BUY or SELL → asks XGBoost: "how confident are you about the next bar?"
   → XGBoost returns a confidence score (0-1)
   → This is used as a "quality gate", NOT as a direction vote

4. If quality < mr_min_quality → HOLD (trade blocked)

5. Otherwise → opens trade in MR direction (NOT ML direction)
```

The XGBoost model with 199 features and F1 0.55 is a **bouncer** — it decides whether the door is open, not where to go. The MR z-score decides direction 100% of the time.

---

## Evidence from the Database

### signal_log (29,949 entries)
- All executed trades: `strategy = 'mean_reversion'`, `model_proba = None`
- The ML prediction probability is **not even recorded**
- Example executed signals:
  ```
  NATGAS LONG  conf=0.66  model_proba=None  strat=mean_reversion
  DE40   LONG  conf=0.60  model_proba=None  strat=mean_reversion
  TSLA   LONG  conf=0.56  model_proba=None  strat=mean_reversion
  NVDA   SHORT conf=0.90  model_proba=None  strat=mean_reversion
  ```

### positions (1,137 closed)
- `signal_id`: **0 out of 1,137** have a link to the ML signal
- `strategy_id`: **0 out of 1,137** populated
- There is no way to retrospectively compare ML direction vs actual direction — the data was never stored

### signals table (4,776 entries)
- `features.ml`: always `null`
- The ML prediction is not persisted in any queryable form

---

## Why This Explains the 28% Win Rate

The MR strategy is a **contrarian** strategy:
- Price above VWAP → SELL (expect reversion to mean)
- Price below VWAP → BUY (expect reversion to mean)

This works in **ranging/mean-reverting markets**. It fails catastrophically in **trending markets** because:
- In an uptrend: price is persistently above VWAP → MR keeps selling → SL hit repeatedly
- In a downtrend: price is persistently below VWAP → MR keeps buying → SL hit repeatedly

**From February to April 2026, markets were dominated by strong trends** (tariff volatility, macro moves). The MR strategy was systematically:
- Selling assets in uptrends
- Buying assets in downtrends

The ADX filter (`mr_adx_max`) is supposed to prevent this, but evidently it's not filtering aggressively enough — or the threshold is wrong.

---

## The XGBoost Model Is Wasted

The ML model was trained to predict direction (BUY/SELL/HOLD) with F1 0.50-0.63. This means it has **genuine predictive power** on direction. But the system architecture ignores this entirely:

| Component | Role | Uses ML direction? |
|---|---|---|
| MR Strategy | Decides direction via z-score | No — rule-based only |
| XGBoost | Quality gate (confidence threshold) | No — only confidence scalar used |
| Risk Manager | Position sizing, exposure limits | No |
| Execution Engine | Order placement | No |

The model's best capability (direction prediction) is discarded. Its weakest capability (generic confidence score) is the only thing used.

---

## What Cannot Be Answered (Data Gap)

The critical question — **"How often did ML and MR agree on direction?"** — is unanswerable from the current DB because:

1. The ML predicted direction is never stored (`model_proba = None`, `features.ml = null`)
2. Positions don't link to signals (`signal_id = 0` on all 1,137 trades)
3. The signal_log only records the final MR direction, not the ML prediction

To answer this, we would need to either:
- Add logging of ML direction vs MR direction at decision time
- Run a retrospective backtest comparing ML-only vs MR-only vs current hybrid

---

## Possible Paths Forward

### Option A: Let ML decide direction, MR provides SL/TP levels
- ML has F1 0.55 on direction → expected WR ~55% (vs current 28%)
- MR z-score sets the mean target for TP, ATR sets SL
- Risk: ML predictions may not translate from OOS test to live (train/live gap)

### Option B: Require ML and MR to agree (consensus)
- Only trade when ML direction == MR direction
- Fewer trades, but higher conviction
- Risk: reduces trade frequency significantly, may miss opportunities

### Option C: Use ML direction with MR as a filter (inverse of current)
- ML decides BUY/SELL
- MR z-score must confirm (e.g., z > 1.5 in ML's direction)
- Risk: MR filter may block too many ML signals

### Option D: Pure ML (remove MR entirely)
- Trust the XGBoost predictions for direction
- Use ATR-based SL/TP (no z-score dependency)
- Risk: ML may overfit, no contrarian hedge

### Option E: Keep MR but fix the regime filter
- Tighten ADX filter (lower threshold) to only trade in confirmed ranging markets
- Accept fewer trades in exchange for higher WR
- Risk: may result in very few trades per week

---

## Recommendation

**Do not change anything yet.** First:

1. **Add dual-direction logging**: record both ML predicted direction and MR direction in signal_log for every signal (including HOLD). Run for 1-2 weeks.
2. **Compute agreement rate**: what % of the time do ML and MR agree?
3. **Compute WR by agreement**: when they agree, what's the WR? When they disagree?
4. **Then decide**: the data will tell you whether Option A, B, C, or E is correct.

Making another architecture change without this data would repeat the pattern identified in the postmortem: reasonable changes based on theory, without verifying assumptions against actual data.
