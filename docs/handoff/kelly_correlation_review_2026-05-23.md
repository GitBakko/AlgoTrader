# Kelly Sizer + Correlation Review — Phase 1 Expansion (19 assets)

**Date:** 2026-05-23
**Trigger:** Phase 0 ri-validation expanded tradable basket from 5 → 19
(`docs/handoff/NEXT_SESSION_PROMPT.md` §Tradable basket expansion).
**Scope:** Validate that risk caps, Kelly sizer and correlation guard
behave coherently when 19 assets compete for equity allocation. Propose
concrete config deltas before turning the expanded basket on in paper
trading.

## TL;DR

| Concern | Current | Issue at 19 assets | Proposed delta |
|---|---|---|---|
| Concurrent positions cap | `MAX_TOTAL_OPEN_POSITIONS=5` (lowered 20→5 on 2026-05-15 for portfolio safety) | Hard bottleneck — only 5 of 19 candidates can be open simultaneously, defeating diversification thesis. | Raise to **10** as a first step. Monitor 2 weeks. |
| Per-position notional cap | `max_position_pct=0.20` (20 % equity per trade, default) | With 10 concurrent positions, worst-case 200 % notional exposure (before forex 60× multiplier). Already covered by `max_total_exposure=1.0` cap but at the wrong layer. | Lower to **0.10** (10 % per position). Forex 60× multiplier still applies on top for USD-base pairs only. |
| Total exposure cap | `MAX_TOTAL_EXPOSURE=1.0` (effectively disabled — only enforced when `<1.0`) | At 10 positions × 10 % = 100 % notional cap reached naturally without leverage. Could activate to enforce hard ceiling. | **Enable** `MAX_TOTAL_EXPOSURE=1.0` cap (currently skipped because of `<1.0` guard in `risk_manager.py:212`) — fix the guard or set to `0.99`. |
| Correlation guard — static pairs | 9 hardcoded pairs in `correlation_guard.py:15` | Misses USD-forex cluster, US tech megacaps, commodities triangle (COPPER/WTI/XAU). Static enumeration cannot scale to C(19,2)=171 pairs. | Add **6 critical pairs** (see §4 below). Enable dynamic matrix as primary. |
| Correlation guard — dynamic matrix | `CORRELATION_REGIME_ENABLED=False` (Phase 2 gate FAILED, gate stays off) | Phase 2 was a separate experiment (regime gating). The *dynamic correlation matrix* in `CorrelationGuard.update_matrix()` is independent and is the right tool for 19-basket sizing reduction. | **Enable** a fresh flag (`DYNAMIC_CORRELATION_ENABLED`) decoupled from Phase 2's `REGIME_GATE_ENABLED`. Refresh nightly from price history. |
| Kelly stats scope | Global deque of last 200 trades, blended across all epics (`paper_loop.py:221`) | At 19 dissimilar assets the global win-rate/payoff is a noisy aggregate; USDCHF (WR 64 %) and NVDA (WR 50 %) get the same Kelly fraction. | Phase-1 fix: **flag as known limitation**, monitor live edge. Phase-2 fix: per-asset deque with global fallback when `len < min_trades`. |
| Dead config | `max_correlated_exposure=0.50` in `RiskLimits` but never read in `risk_manager.py` | Cosmetic — caller can think a cap is enforced when it isn't. | Either wire it into `_check_correlated_exposure` (sum of size×corr per cluster ≤ 0.50 × equity) or **delete the field** to remove confusion. |

## 1. Concurrent positions cap

`RiskLimits.max_total_open_positions` defaults to **5** (was lowered from
20 on 2026-05-15 — see schemas.py:36 description "portfolio safety").
`risk_manager.py:201` rejects any new trade when `total_open ≥ 5`.

With 19 candidate epics each producing a 4h signal independently, the
expected number of *simultaneously viable* signals at any tick is
substantially higher than 5. With the cap unchanged the basket
collapses to "first 5 to fire" — defeating the entire diversification
gain demonstrated in the ri-val (Sharpe 3.75 USDCHF + 3.34 WTI + 2.98
USDCAD all standalone winners).

**Proposed:** `MAX_TOTAL_OPEN_POSITIONS=10` (covers ~53 % of basket).
Combined with the per-position cap reduction (§2) this keeps the
worst-case notional at 100 % equity — same as today's
`5 × 20 % = 100 %`.

**Hard upper:** schema accepts `le=50` — leaves headroom. Don't go
above 12 without a dedicated portfolio-heat metric (sum of `risk_amount`
across open trades ≤ `2 × max_risk_per_trade × equity` is the textbook
ceiling).

## 2. Per-position notional cap

