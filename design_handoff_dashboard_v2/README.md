# Handoff: MANTIS AI — Dashboard v2 (Variant B) + 2 new KPIs

> **Audience:** Claude Code (or human dev) working in **GitBakko/AlgoTrader** (Angular 21 + CoreUI + SCSS).
> **Bundle:** HTML/React mocks + this README. Mocks are **design references**, NOT code to paste.
> **Objective:** Recreate the designs inside the existing Angular dashboard, **wired to real trading/risk/performance data** from `TradingService` / `WebSocketService`. The handoff is only **successful** when **every mock number in this bundle is replaced by live, production data — no hardcoded trade counts, P&L, equity, durations, funding, or TP/SL/Going counts may remain**.

---

## 1. About the design files

The `mocks/` folder in this bundle is a **React + inline-JSX prototype** (Babel-standalone, no build). It renders inside the `DesignCanvas` component just as a visual spec. **Do not ship this React code** — the production app is Angular.

Your job:
1. Read the mocks as the source of truth for **layout, visual hierarchy, colors, typography, spacing, and interactions**.
2. Reimplement them as **Angular 21 standalone components** living in `frontend/src/app/views/dashboard/` (and subfolders you create under it).
3. Wire every value to real data via the existing services (`TradingService`, `WebSocketService`, `MarketStatusService`, etc.).
4. Respect the existing theme tokens in `frontend/src/scss/_palette.scss` + `_custom.scss` — **use CSS variables, never hex literals**.

## 2. Fidelity

**High-fidelity.** Colors, typography, glows, borders, exact pixel spacing — all are final. The only thing that is *not* final is the dataset: numbers are randomized plausible values.

## 3. Where this lands in the codebase

- Existing dashboard: **`frontend/src/app/views/dashboard/`**
  - `dashboard.component.ts` — `DashboardComponent` (ChangeDetection.OnPush, standalone)
  - `dashboard.component.html`
  - `dashboard.component.scss`
  - `dashboard-charts-data.ts`
  - `utils.ts`
  - `routes.ts`
- Services to reuse (no new HTTP client needed except where noted):
  - `core/services/trading.service.ts` — `overview`, `equityCurve`, `performance`, `paperStatus`, `riskStatus`, `paperPositions`, `paperSignals`
  - `core/services/websocket.service.ts` — live prices
  - `core/services/market-status.service.ts` — session state
  - `core/services/news.service.ts` — US500 headlines
  - `core/services/notification-center.service.ts` — alerts/unread count
- Shared components to reuse:
  - `shared/components/tv-chart/tv-chart.component.ts` (equity curve)
  - `shared/components/epic-logo/epic-logo.component.ts` (instrument logos)
  - `shared/components/skeleton-card/skeleton-card.component.ts`
  - `shared/components/skeleton-table/skeleton-table.component.ts`
- Theme tokens: **`frontend/src/scss/_palette.scss`** + **`frontend/src/scss/_custom.scss`** — read these BEFORE writing SCSS.
- Design-system CSS variables available on `:root` (examples):
  - `--mantis-neon` `#39FF14` · `--mantis-green` `#00d97e` · `--mantis-danger` `#FF3D57` · `--mantis-warning` `#FFB020` · `--mantis-info` `#00E5FF`
  - `--mantis-bg` `#0d1117` · `--mantis-surface-2` `#161b22`
  - `--mantis-font-sans` (Plus Jakarta Sans) · `--mantis-font-mono` (IBM Plex Mono)

## 4. Scope — what to build

This handoff covers **three deliverables**, in priority order:

### Deliverable A — New `DashboardV2` page (Variant B "Cockpit")
A full redesign of the dashboard view. Replaces `dashboard.component.html` entirely. See **§6**.

### Deliverable B — `OperationalStripComponent` (new, reusable KPI strip)
A standalone sub-component rendered at the top of Deliverable A. Can also be consumed by other views. See **§7**.

### Deliverable C — `TradeBreakdownComponent` (new, reusable per-day breakdown)
A standalone sub-component rendered at the bottom of Deliverable A. See **§8**.

> **Each deliverable is only DONE when it reads from a real service. Hardcoded arrays = not done.**

---

## 5. Global dashboard shell (Variant B — "Cockpit")

### 5.1 Layout

Root container: `display: flex; flex-direction: column; gap: 10px; background: #0a0e13; padding: 14px;`.

Children, in order:

```
┌──────────────────────────────────────────────────────────────┐
│ 1. Top command bar (timeframe tabs + live clock + kill btn)  │   40px
├──────────────────────────────────────────────────────────────┤
│ 2. OperationalStripComponent  (Deliverable B)                │   ~86px
├──────────────────────────────────────────────────────────────┤
│ 3. Cockpit spine   ──   Equity + KPI rail (left 2fr / right 1fr) │ ~400px
├──────────────────────────────────────────────────────────────┤
│ 4. Bottom row   Duration · Funding · Heatmap (1/1/1.7)      │ ~260px
├──────────────────────────────────────────────────────────────┤
│ 5. TradeBreakdownComponent  (Deliverable C)                 │ ~280px
└──────────────────────────────────────────────────────────────┘
```

Design uses a fixed 1380×1260 artboard; in production it should be **responsive**. Above 1280px use the layout above; below 1280px stack each row to 1-col.

### 5.2 Top command bar

A single horizontal bar, 40px tall, 4px radius, `background: #161b22`, `border: 1px solid rgba(0,217,126,0.15)`, `padding: 0 14px`:

- **Left:** pill-group of **timeframe tabs** — `1D · 7D · 30D · 90D · YTD · ALL · Custom…`.
  - Active tab: `background: rgba(57,255,20,0.1); color: #39FF14; box-shadow: 0 0 8px rgba(57,255,20,0.35)`.
  - Inactive: `color: rgba(255,255,255,0.55)`.
  - Font: `var(--mantis-font-mono)`, 11px, letter-spacing 0.04em.
  - Selected timeframe is bound to a `WritableSignal<Timeframe>` and drives every child component.
- **Center:** `MANTIS · DASHBOARD` wordmark (mono, 10px, opacity 0.4, letter-spacing 0.28em, uppercase) — decorative only.
- **Right:** live clock `HH:MM:SS CET` + a red **KILL SWITCH** button (`emergencyPulse` animation, 2s red glow). The kill-switch triggers the existing stop flow in `paperStatus`/`trading.stop` (re-use whatever the current Stop action hits).

### 5.3 Cockpit spine (row 3)

Grid `2fr 1fr`, 400px tall.

**Left pane — Equity + drawdown chart**
- Use `<app-tv-chart [data]="equityLineData()" [overlay]="drawdownLineData()" [tooltipPoints]="equityTooltipPoints()">` — already in use in the current dashboard.
- Title: `Equity · <timeframe>` (mono, 10px, uppercase, letter-spacing 0.18em, opacity 0.55).
- Headline metric bottom-left of chart: `€{overview.equity}` in Plus Jakarta Sans 28px weight 700 + `{deltaPct}` signed, neon-green if positive.

**Right pane — KPI rail (vertical list)**
8 compact rows, each:
- 50px tall, `padding: 8px 10px`, `border-left: 2px solid <accent>`, `background: rgba(255,255,255,0.02)`.
- Row content (mono):
  - `<Label>` 9px uppercase letter-spacing 0.12em opacity 0.55
  - `<Value>` 16px weight 700, colored by sign/accent
  - `<Sub>` 9px opacity 0.5, small context (e.g. `258W · 154L · ▲ +1.8pp`)
- Labels + bindings:
  1. `Daily P&L` → `overview().daily_pnl`
  2. `Open positions` → `openPositionCount()` (already computed in existing `dashboard.component.ts`)
  3. `Unrealized P&L` → `totalUnrealizedPnl()`
  4. `Net Exposure €` → sum `size × level` of live positions
  5. `Drawdown %` → `riskStatus().current_drawdown_pct * 100` — accent turns red above 5%
  6. `Sharpe (30d)` → `performance().sharpe_ratio` (or extend backend if missing)
  7. `Win Rate` → `performance().win_rate`
  8. `Hit rate TP` → `performance().tp_hit_rate` (NEW backend field required, see §8.3)

### 5.4 Bottom row (row 4)

Grid `1fr 1fr 1.7fr`, ~260px tall.

**Duration × PnL scatter** (left)
- Scatter: x = trade duration (minutes), y = net € per trade. 180 dots.
- Dot color: green if closed in profit, red if in loss.
- Two medians drawn as horizontal dotted rules (`win 47m · +€38.20/h`, `loss 1h 08m · −€28.70/h`).
- Alert pill if `loss_avg_duration_min > win_avg_duration_min * 1.3`: yellow `⚠ loss dura +XX% del win · late-exit bias`.
- **Data source:** compute from `trading.paperTrades()` (filter closed, group by result). If backend doesn't expose duration yet, add it (`closed_at - opened_at`).

