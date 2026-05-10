# Frontend Audit — Synthesized Review (2026-05-10)

Aggregated from 5 parallel surfaces:
- 01-core.md (Core layer)
- 02-views-cockpit3.md (Dashboard v2 + Paper Trading + Positions)
- 03-views-other.md (12 remaining views)
- 04-shared-scss.md (Shared components + global SCSS)
- 05-cross-cutting.md (RxJS/OnPush/DestroyRef/ts-strict/console.log/mock-data sweep)

## Aggregate stats (deduped)
- Files reviewed: ~140
- Findings (deduped): **42** — CRITICAL: **6** | HIGH: **17** | MEDIUM: **15** | LOW: **4**

## Severity philosophy
- **CRITICAL** — production functional bug, security risk, or hard CLAUDE.md invariant violation with runtime impact.
- **HIGH** — convention violation with measurable side-effect, missing OnPush, raw HttpClient, anti-pattern with documented past incident.
- **MEDIUM** — style inconsistency, missing tokens, unscoped selectors, missing aria, missing mantis-mono.
- **LOW** — magic numbers, untyped parameters, dead TODOs.

---

## CRITICAL (6)

### C1 — `registerLogoutTeardown` never called → both WebSockets reconnect after logout
**Source**: 01-core.md C1-CORE
**Files**: `frontend/src/app/app.component.ts` + `frontend/src/app/core/services/auth.service.ts:184-189`

`AuthService.clearAuth()` calls `this._wsLazy?.disconnect()` and `this._notifLazy?.disconnectWs()`, but the lazy refs are populated only via `registerLogoutTeardown()`. **Grep confirms it's never called anywhere.** H1-FE/H2-FE fixes from prior session are dead code without the wiring. After logout, both WebSockets stay connected and auto-reconnect.

**Fix**: Wire in `AppComponent.ngOnInit()`:
```typescript
readonly #authService = inject(AuthService);
readonly #notifCenter = inject(NotificationCenterService);

ngOnInit(): void {
  this.#authService.registerLogoutTeardown({ ws: this.#ws, notif: this.#notifCenter });
}
```

---

### C2 — Trading Invariant #2 violated in legacy Dashboard
**Source**: 02-views-cockpit3.md C1-VIEWS-COCKPIT3
**File**: `frontend/src/app/views/dashboard/dashboard.component.ts:163-170`

`allLivePositions` falls through to `(currentPrice - pos.level) * pos.size` when `pos.upl == null`. Sibling views correctly return `live_pnl: 0`. CLAUDE.md Trading Invariant #2 forbids this arithmetic.

**Fix**: Remove fallback branch; return `{ ...pos, live_pnl: 0 }`.

---

### C3 — `trade-journal` `openPositionsByEpic` keyed by epic, not deal_id
**Source**: 03-views-other.md C2-VIEWS-OTHER
**File**: `frontend/src/app/views/trade-journal/trade-journal.component.ts:358-366`

Documented invariant violation (badge bug `dea2a29`). Two positions on same epic → wrong direction/size/level used for live P&L computation.

**Fix**: Key by `deal_id`, carry `epic` in value, search-by-epic + timestamp proximity.

---

### C4 — Untokenized hex `#ffa726`/`#ef5350` in risk-badges
**Source**: 04-shared-scss.md C1-SHARED
**File**: `_components.scss:192-201, 220-221`

Hardcoded outside `_palette.scss`. Palette already defines `$mantis-warning: #FFB020` and `$mantis-loss: #FF3D57` for these semantic roles.

**Fix**: Replace with token references.

---

### C5 — Epic-logo neon-green large fill
**Source**: 04-shared-scss.md C2-SHARED
**File**: `frontend/src/app/shared/components/epic-logo/epic-logo.component.ts:63-72`

`background-color: var(--mantis-neon, #39ff14)` fills 32×32 to 96×96 placeholder. Violates CLAUDE.md "neon = accent only".

**Fix**: Use `var(--mantis-surface-3)` for bg, neon for text only.

---

### C6 — Fictional CSS var `--cui-mantis-green` never resolves
**Source**: 04-shared-scss.md C3-SHARED
**File**: `frontend/src/app/shared/components/news-widget/news-widget.component.scss:67`

