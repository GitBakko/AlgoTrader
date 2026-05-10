# Frontend Audit — Cross-Cutting (2026-05-10)

## Stats
- Patterns checked: 14
- Components scanned: 61
- Total findings: 38 (CRITICAL: 1, HIGH: 14, MEDIUM: 23, LOW: 0)

---

## Pattern 1 (CRITICAL): console.log
**Result**: CLEAN — 0 occurrences in production `.ts`.

---

## Pattern 2 (CRITICAL): Mock Data Invariant
**Occurrences**: 1 dead-code only

`frontend/src/app/views/dashboard/dashboard-charts-data.ts:27-48` — `DashboardChartsData.random()` generates random ints; `initMainChart()` builds three datasets of random values with static month labels — full synthetic chart data.

**Assessment**: Class is `@Injectable({ providedIn: 'any' })` but NOT imported anywhere (grep returns only its own declaration). Dead legacy code from CoreUI template. Runtime impact zero today, but must be deleted to prevent accidental re-import.

**Fix**: Delete `frontend/src/app/views/dashboard/dashboard-charts-data.ts`.

---

## Pattern 3 (HIGH): Missing OnPush
**Occurrences**: 9 components
1. `app.component.ts` — root shell
2. `default-layout.component.ts` — layout wrapper
3. `default-footer.component.ts`
4. `user-dropdown.component.ts`
5. `bottom-nav.component.ts`
6. `avatar.component.ts`
7. `avatar-upload.component.ts`
8. `views/pages/page404/page404.component.ts`
9. `views/pages/page500/page500.component.ts`

(Items 2-5 also flagged in 04-shared-scss.md — dedupe in synth.)

**Fix**: Add `changeDetection: ChangeDetectionStrategy.OnPush` to each. All use signals or static templates — mechanical migration.

---

## Pattern 4 (HIGH): RxJS Subscription Leaks
**Result**: CLEAN — all component subscriptions use `takeUntilDestroyed`. Service-level one-shot HTTP no leak.

---

## Pattern 5 (HIGH): Signal-Effect Infinite-Loop Risk
**Result**: CLEAN — all 14 `effect()` calls reviewed; none read+write same signal without `queueMicrotask` deferral.

> Note: Cross-cutting agent disagrees with cockpit-3 agent on `bot-vitals-panel.component.ts:73` (cross-cutting says safe, cockpit-3 says HIGH). Reason: cockpit-3 agent flagged it because effect reads heartbeat input + writes `beating` synchronously, deviating from project pattern. Cross-cutting accepts as safe because reads `heartbeat()` (input), writes `beating` (different signal). **Verdict**: borderline; flag as MEDIUM (style consistency) not HIGH.

---

## Pattern 6 (HIGH): TypeScript Strict Gaps
**Occurrences**: 15

