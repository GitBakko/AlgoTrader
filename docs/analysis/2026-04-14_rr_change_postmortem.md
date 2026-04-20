# R:R Change Postmortem — Why 2.0 → 0.75 Was Premature (2026-04-14)

## Critical Context

The 1,137 trades in the DB span weeks/months. The R:R 0.75 change was made on **April 9** — 5 days ago. Of those 5 days:
- Apr 10: ~3 trades opened with new R:R
- Apr 11: time-stop tried to close but market was closed (Friday evening)
- Apr 12-13: weekend, zero trades, plus scheduler bug blocked 4h candle refresh
- Apr 14: first working day after the scheduler fix

**Almost all 1,137 trades were made with the OLD R:R 2.0** (or worse, with the R:R 7-10 blow-up on indices before the post-fill modify fix). The 27.8% WR does **not** measure the current system — it measures the broken system we spent weeks fixing.

---

## Why Was R:R Changed?

On April 9, the user noticed DE40 had a TP target at 4.3% — unrealistic for a 4h mean reversion trade. I researched the literature and found:

- Lopez de Prado, QuantPedia, Robot Wealth all converge on **TP/SL 0.5–1.0 for MR**
- R:R 2.0 is a trend-following ratio, not a mean reversion ratio
- MR works with tight targets and high win-rate (55–65%)

The reasoning was correct **in theory**.

---

## The Mistake

I applied the change without verifying a critical assumption: **that the ML model could deliver a 55%+ win rate**.

If the model predicts direction correctly only 28% of the time, changing R:R from 2.0 to 0.75 **mathematically accelerates losses**:

| R:R | Break-even WR | Expectancy at WR 28% |
|---|---|---|
| 2.0 | 33% | 0.28 × 2.0 − 0.72 × 1.0 = **−0.16** |
| 1.5 | 40% | 0.28 × 1.5 − 0.72 × 1.0 = **−0.30** |
| 1.0 | 50% | 0.28 × 1.0 − 0.72 × 1.0 = **−0.44** |
| 0.75 | 57% | 0.28 × 0.75 − 0.72 × 1.0 = **−0.51** |

With WR 28%, R:R 0.75 loses **3x faster** than R:R 2.0. I took a system that was losing slowly and made it lose fast.

---

## The Pattern of Reactive Changes

| Date | Change | Rationale | Correct in isolation? | Addressed root cause? |
|---|---|---|---|---|
| Apr 9 | TP_MAX_ATR 4.0 → 1.5 | TP too far for MR | Yes | No |
| Apr 9 | MR_MAX_HOLD_HOURS = 24h | Positions drifting | Yes | No |
| Apr 9 | Hardcoded R:R override removed | paper_loop was ignoring strategy params | Yes (bug fix) | No |
| Apr 9 | 8 excluded epics reactivated | Old exclusions based on 83-feature models | Debatable | No |
| Apr 10 | Per-class ATR multipliers | TSLA SL at 5% too wide | Yes | No |
| Apr 10 | MR_MAX_HOLD 24h → 12h | 16h positions still open | Yes | No |
| Apr 12 | Scheduler 4h refresh fix | No 4h candles = no signals | Yes (bug fix) | No |
| Apr 12 | Skip SL/TP check when market closed | Spam errors on weekends | Yes | No |

Every single change was reasonable in isolation. But **none attacked the real problem**: the model predicts the wrong direction 72% of the time. Until that changes, every other adjustment is cosmetics on a corpse.

---

## What Should Have Been Done on April 9

1. **Check historical WR BEFORE touching parameters** — the 28% WR was already in the DB
2. **Realize that with WR 28%, the only R:R that slows losses is the highest possible** — not the lowest
3. **Focus on WHY the model gets direction wrong**, not on how to size SL/TP
4. **Do not reactivate 8 excluded epics** without first understanding why the current 10 are losing

---

## The Real Question

The R:R ratio is a second-order problem. The first-order problem is:

> **Why does the model predict the correct direction only 28% of the time when the OOS F1 during training was 0.50–0.63?**

Possible explanations (to investigate):
1. **Train/live distribution shift**: training data looks different from live market conditions (tariff-era volatility, regime change)
2. **Feature leakage in training**: OOS F1 was inflated by subtle data leakage (lookahead in rolling features, overlapping windows)
3. **MR direction ≠ ML direction**: the MR strategy overrides the ML prediction for direction, using the ML only as a quality score — if MR is systematically wrong on direction, a high ML F1 doesn't help
4. **The 28% WR includes the broken R:R period**: when R:R was 7-10 on indices, even correct-direction trades hit SL before TP because the SL was absurdly close relative to market noise

Investigation #3 and #4 are the most likely. The MR strategy decides direction based on z-score (price deviation from VWAP/BB), not the ML model. If the market is trending (not mean-reverting), the MR direction will be systematically wrong regardless of ML quality.

---

## Recommended Next Steps

1. **Revert R:R to 2.0** until WR improves — it loses slower
2. **Split the WR analysis**: trades before Apr 9 vs after, to see if recent fixes helped at all
3. **Investigate MR direction accuracy**: what % of MR signals correctly predicted the direction? Compare with ML prediction direction
4. **ADX filter audit**: the MR strategy has an ADX gate (skip trending markets) — is it working? What ADX values were active during losing trades?
5. **Do NOT make more parameter changes** until the direction accuracy question is answered