`--cui-mantis-green` not defined anywhere. Always falls through to literal hex fallback `#00d97e`.

**Fix**: `color: var(--mantis-green);`

---

## HIGH (17)

### H1 — `refreshTokenSubject.complete()` silently drops queued 401-retry requests
**Source**: 01-core.md H2-CORE
**File**: `frontend/src/app/core/interceptors/auth.interceptor.ts:31-36`

**Fix**:
```typescript
try { refreshTokenSubject.error(new Error('Session terminated')); } catch { /* already errored */ }
refreshTokenSubject = new BehaviorSubject<string | null>(null);
```

### H2 — `logout()` clears state AFTER backend round-trip
**Source**: 01-core.md H3-CORE
**File**: `frontend/src/app/core/services/auth.service.ts:130-138`

200-500ms window with stale auth. Double-click race corrupts interceptor state.

**Fix**: Optimistic local state clear before HTTP call.

### H3 — `MarketStatusService.getMultiStatus()` allocates new computed() per call
**Source**: 01-core.md H4-CORE
**File**: `frontend/src/app/core/services/market-status.service.ts:84-96`

Unbounded signal-graph growth.

**Fix**: Expose readonly cache snapshot; let callers derive locally.

### H4 — Raw HttpClient in 4 services (deduped C1-VIEWS-OTHER + H1-CORE + Pattern-7)
**Files**:
- `news.service.ts:7,22`
- `monitoring.service.ts:2,130`
- `notification-center.service.ts:2,14`
- `market-status.service.ts:2,24`

> **Correction**: 03-views-other agent claimed this "bypasses auth interceptor". **False** — `app.config.ts` registers `provideHttpClient(withInterceptors([...]))`, applies to ALL HttpClient injections. Severity: convention violation (HIGH), not security hole (CRITICAL).

**Fix**: Add `ApiService.delete<T>()` first, migrate the 4 services.

### H5 — `effect()` triggers HTTP fetch (markets)
**Source**: 03-views-other.md H1-VIEWS-OTHER
**File**: `frontend/src/app/views/markets/markets.component.ts:215-220`

**Fix**: Move `getNews()` call from effect to `selectAsset()` action handler.

### H6 — `effect()` writes signal without `queueMicrotask` (ai-models)
**Source**: 03-views-other.md H2-VIEWS-OTHER
**File**: `frontend/src/app/views/ai-models/ai-models.component.ts:493-498`

**Fix**: `queueMicrotask(() => this.trading.trainingStatus.set(update));`

### H7 — `saveConfig()` / `saveLimits()` silent on error (strategy)
**Source**: 03-views-other.md H3-VIEWS-OTHER
**File**: `frontend/src/app/views/strategy/strategy.component.ts:127-136`

**Fix**: Add `next`/`error` handlers via ToastService.

### H8 — Hardcoded hex in Chart.js datasets (performance + correlation-heatmap)
**Source**: 03-views-other.md H4-VIEWS-OTHER, dedupe Pattern-9
**Files**:
- `performance.component.ts:135,185`
- `correlation-heatmap.component.ts:124,128`
- Template bindings: `backtest.component.ts:307`, `dashboard.component.html:218`, `performance.component.html:140`, `dashboard-v2.component.html:104`

**Fix**: Create `frontend/src/app/shared/constants/chart-colors.ts` with palette-synced exports.

### H9 — Unjustified `!important` (system-logs + news)
**Source**: 03-views-other.md H5+H6-VIEWS-OTHER
**Files**:
- `system-logs.component.scss:156`
- `news.component.scss:46, 110`

**Fix**: Increase specificity (`:host table tbody tr:hover`).

### H10 — Inline `[style.height.px]` + `Math` exposure (performance)
**Source**: 03-views-other.md H7-VIEWS-OTHER
**File**: `frontend/src/app/views/performance/performance.component.html:182`

**Fix**:
```typescript
readonly assetChartHeight = computed(() => Math.max(280, this.pnlByAsset().length * 28));
```