`RiskLimits.max_position_pct=0.20` is the per-trade notional cap
expressed as a fraction of equity. The exposure cap (§3) covers the
*sum*; the per-position cap covers individual blow-ups.

With 10 concurrent slots, 20 % per position can produce 200 % notional
gross. Lowering to **0.10** keeps the 100 % gross identical to today's
behaviour while still letting each trade be large enough to clear the
$10 risk floor (`MIN_RISK_AMOUNT_USD=10`) on most assets.

Forex USD-base pairs (USDJPY/USDCHF/USDCAD) use
`forex_usd_base_size_multiplier=60` on top of `max_position_pct`
(`config.py:349`), so effective cap stays at 6 % equity (10 % × 60 / 100)
— still ≈ 30 % less than today's 12 % (20 % × 60 / 100). Forex sizing
is dominated by the floor lift in step 7-bis, not the cap, so the
practical impact is minor.

## 3. Total exposure cap

`risk_manager.py:212-221` has a guard:

```python
if self.limits.max_total_exposure < 1.0 and open_positions and equity > 0:
    ...
    if exposure_ratio >= self.limits.max_total_exposure:
        return REJECT
```

Because the default is exactly `1.0`, the entire enforcement branch is
**skipped**. The cap is effectively never checked. With 19 assets
competing for equity this should be activated.

**Option A (minimal change):** set default to `0.99`. The branch
activates without changing real behaviour at any reasonable trade size.

**Option B (semantic fix):** change the guard from `<1.0` to `<=1.0`.
Cleaner — `MAX_TOTAL_EXPOSURE=1.0` should mean "100 % cap enforced",
not "disabled".

I'd take **B**; it's a one-line semantic fix and avoids the
"floating-point dance to keep `MAX_TOTAL_EXPOSURE` from being a no-op"
trap.

## 4. Correlation guard — static pairs

`correlation_guard.py:15-25` lists 9 hardcoded pairs. Missing for the
expanded basket:

| New pair | Plausible correlation | Reason |
|---|---|---|
| `USDCHF` ↔ `USDCAD` | 0.60 | Both USD-base — share DXY direction. |
| `USDCHF` ↔ `USDJPY` | 0.55 | Same. |
| `USDCAD` ↔ `USDJPY` | 0.55 | Same. |
| `US500` ↔ `MSFT` / `GOOGL` / `META` / `AAPL` / `AMD` | 0.50 each | All top-10 SP500 constituents. |
| `MSFT` ↔ `GOOGL` ↔ `META` ↔ `AAPL` | 0.40-0.50 between any pair | Tech megacap cluster. |
| `COPPER` ↔ `WTIUSD` | 0.40 | Both industrial-demand commodities. |
| `XAUUSD` ↔ `PLATINUM` | 0.65 | Precious metals cluster. |
| `DE40` ↔ `US500` | 0.70 | Already in the static list, leave. |

If you stay with the static-only path you need to extend the list to
roughly **20 pairs**. C(19,2)=171 pairs total — static can't reasonably
cover all clusters.

## 5. Correlation guard — dynamic matrix (IMPLEMENTED 2026-05-23)

The dynamic correlation matrix is now populated by
`paper_loop._refresh_correlation_matrix` (split out of the legacy
`_refresh_correlation_regime`) and consumed by
`RiskManager.check_trade` step 5 via
`correlation_guard.check_exposure_dynamic`.

Flags:
- `DYNAMIC_CORRELATION_ENABLED=true` (default, new) — gates the matrix
  refresh. Decoupled from `CORRELATION_REGIME_ENABLED` (Phase 2 panic
  regime gate, separate experiment).
- `DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS=5` (default, new) — floor on
  how many epics with ≥100 bars are needed before refresh runs.

Coverage: full `self.epics` basket (was `[:10]` in the legacy path).
Throttle: one refresh per 30 min unless `force=True` (used by first-tick
bootstrap so the matrix is hot before signal generation).

Validation: `CorrelationGuard.update_matrix` now rejects matrices with
NaN/Inf entries (constant-price epic in `np.corrcoef`). Prior matrix
preserved on rejection.

Implementation: commits `0f48804` (settings), `48c6128` (paper_loop split),
`6bf1eb3` (NaN/Inf validation). Plan: `docs/superpowers/plans/2026-05-23-phase1-expansion-risk-config.md` Task 5 + Task 6 + Task 4.

## 6. Kelly sizer scope

`paper_loop.py:221` declares:

```python
self._trade_history: deque[dict] = deque(maxlen=200)
```

— a **single global deque** of the last 200 trade pnls across all
assets. `AdaptiveKellySizer.compute_stats()` reads `pnl` only; it does
not look at `epic`. So a winning streak on USDCHF inflates the Kelly
fraction applied to subsequent NVDA trades.

