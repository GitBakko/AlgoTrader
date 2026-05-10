# Frontend Audit — Views Other (12 pages) — 2026-05-10

## Stats
- Total findings: 18 (CRITICAL: 2, HIGH: 8, MEDIUM: 5, LOW: 3)

> **NOTE on C1-VIEWS-OTHER**: agent claimed raw HttpClient "bypasses auth interceptor". This is **incorrect**: `app.config.ts` registers `provideHttpClient(withInterceptors([authInterceptor, requestIdInterceptor]))`, so interceptors apply to ALL HttpClient injections. Severity downgraded to **HIGH** (convention violation, not security hole) and merged with H1-CORE in synth phase.

---

## CRITICAL

### C1-VIEWS-OTHER (downgraded → HIGH, see note above): `MonitoringService` uses raw `HttpClient` — system-logs
**File**: `frontend/src/app/core/services/monitoring.service.ts:130`

Already covered by H1-CORE. Same root: raw HttpClient injection bypasses ApiService convention. Interceptors STILL FIRE (verified `app.config.ts`).

### C2-VIEWS-OTHER: `openPositionsByEpic` keys by `epic` not `deal_id` — trade-journal
**File**: `frontend/src/app/views/trade-journal/trade-journal.component.ts:358-366`
**Confidence**: 92

```typescript
map.set(pos.epic, { direction: pos.direction, size: pos.size, level: pos.level, ... });
```

CLAUDE.md: "livePosition lookups MUST match by `deal_id`, not `epic`" (badge bug `dea2a29`). If two positions on same epic exist (close-detection lag, same-epic re-entry), `getPositionInfo()` at line 663 returns whichever iteration order yields. Older signal's displayed P&L computed against wrong position's direction/size/level.

**Fix**: Key by `deal_id`, carry `epic` in value:
```typescript
map.set(pos.deal_id, { epic: pos.epic, direction: pos.direction, size: pos.size, level: pos.level, opened_at: pos.opened_at ?? null });
// In getPositionInfo: search map.values() where v.epic === sig.epic, then apply timestamp proximity
```

---

## HIGH

### H1-VIEWS-OTHER: `effect()` triggers HTTP side-effect — markets
**File**: `frontend/src/app/views/markets/markets.component.ts:215-220`

```typescript
effect(() => {
  const epic = this.selectedEpic();
  if (epic) { this.newsService.getNews(epic, 5, 7); }
});
```

CLAUDE.md anti-pattern. `selectAsset()` is already the action handler.

**Fix**: Remove effect, move call to `selectAsset()`.

### H2-VIEWS-OTHER: `effect()` writes signal without `queueMicrotask` — ai-models
**File**: `frontend/src/app/views/ai-models/ai-models.component.ts:493-498`

```typescript
effect(() => {
  const update = this.ws.trainingUpdate();
  if (update) { this.trading.trainingStatus.set(update); }
});
```

Documented loop pattern (`history-tab infinite-loop bug 1cdd48f`).

**Fix**: `queueMicrotask(() => this.trading.trainingStatus.set(update));`

### H3-VIEWS-OTHER: `saveConfig()` / `saveLimits()` silent on error — strategy
**File**: `frontend/src/app/views/strategy/strategy.component.ts:127-136`

`.subscribe()` calls have no error/next handlers. Failed save invisible.

**Fix**: Use ToastService for next/error feedback.

### H4-VIEWS-OTHER: Hardcoded hex in Chart.js datasets — performance + correlation-heatmap
**Files**:
- `frontend/src/app/views/performance/performance.component.ts:135,185`
- `frontend/src/app/views/performance/correlation-heatmap.component.ts:124,128`

`'rgba(57, 255, 20, 0.7)'` (neon) and `'rgba(255, 61, 87, 0.7)'` (loss) hardcoded.

**Fix**: Create `frontend/src/app/shared/constants/chart-colors.ts` with palette-synced exports.

### H5-VIEWS-OTHER: `!important` on user-authored hover rule — system-logs
**File**: `frontend/src/app/views/system-logs/system-logs.component.scss:156`
**Fix**: Increase specificity (`:host table tbody tr:hover`).