### H11 — Non-CoreUI inline SVG icons (news)
**Source**: 03-views-other.md H8-VIEWS-OTHER
**File**: `frontend/src/app/views/news/news.component.html:37-39, 82-85`

**Fix**: Replace with `<svg cIcon name="cilNewspaper">` etc. Add `IconDirective` to imports.

### H12 — Missing OnPush in 9 components (deduped 04-shared + Pattern-3)
**Components**:
1. `app.component.ts`
2. `default-layout.component.ts`
3. `default-footer.component.ts`
4. `user-dropdown.component.ts`
5. `bottom-nav.component.ts`
6. `avatar.component.ts`
7. `avatar-upload.component.ts`
8. `views/pages/page404/page404.component.ts`
9. `views/pages/page500/page500.component.ts`

**Fix**: Add `changeDetection: ChangeDetectionStrategy.OnPush` to each. Mechanical migration.

### H13 — Wrong dark-mode media query hook (user-dropdown)
**Source**: 04-shared-scss.md H4-SHARED
**File**: `user-dropdown.component.scss:144`

`@media (prefers-color-scheme: dark)` doesn't fire on UI toggle. App uses `[data-coreui-theme]` everywhere else.

**Fix**: `[data-coreui-theme="dark"] { ... }`

### H14 — Fixed pixel `max-height: 600px` on news-grid
**Source**: 04-shared-scss.md H5-SHARED
**File**: `news-widget.component.scss:5`

**Fix**: `max-height: 60vh;`

### H15 — `#00ff88` hardcoded in `_auth.scss:93`
**Source**: 04-shared-scss.md H6-SHARED

**Fix**: `background: radial-gradient(circle, $mantis-green, transparent);`

### H16 — `openPosition`/`swapEpic` lookup by epic only (cockpit-3)
**Source**: 02-views-cockpit3.md H2+H3-VIEWS-COCKPIT3
**Files**:
- `dashboard-v2/cockpit-bottom/overnight-swap.component.ts:73`
- `dashboard-v2/dashboard-v2.component.ts:105`

**Fix**: Filter `&& p.upl != null`, prefer most-recent `opened_at` for same-epic disambiguation.

### H17 — `pnlPct` price arithmetic for non-USD-quote (paper-trading)
**Source**: 02-views-cockpit3.md H4-VIEWS-COCKPIT3
**File**: `paper-trading.component.ts:593-595`

USDJPY shows incorrect %.

**Fix**: `(upl / (entry * size)) * 100`.

---

## MEDIUM (15)

### M1 — `getNews()` `isLoading` stuck on edge errors
**Source**: 01-core.md M1-CORE  
**Fix**: Explicit error callback in subscribe.

### M2 — `ApiService` `params as any`
**Source**: 01-core.md M2-CORE  
**Fix**: Build HttpParams via String() loop; type as `Record<string, string|number|boolean>`.

### M3 — `NotificationCenterService.init()` duplicate REST calls
**Source**: 01-core.md M3-CORE  
**Fix**: `if (this.initialized) return;` guard.

### M4 — `effect()` writes signal without `queueMicrotask` (BotVitalsPanel)
**Source**: 02-views-cockpit3.md H1 (downgraded — borderline)
**File**: `bot-vitals-panel.component.ts:73-84`

### M5 — Hardcoded `#0d1117` (dashboard-v2)
**Source**: 02-views-cockpit3.md M1  
**Fix**: `var(--mantis-surface-1)`.

### M6 — `rgba(57,255,20,...)` literals (dashboard-v2)
**Source**: 02-views-cockpit3.md M2  
**Fix**: `color-mix(in srgb, var(--mantis-neon) X%, transparent)`.

### M7 — `font-size: 1.05rem` (dashboard.component.scss)
**Source**: 02-views-cockpit3.md M3  
**Fix**: Use `var(--mantis-fs-md)` token.

### M8 — `pos.direction === 'SHORT'` mismatch (overnight-swap)
**Source**: 02-views-cockpit3.md M4  
Capital.com emits `'SELL'`. Swap tile shows long rate for SELL positions.  
**Fix**: `dir === 'SELL' || dir === 'SHORT'`.

### M9 — KPI values missing `mantis-kpi` class (performance)
**Source**: 03-views-other.md M1  
**File**: `performance.component.html:26,35,47,63`