At 5 assets this drift was tolerable (assets clustered in crypto +
gold, similar edge profiles). At 19 assets with forex (high WR / low
payoff) mixed with stocks (50 % WR / higher payoff) the blended Kelly
will systematically *overweight* the low-payoff epics and *underweight*
the high-payoff ones.

**Phase 1 (now):** Document as known limitation. The half-Kelly cap
(`max_kelly=0.25` and `use_half_kelly=True`) means the worst-case Kelly
fraction is 12.5 % of equity — same blast radius for any epic.

**Phase 2 (post 2-week paper soak):** map `epic → deque(maxlen=100)`,
fall back to global when an epic has < `min_trades=30`. ~30 lines of
code, no architectural change.

## 7. Dead config

`RiskLimits.max_correlated_exposure: float = 0.50` (schemas.py:35) is
declared but never read by `risk_manager.py`. Either:

- (a) Wire it: sum `position_size × max(|corr|, static_reduction)`
  across the correlated cluster, reject when > 0.50 × equity. The
  correlation matrix already exposes the data.
- (b) Delete the field. Less confusing.

Today (b) is the safer call — the dynamic matrix + per-position cap
already enforce the same intent via the size multiplier (corr=0.6 →
multiplier 0.4 → position shrinks). Adding a separate cluster cap is a
second gate on the same dimension.

## Proposed config delta — paste-ready

```bash
# backend/.env
# Phase 1 expansion (19-asset basket) risk-cap adjustments
MAX_TOTAL_OPEN_POSITIONS=10
# (raise from 5; combined with lower per-position cap keeps gross 100% notional)

# Per-position notional cap moved into RiskLimits default — no env override
# needed unless you want to deviate. The RiskLimits Pydantic default is the
# enforcement layer. Update schemas.py:34: max_position_pct=0.10.

# Activate the total-exposure cap (one-line fix in risk_manager.py:212)
# Change `if self.limits.max_total_exposure < 1.0` → `<= 1.0`.
MAX_TOTAL_EXPOSURE=1.0  # already default; the guard fix is in code

# New flag — dynamic correlation matrix, independent of Phase 2 regime gate
DYNAMIC_CORRELATION_ENABLED=true
DYNAMIC_CORRELATION_REFRESH_HOURS=24
```

## Open items / deferred

- **Per-asset Kelly stats** — defer to post-paper-soak (Phase 2 fix).
- **Static correlation pair extension** — only useful if dynamic matrix
  isn't enabled; otherwise the matrix supersedes. If dynamic gets
  enabled, leave static pairs as the fallback they already are.
- **`max_correlated_exposure` field** — flag for cleanup PR (delete or
  wire), not blocking.
- **Portfolio heat metric** — sum of `risk_amount_usd` across open
  trades. If > `2 × max_risk_per_trade × equity` (=4 % at default) the
  next signal sizes down or rejects. Not in this milestone but worth
  thinking about before going to 12+ concurrent positions.

## Validation plan before live deploy

1. **Phase 1 expansion Optuna** — run
   `phase1_optuna_full_basket.py` (100 trials × 19 epics ≈ 25 min) →
   confirm per-asset KEEP gate ≥ 14/19 (matches ri-val baseline).
2. **Apply config delta** (`MAX_TOTAL_OPEN_POSITIONS=10`,
   `max_position_pct=0.10`, dynamic correlation enabled) on dev.
3. **Backtest sanity** — re-run `phase4_btc_walkforward.py` to verify
   BTC standalone Sharpe doesn't regress (cap changes shouldn't affect
   single-asset path).
4. **Paper soak** — enable expanded basket in DEMO for 14 days,
   monitor:
   - Concurrent position count distribution
   - Per-asset Kelly fraction drift (log `kelly_stats` every 30 min)
   - Correlation guard size-multiplier rejections (count per epic)
   - Realised vs expected DD (should stay < Phase 0 baseline)
5. **Promote to LIVE** only if (a) all above pass and (b) per-asset
   Kelly limitation hasn't manifested as cross-epic edge bleed.

## Artifacts

- Config inspected: `backend/src/utils/config.py`,
  `backend/src/risk/schemas.py`,
  `backend/src/risk/risk_manager.py`,
  `backend/src/risk/kelly_sizer.py`,
  `backend/src/risk/correlation_guard.py`,
  `backend/src/trading/paper_loop.py`.
- Sibling reports: `2026-05-23_phase0_revalidate_excluded.md`,
  `2026-05-23_phase3_rerun.md`.
- Next step script: `backend/scripts/phase1_optuna_full_basket.py`.