### H6-VIEWS-OTHER: Unjustified `!important` in news.component.scss
**File**: `frontend/src/app/views/news/news.component.scss:46,110`

(Line 85 IS acceptable — overrides CoreUI badge color.)

**Fix**: Drop `!important` from L46 and L110.

### H7-VIEWS-OTHER: Inline `[style.height.px]` binding in performance template
**File**: `frontend/src/app/views/performance/performance.component.html:182`

Requires `readonly Math = Math` exposure on class.

**Fix**:
```typescript
readonly assetChartHeight = computed(() => Math.max(280, this.pnlByAsset().length * 28));
```

### H8-VIEWS-OTHER: Non-CoreUI inline SVG icons — news
**File**: `frontend/src/app/views/news/news.component.html:37-39, 82-85`

**Fix**:
```html
<svg cIcon name="cilNewspaper" size="xl" class="mb-3"></svg>
<svg cIcon name="cilClock" size="sm" class="me-1"></svg>
```
Add `IconDirective` to imports.

---

## MEDIUM

### M1-VIEWS-OTHER: KPI values missing `mantis-mono`/`mantis-kpi` — performance
**File**: `frontend/src/app/views/performance/performance.component.html:26,35,47,63`

**Fix**: `<div class="dash-kpi-card__value mantis-kpi">`.

### M2-VIEWS-OTHER: Hardcoded hex in `<app-tv-chart>` input — backtest + performance
**Files**:
- `frontend/src/app/views/backtest/backtest.component.ts:307`: `lineColor="#00d97e"`
- `frontend/src/app/views/performance/performance.component.html:141`: `lineColor="#00d97e"`

**Fix**: Extract to `chart-colors.ts` constant `CHART_GREEN = '#00d97e'`.

### M3-VIEWS-OTHER: Service injection not `readonly` — system-logs
**File**: `frontend/src/app/views/system-logs/system-logs.component.ts:38,48-56`

**Fix**: Use `private readonly` consistently.

### M4-VIEWS-OTHER: Fixed `max-height: 700px` on `.news-list` — news
**File**: `frontend/src/app/views/news/news.component.scss:2`
**Fix**: `max-height: min(700px, 80vh);`

### M5-VIEWS-OTHER: `1.05rem` literal font-size — markets
**File**: `frontend/src/app/views/markets/markets.component.scss:31`
**Fix**: Use `var(--mantis-fs-lg)`.

---

## LOW

### L1-VIEWS-OTHER: Hard-coded `rgba(255, 61, 87, ...)` in trade-journal row tints
**File**: `frontend/src/app/views/trade-journal/trade-journal.component.scss:235,244`

`!important` IS acceptable (overrides CoreUI striped zebra). Raw RGBA values should use `var(--mantis-loss)`.

### L2-VIEWS-OTHER: Magic number `30_000` ms polling — news
**File**: `frontend/src/app/views/news/news.component.ts:33`
**Fix**: `const NEWS_POLL_INTERVAL_MS = 30_000;`

### L3-VIEWS-OTHER: `Record<string, any>` untyped params — notifications
**File**: `frontend/src/app/views/notifications/notifications.component.ts:61`
**Fix**: `Record<string, string | number | boolean>`.

---

## Summary by Page

| Page | Severity | Key Issue |
|------|----------|-----------|
| system-logs | H (down from C1), H5, M3 | Raw HttpClient (convention only — interceptor fires) |
| trade-journal | **C2**, L1 | `epic`-keyed position map violates `deal_id` invariant |
| markets | H1, M5 | `effect()` triggering HTTP call |
| ai-models | H2 | `effect()` writing signal without `queueMicrotask` |
| strategy | H3 | Silent errors on save |
| performance | H4, H7, M1, M2 | Hardcoded hex; inline style; missing mantis-kpi |
| backtest | M2 | Hardcoded hex `#00d97e` in @Input |
| news | H6, H8, M4, L2 | `!important`; non-CoreUI SVGs; fixed height; magic number |
| notifications | L3 | Untyped params |
| settings | — | Clean |
| signals | — | Clean |
| user-profile | — | Clean |