**Funding ring** (center)
- 96×96 SVG ring, stroke `#FFB020`, dasharray proportional to `|funding_rate_8h|` normalized to ±0.5%.
- Center text: `−0.04%` (current rate), subtitle `per 8h`.
- Right of ring: accumulated funding `€{cum_funding_7d}` in red/green by sign, then `BTC long 0.12 · €7,858 notional · next 04:38`.
- **Data source:** new service `FundingService` (or extend `trading.service`) hitting Bybit REST `/v5/market/funding/history` for active perp symbols. Values must update every 60s or on WS funding tick.

**Daily Heatmap · 90d** (right)
- Calendar-grid heatmap, one cell per day over the last 90 days. Cells colored by daily P&L sign + magnitude (green scale 0→neon, red scale 0→#FF3D57).
- Small stats in the top-right: `best +€1,408 · worst −€612`.
- Tooltip on hover: date + P&L + trade count.
- **Data source:** `trading.equityCurve()` — already has `daily_pnl` and `trade_count` per day (see `dashboard.component.ts` `equityTooltipPoints`).

### 5.5 TradeBreakdownComponent (row 5)

See **§8** below. This sits at the very bottom because it is a secondary KPI.

---

## 6. Deliverable A — `DashboardV2Component`

### 6.1 File layout

```
frontend/src/app/views/dashboard/
  dashboard.component.ts                // (keep for now; swap route or rename)
  dashboard-v2.component.ts             // NEW
  dashboard-v2.component.html           // NEW
  dashboard-v2.component.scss           // NEW
  operational-strip/
    operational-strip.component.ts      // Deliverable B
    operational-strip.component.html
    operational-strip.component.scss
  trade-breakdown/
    trade-breakdown.component.ts        // Deliverable C
    trade-breakdown.component.html
    trade-breakdown.component.scss
  kpi-rail/
    kpi-rail.component.ts               // right pane of cockpit spine
  cockpit-bottom/
    duration-scatter.component.ts
    funding-ring.component.ts
    calendar-heatmap.component.ts       // (reuse existing heatmap code if present)
```

### 6.2 State

- `timeframe = signal<Timeframe>('30D')` — shared via a tiny `TimeframeService` (injectable singleton) so every child reads from the same signal.
- Every child component `@Input({required:true}) tf!: Signal<Timeframe>` OR injects `TimeframeService` directly — pick one pattern and be consistent.

### 6.3 Routing

Add the new component to `dashboard/routes.ts` as the new root:
```ts
{ path: '', component: DashboardV2Component, title: 'Dashboard' }
```

---

## 7. Deliverable B — `OperationalStripComponent`

### 7.1 Visual

A horizontal 86px-tall strip of **6 tiles** with a 2px red left-border on the first tile (session-sensitive) and 2px neon-green top-accent on the rest. Grid `repeat(6, 1fr)`, gap 10px.

Each tile:
- `background: #161b22; border: 1px solid rgba(0,217,126,0.15); border-radius: 6px; padding: 10px 12px;`
- Top: `<label>` (mono, 9px, uppercase, letter-spacing 0.12em, opacity 0.55)
- Middle: main value (Plus Jakarta Sans, 20px, weight 700; mono if numeric)
- Bottom: subtitle (mono, 10px, opacity 0.55)

### 7.2 Tiles

| # | Label | Value | Data binding |
|---|-------|-------|--------------|
| 1 | **Session** | `LONDON · NY · open` + pulsing green dot | `marketStatus.currentMarketStatus()` |
| 2 | **Broker WS** | `LIVE · 42ms` + WS ping | `ws.connected` + `ws.latencyMs` (add if missing) |
| 3 | **Trades today** | `18` | `performance().daily_trade_count` (derive from `equityCurve` last row) |
| 4 | **Circuit breakers** | `0/6 tripped` · green, else red w/ `emergencyPulse` | `circuitBreakersTripped()` from existing component |
| 5 | **Paper bot** | `RUNNING` + uptime | `paperStatus()?.running`, `paperStatus()?.uptime_sec` |
| 6 | **Model** | `ML-Primary · v2.3` + last trained | `modelInfo()` — new service `AiModelService.currentModel()` or extend `performance` payload |

### 7.3 Behavior

- Live-refresh from the same polling interval the dashboard already uses (`10_000ms` when running, `60_000ms` idle — see existing `startSmartPolling()`).
- Reduced-motion kills the pulse dots (`@media (prefers-reduced-motion: reduce)`).

### 7.4 Isolated mock

See `mocks/OperationalStrip.jsx` (the `OperationalStrip` export — rendered standalone, not inside the dashboard).

---

## 8. Deliverable C — `TradeBreakdownComponent` (per-day)

### 8.1 Purpose

Secondary KPI. For the selected timeframe, shows **each day as a column**. Each column has:
- **Above zero:** BUY trades stacked, segmented TP (green) / Going (cyan) / SL (red).
- **Below zero:** SELL trades stacked, same segmentation mirrored.
- Hover/tap a column → focus panel on the right shows that day's exact counts + day P&L + open-trades warning.

### 8.2 Visual

- Card: `background: #161b22; border: 1px solid rgba(0,217,126,0.15); border-radius: 6px; padding: 10px 12px;`
- Grid inside: `1fr 200px` (chart / focus readout).
- Chart: flex row of `days.length` columns, 1px gap. Each column is a flex-column with BUY segments (stacked above zero axis) and SELL segments (below).
- Zero axis: 1px `rgba(255,255,255,0.2)` horizontal line between the two halves.
- Heights: H = 110px per side (so the chart region = 220px + 1px axis).
- Segment colors: TP `#39FF14` (inset glow `rgba(57,255,20,0.35)`), Going `#00E5FF` (inset glow `rgba(0,229,255,0.35)`), SL `#FF3D57`.
- Hover highlight: column background `rgba(255,255,255,0.04)`, TP segment gets extra outer glow.
- x-axis labels: sparse — first date, middle date (only if > 14 days), last date `· today`. Mono 9px opacity 0.35.

### 8.3 Data shape (what to ask from the backend)

```ts
// Extend GET /performance response (or new GET /performance/breakdown?tf=30D)
interface TradeBreakdownDay {
  date: string;            // 'YYYY-MM-DD'
  buy:  { tp: number; sl: number; going: number; pnl: number };
  sell: { tp: number; sl: number; going: number; pnl: number };
}
interface TradeBreakdownResponse {
  timeframe: Timeframe;
  days: TradeBreakdownDay[];   // ordered oldest→newest, weekends included with zero counts
}
```

- `tp` = trade closed hitting take-profit (positive outcome).
- `sl` = trade closed hitting stop-loss (negative outcome).
- `going` = trade still open at end-of-day (only non-zero for today).
- `pnl` = realized + unrealized net EUR for that direction on that day.

If the backend cannot deliver this aggregate, derive it client-side from `paperTrades()` + `paperPositions()` — group by date-UTC, direction, and outcome. **Do not leave the mock `BREAKDOWN_30` / `BREAKDOWN_90` arrays in.**

### 8.4 Behavior

- `@Input({required:true}) tf!: Signal<Timeframe>` — re-compute days on tf change.
- Default focus = last day (today).
- Hover → updates focus panel; on touch devices, tap = focus.
- Focus panel shows:
  - Date (`Ven 22 apr`)
  - `▲ BUY N` with `TP x · Go x · SL x`
  - `▼ SELL N` with `TP x · Go x · SL x`
  - Day P&L (big, 18px, signed, color by sign, neon glow if positive)
  - If `buy.going + sell.going > 0`: info pill `⏱ N trade ancora aperte` (cyan left-border 2px, `rgba(0,229,255,0.08)` bg).
- If no trades for the day (weekend/idle): columns render as empty padding; focus shows `— no trades`.

### 8.5 Isolated mock

See `mocks/TradeBreakdown.jsx` — the `TradeBreakdownB` export is the target. `TradeBreakdownA` is an alternative laddered layout we rejected; ignore.

---

## 9. Design tokens (authoritative)

**Use the SCSS variables from `frontend/src/scss/_palette.scss` / `_custom.scss`.** This table is only for parity:

| Token | Hex | Role |
|-------|-----|------|
| `--mantis-neon` | `#39FF14` | Profit, TP, active state |
| `--mantis-green` | `#00d97e` | Brand primary, card border accent |
| `--mantis-danger` | `#FF3D57` | Loss, SL, drawdown |
| `--mantis-warning` | `#FFB020` | Funding exposure, late-exit bias |
| `--mantis-info` | `#00E5FF` | Going / in-flight / predicted |
| `--mantis-bg` | `#0d1117` | App background (Variant B uses `#0a0e13` for slightly-darker canvas) |
| `--mantis-surface-2` | `#161b22` | Cards |
| Border accent | `rgba(0,217,126,0.15)` | Default card border |
| Border strong | `rgba(57,255,20,0.3)` | Focused/hover |

**Typography**
- Sans: `var(--mantis-font-sans)` — Plus Jakarta Sans (400/500/600/700/800).
- Mono: `var(--mantis-font-mono)` — IBM Plex Mono with `font-feature-settings: "tnum" 1, "zero" 1` always on for numeric cells.
- Sizes used: 9 (micro label), 10, 11, 13, 14 (body), 16 (KPI sub-value), 20 (KPI value), 28 (hero number).
- Letter-spacing: 0.04em (tabs), 0.08em (badges), 0.12em (labels), 0.18em (section headers), 0.28em (decorative wordmark).

**Spacing** — 4px base scale: 4, 6, 8, 10, 12, 14, 16, 24.
**Radii** — 4 (pills), 6 (cards default in this design), 8 (global card), 100px (pills).
**Shadows / glows** — only on active / emergency states. Do not add shadows to static cards.

---

## 10. Animations

| Name | Duration | Easing | Used on |
|------|----------|--------|---------|
| `pulse-glow` | 2s infinite | ease-in-out | Live WS dot, Session dot, Bot RUNNING dot |
| `emergency-pulse` | 2s infinite | ease-in-out | Kill switch button, Circuit-breakers tile if tripped |
| `value-flash` | 600ms | ease-out | KPI rail cells on value change (green wipe if Δ>0, red if Δ<0) |
| `fade-slide-up` | 250ms | `cubic-bezier(.16,1,.3,1)` | Dashboard mount, staggered 50ms per row |

All animations must respect `@media (prefers-reduced-motion: reduce)` — force `animation-duration: 0.01ms !important`.

---

## 11. Interactions

- **Timeframe tabs** → updates `TimeframeService.current`; every child re-computes via `computed()`/`effect()`.
- **KPI rail row click** → navigates to the related detail view (daily P&L → `/performance`, open positions → `/positions`, etc.). Use `routerLink`.
- **TradeBreakdown column hover** → local signal `focusedDay`.
- **Kill switch** → existing confirm-dialog flow from `ConfirmDialogService`, then `trading.stopPaper()` (or whatever method the current Stop button already uses — reuse it).
- **Circuit-breakers tile click** → scroll/anchor to existing CB reset UI on the same page.

---

## 12. Responsive

- ≥1280px: the layout above.
- 768–1279px: rows 3, 4, 5 each collapse to 1 column; rail moves below the chart; bottom triplet stacks.
- <768px: single column everywhere; TradeBreakdown reduces x-axis density (show only last 14 days, allow horizontal scroll for more). Min touch target 44px.

---

## 13. Files in this bundle

```
design_handoff_dashboard_v2/
  README.md                           ← this file
  mocks/
    index.html                        ← entry point, open in a browser to preview
    colors_and_type.css               ← design-system tokens (mirror of the Angular SCSS)
    design-canvas.jsx                 ← canvas frame (ignore — presentation only)
    Shared.jsx                        ← Label + helpers
    OperationalStrip.jsx              ← Deliverable B mock
    TradeBreakdown.jsx                ← Deliverable C mock (use TradeBreakdownB export)
    VariantB_Ambitious.jsx            ← Deliverable A mock (the full page)
    VariantA_Conservative.jsx         ← rejected, ignore
  assets/
    mantis-eyes.svg                   ← favicon / brand mark
```

Open `mocks/index.html` in any browser to see both variants side-by-side. Variant B is the target.

---

## 14. Definition of Done (non-negotiable)

The handoff is **DONE** only when **all three** deliverables satisfy every row below:

| Check | A (DashboardV2) | B (OperationalStrip) | C (TradeBreakdown) |
|-------|:---:|:---:|:---:|
| Replaces/routes over the current dashboard | ✓ | — | — |
| Every number reads from a live service (no `const MOCK = …`) | ✓ | ✓ | ✓ |
| Uses `:root` CSS vars from `_palette.scss` (no hex literals in component SCSS except for unavoidable SVG fills) | ✓ | ✓ | ✓ |
| Respects `prefers-reduced-motion` | ✓ | ✓ | ✓ |
| Is responsive down to 360px wide | ✓ | ✓ | ✓ |
| Passes existing dashboard `*.spec.ts` patterns (add new specs mirroring `dashboard.component.spec.ts` if present) | ✓ | ✓ | ✓ |
| No new runtime deps beyond `@coreui/*` + existing shared components | ✓ | ✓ | ✓ |

If a data field doesn't exist on the backend yet (TP/SL/Going breakdown, funding accumulation, WS latency, model info, sharpe), **surface it as a TODO at the top of the component** with the exact shape needed, and render the tile in a skeleton/empty state — **do not** fabricate placeholder numbers.

---

## 15. Contacts / questions

Any ambiguity in measurements, copy, or binding — open the mocks in a browser first, then ask. Do not guess.
