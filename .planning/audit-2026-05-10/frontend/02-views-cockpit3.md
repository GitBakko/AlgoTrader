# Frontend Audit — Cockpit-3 Views (2026-05-10)

## Stats
- Files reviewed: 36 (TS: 18, HTML: 10, SCSS: 8)
- Total findings: 12 (CRITICAL: 1, HIGH: 4, MEDIUM: 6, LOW: 1)

---

## CRITICAL

### C1-VIEWS-COCKPIT3: Trading Invariant #2 violated in legacy Dashboard
**File**: `frontend/src/app/views/dashboard/dashboard.component.ts:163-170`

**Issue**: `allLivePositions` falls through to `(currentPrice - pos.level) * pos.size` multiplication whenever `pos.upl == null`. This is the exact forbidden pattern from CLAUDE.md Invariant #2. Sibling views (`paper-trading.component.ts:591`, `positions.component.ts:527`) both return `live_pnl: 0` when UPL is null — the legacy dashboard is inconsistent and invents P&L that ignores spreads, FX multipliers, and contract size.

**Why bad**: Invariant #2 says no `(exit-entry)*size` fallbacks. Always P&L from broker `Transaction.size` or `Position.upl`. This path invents P&L.

**Fix**: Remove arithmetic branch; return `{ ...pos, live_pnl: 0 }` when `upl == null`.

---

## HIGH

### H1-VIEWS-COCKPIT3: `effect()` writes signal without `queueMicrotask` — BotVitalsPanel
**File**: `paper-trading/components/bot-vitals-panel/bot-vitals-panel.component.ts:73-84`

**Issue**: Constructor effect calls `this.beating.set(false)` synchronously inside the effect body, deviating from the project's established pattern (position-detail-drawer uses `queueMicrotask`). Under rapid heartbeat bursts two CD cycles are emitted per beat.

**Fix**: Wrap both `set()` calls in `queueMicrotask`.

### H2-VIEWS-COCKPIT3: `openPosition` lookup by epic only in OvernightSwapComponent
**File**: `dashboard-v2/cockpit-bottom/overnight-swap.component.ts:73`

**Issue**: `positions.find(p => p.epic === target)` violates CLAUDE.md "livePosition lookups MUST match by `deal_id`, not `epic`". When two positions share an epic (stale closing + new), wrong direction is picked → wrong swap rate displayed.

**Fix**: Sort by `opened_at` DESC and take the most recent match, or filter by `upl != null`.

### H3-VIEWS-COCKPIT3: `swapEpic` validation by epic only in DashboardV2
**File**: `dashboard-v2/dashboard-v2.component.ts:105`

**Issue**: `positions.some(p => p.epic === pick)` same epic-only matching pattern. Closed position whose epic is still in the array can keep `userSwapEpic` appearing "valid" after it is gone.

**Fix**: Add `&& p.upl != null` guard.

### H4-VIEWS-COCKPIT3: `pnlPct` uses price arithmetic for non-USD-quote instruments
**File**: `paper-trading/paper-trading.component.ts:593-595`

**Issue**: `((current - p.level) / denom) * 100` displayed as P&L percentage on all position cards. Ignores FX conversion — USDJPY shows incorrect %.

**Fix**: Derive from `upl / (entry * size)`.

---

## MEDIUM

### M1-VIEWS-COCKPIT3: Hardcoded `#0d1117` in dashboard-v2.component.scss:7
Use `var(--mantis-surface-1)`.

### M2-VIEWS-COCKPIT3: Multiple `rgba(57, 255, 20, ...)` literals
`dashboard-v2.component.scss:83-84, 137-138, 151-153` — use `color-mix(in srgb, var(--mantis-neon) ..., transparent)` or SCSS token.

### M3-VIEWS-COCKPIT3: `font-size: 1.05rem` in dashboard.component.scss:167
Use nearest token `var(--mantis-fs-md)`.

### M4-VIEWS-COCKPIT3: `pos.direction === 'SHORT'` in overnight-swap.component.ts:49
Capital.com emits `'SELL'` not `'SHORT'`. Swap tile always displays the long rate for SELL positions.
**Fix**: `dir === 'SELL' || dir === 'SHORT'`.

### M5-VIEWS-COCKPIT3: SVG icon lacks `aria-hidden="true"` on CSV export button in positions.component.ts inline template.

### M6-VIEWS-COCKPIT3: `stopLoss` fallback to `p.level` inflates R:R
For locally-risk-managed positions with no broker SL. KPI strip's average R:R is misleading.
**Fix**: Treat `stop_level == null` as `rr = 0` for the average.

---

## LOW

### L1-VIEWS-COCKPIT3: `DashboardComponent` decorator omits `standalone: true`
`dashboard.component.ts:28-43`. Defaults to true in Angular 21 but inconsistent with every other view.

---

## Notes — Clean areas
- No mock data, `syntheticSpark`, or in-memory WS ring buffers found anywhere in scope. TradeBreakdown correctly shows a "backend missing" banner. KPI and position sparklines correctly source from snapshot endpoints.
- All `!important` uses inside `prefers-reduced-motion` blocks are legitimate CoreUI animation overrides.
- No `console.log` found.
- Signal-effect infinite-loop risk: only BotVitalsPanel deviates from project pattern (H1 above). All other effects (`paper-trading` WS throttle, `position-detail-drawer` deal reset) use proper deferral.