### M10 — Service injection not `readonly` (system-logs)
**Source**: 03-views-other.md M3

### M11 — Fixed `max-height: 700px` on news-list
**Source**: 03-views-other.md M4  
**Fix**: `max-height: min(700px, 80vh);`

### M12 — `1.05rem` literal in markets.component.scss
**Source**: 03-views-other.md M5

### M13 — `color: #000` in audit-drawer
**Source**: 04-shared-scss.md M1

### M14 — `#ff6b7a`/`#dc3545`/`#ffc107` in `_auth.scss`
**Source**: 04-shared-scss.md M2+M3

### M15 — Visual-timing `setTimeout` (notification-dropdown + avatar-upload)
**Source**: 05-cross-cutting Pattern-11
- `notification-dropdown.component.ts:40` — 600ms shake → use CSS `animationend`
- `avatar-upload.component.ts:261` — 3000ms success → use CSS `transitionend`

---

## LOW (4)

### L1 — `permissionGuard` fail-open on misconfigured route data
**Source**: 01-core.md L1-CORE  
**Fix**: Return false + redirect to `/403`.

### L2 — Legacy mock-data dead file
**Source**: 05-cross-cutting Pattern-2  
**File**: `frontend/src/app/views/dashboard/dashboard-charts-data.ts`  
**Fix**: Delete (not imported anywhere).

### L3 — `Record<string, any>` untyped params (notifications)
**Source**: 03-views-other.md L3

### L4 — `epic-colors.ts` ↔ `logo.service.ts` ACCENT_MAP duplication
**Source**: 05-cross-cutting Notes  
**Fix**: Single source of truth `epic-colors.ts`.

---

## Findings deferred / out-of-scope

- `trade-journal.component.scss:235,244` raw RGBA in row tints — `!important` justified, RGBA cosmetic. (LOW noise, defer.)
- `news.component.ts:33` `30_000` ms magic number — extract to constant when convenient.
- `register.component.ts:157` 2000ms redirect setTimeout — borderline; toast + immediate navigate would be cleaner.
- ts-strict `(x: any)` in `signals.component.ts:173-186` — type the signal properly when scoping next refactor.
- Toast container `z-index: 1090` — documented exception, add named carve-out in CLAUDE.md.

---

## Clean areas
- ✅ No `console.log` in production code
- ✅ No mock data runtime-active (only dead-code remnant)
- ✅ No RxJS subscription leaks (`takeUntilDestroyed` everywhere)
- ✅ No deprecated APIs (`provideRouter`, `withFetch`, `color.adjust()` all correct)
- ✅ No `lighten()`/`darken()` SASS calls
- ✅ All `@for` use `track`
- ✅ Settings, Signals, User-Profile views are clean

---

## Fix sequencing for atomic-commit execution

**T1 — auth/WS critical** (single commit)
- C1, H1, H2 (auth.service + interceptor + AppComponent wiring)

**T2 — Trading Invariant + livePosition fixes** (single commit)
- C2 (legacy dashboard arithmetic)
- C3 (trade-journal deal_id keying)
- H16 (cockpit-3 epic-only lookups)
- H17 (paper-trading pnlPct FX)

**T3 — design tokens + neon-large-area** (single commit)
- C4 (risk-badge tokens)
- C5 (epic-logo bg)
- C6 (cui-mantis-green typo)
- H13 (data-coreui-theme dark hook)
- H14 (news-grid max-height)
- H15 (auth.scss #00ff88)
- M5, M6, M7, M11, M12, M13, M14 (token sweep)

**T4 — chart colors palette constants** (single commit)
- H8 + M9 + L4 (chart-colors.ts + dedupe + mantis-kpi class)

**T5 — raw HttpClient migration** (single commit)
- H4 (4 services + ApiService.delete)
- M2 (ApiService params typing)

**T6 — OnPush sweep** (single commit)
- H12 (9 components)

**T7 — view-level cleanups** (single commit)
- H5, H6, H7, H9, H10, H11
- M1, M3, M4, M8, M10, M15

**T8 — LOW + dead code** (single commit)
- L1, L2, L3