`as any` casts in production logic:
1-4. `signals.component.ts:173,177,179,186` — `(x: any)` in filter/reduce/forEach (signals() untyped)
5-6. `trade-journal.component.ts:442,443` — `(a as any)[field]` dynamic sort key
7. `trade-journal.component.ts:542` — `errorTooltip(detail: any)`
8-9. `api.service.ts:14,32` — `params as any`
10-11. `tv-chart.component.ts:122,211` — lightweight-charts typing limitation (Golden Rule: don't touch)
12-13. `signal-audit-drawer.component.ts:352,393` — `formatValue(val: any)`, `gateDetail(key: string, gate: any)`
14-15. `performance.component.ts:158,159,201` — Chart.js tooltip callback params

**Fix**: Type `signals()` properly; refine `trade-journal` sort with keyof; replace `api.service.ts` `params as any` with HttpParams build (covered by M2-CORE).

---

## Pattern 7 (HIGH): Raw HttpClient Bypassing ApiService
**Occurrences**: 4 services
1. `news.service.ts:7,22`
2. `monitoring.service.ts:2,130`
3. `notification-center.service.ts:2,14`
4. `market-status.service.ts:2,24`

(Auth.service.ts excluded — Golden Rule.)

**Fix**: Add `ApiService.delete<T>()` first; migrate 4 services. Already covered by H1-CORE.

---

## Pattern 8 (MEDIUM): ViewChild for Styling
**Result**: CLEAN — only `tv-chart` ViewChild for library mount (legitimate).

---

## Pattern 9 (MEDIUM): Hardcoded Hex Colors
**High volume — grouped:**

**Asset brand colors (separate concern, external standards):**
- `epic-colors.ts:9-29` — 19 brand hexes
- `logo.service.ts:115-126` — duplicate ACCENT_MAP

**Chart component input defaults (Golden Rule — tv-chart.component.ts protected):**
- `tv-chart.component.ts:79,82,83` — `lineColor`/`upColor`/`downColor` defaults

**Template bindings passing hex to inputs (ACTIONABLE):**
- `backtest.component.ts:307`
- `dashboard.component.html:218`
- `performance.component.html:140`
- `dashboard-v2.component.html:104`

**Inline SVG logo (legitimate — SVG must embed colors):**
- `default-layout.component.html:14-30`
- `views/pages/login/login.component.html:13-17`
- `views/pages/register/register.component.html:12-16`

**CSS fallback values (correct pattern):**
- Skeleton components — `var(--mantis-surface-X, #hex)` fallbacks. CORRECT use.

**Fix**: Template bindings → palette constants file (covered by H4-VIEWS-OTHER, M2-VIEWS-OTHER). Dedupe `epic-colors.ts` ↔ `logo.service.ts`.

---

## Pattern 10 (MEDIUM): !important Usage
**Occurrences**: 18

Most justified (CoreUI overrides, reducedMotion accessibility).

**Unjustified (no comment, user-authored):**
1. `news.component.scss:46` — `text-decoration: underline !important` on hover
2. `system-logs.component.scss:156` — `background-color !important` on table hover
3. `operational-strip.component.scss:353` — has comment, acceptable

**Fix**: Drop !important on 2 unjustified; rely on specificity. Already covered by H5-VIEWS-OTHER, H6-VIEWS-OTHER.

---

## Pattern 11 (MEDIUM): setTimeout for Visual Timing
**Occurrences**: 3 visual-timing, 12 legitimate

**Visual timing (CLAUDE.md anti-pattern):**
1. `notification-dropdown.component.ts:40` — 600ms shake clear → use CSS `animationend`
2. `avatar-upload.component.ts:261` — 3000ms success state → use CSS `transitionend`
3. `register.component.ts:157` — 2000ms redirect — borderline (toast + immediate navigate)

**Legitimate (polling, WS reconnect):** ws backoff, training poll, toast auto-dismiss, rAF fallbacks.

**Fix**: Migrate 2 visual-timing to CSS event listeners.

---

## Pattern 12 (LOW): Missing trackBy on @for
**Result**: CLEAN — Angular 17+ enforces `track` at compile time.

---

## Pattern 13 (LOW): Fixed Pixel Heights
**Mostly false positives.** Chart canvases require pixel heights. UX-spec documented heights (792px rail) acceptable.

---

## Pattern 14 (LOW): Deprecated APIs
**Result**: CLEAN — no `lighten()`/`darken()`, `RouterModule.forRoot`, `HttpClientModule`, `BrowserAnimationsModule`.

---

## Notes

1. **Dead legacy file**: `dashboard-charts-data.ts` — delete.
2. **`epic-colors.ts` duplication**: ACCENT_MAP in `logo.service.ts` duplicates `EPIC_COLORS`. Import from single source.
3. **`ApiService` missing DELETE**: Add `delete<T>()` before migrating notification-center.
4. **`signals.component.ts` type gap**: Type `signals()` properly to eliminate 4 `any` uses.
5. **`notification-dropdown` setTimeout**: Highest-impact visual-timing fix.
