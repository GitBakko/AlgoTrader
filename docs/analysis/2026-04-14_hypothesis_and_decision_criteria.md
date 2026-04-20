# Hypothesis & Decision Criteria — ML vs MR Direction (2026-04-14)

Written before data collection. Do not modify after data arrives.

---

## Hypothesis

The 28% win rate is caused by MR contrarian direction decisions in trending markets. The ML model (F1 0.55 OOS) has predictive power on direction that is currently unused. Giving ML a role in direction decisions will improve WR.

## What We're Measuring (2 weeks starting 2026-04-14)

From the `DIRECTION AUDIT` log lines and signal metadata:

1. **Agreement rate**: % of signals where `ml_agrees = true`
2. **WR by agreement**: win rate on executed trades when ML and MR agree vs disagree
3. **ADX distribution on losers**: ADX values on SL-closed trades (is the regime filter broken?)
4. **ML direction accuracy (standalone)**: of all signals where ML said BUY, how often did price go up within 12h? (can compute from historical data retrospectively)

## Decision Matrix

### If agreement rate > 60% AND WR(agree) > 45%:
→ **Option B (consensus)**: require ML and MR to agree. The filter doesn't kill too many trades and the agreed-upon direction is meaningfully better.

### If agreement rate < 40% AND WR(ML-direction) > 45%:
→ **Option A (ML decides direction, MR provides levels)**: ML and MR are systematically opposing each other. ML's direction is more often right. Let ML lead.

### If WR(agree) ≈ WR(disagree) ≈ 28%:
→ **Neither ML nor MR has edge on direction**. The problem is deeper — either feature leakage inflated OOS F1, or the model doesn't generalize to live. Go to Option E (aggressive ADX filter to only trade confirmed ranging regimes) as a stopgap while investigating model validity.

### If ADX on losers is consistently > 25 (trending):
→ **The ADX filter is too loose**. Lower `mr_adx_max` from current value to 20 or even 15. This is compatible with any of the above options.

### If ADX on losers is < 25 (not trending):
→ **MR is failing even in ranging markets**. The z-score entry threshold may be wrong, or the mean target (VWAP/BB) is unreliable. Deeper investigation needed.

## What NOT To Do When Data Arrives

- Do not change R:R again based on WR alone (learned this the hard way)
- Do not reactivate/deactivate assets based on 2 weeks of data
- Do not make multiple changes simultaneously — one architectural change, measure, repeat
- Do not optimize parameters (ATR mult, z-score threshold, ADX max) before settling the direction question

## Success Criterion

The minimum viable outcome is: **identify one configuration where WR > 40% on a subset of assets**. We don't need all 18 assets to work. Even 5 profitable assets with WR > 45% would be a foundation to build on.

## Timeline

- **2026-04-14**: logging deployed, data collection begins
- **2026-04-28**: first data review (~2 weeks)
- **2026-04-28**: decision on which Option to implement
- **2026-05-05**: one week of live testing with new architecture
- **2026-05-12**: second review, decide if direction is viable
