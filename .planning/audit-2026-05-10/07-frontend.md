# Frontend Angular Audit — 2026-05-10

**Files reviewed:** `core/services/`, `core/interceptors/`, `core/guards/`, `views/` (dashboard-v2, paper-trading, positions, signals, ai-models, backtest, trade-journal), `shared/components/signal-audit-drawer`, `layout/default-layout`, `app.config.ts`, `app.routes.ts`, `src/scss/`.

---

## CRITICAL

### C1 — `onHeatmapCellClick` matches live position by `epic`, not `deal_id` (Bug class `dea2a29`)
`frontend/src/app/views/paper-trading/paper-trading.component.ts:482`

**What**: `find((p) => p.epic === cell.epic)` — invariant violation. With two rapid-fire positions on same epic (close not yet reconciled + new signal executing), drawer opens on wrong position.

**Fix**: Carry `deal_id` on `HeatmapCell`. Match by `p.deal_id === cell.deal_id`.

---

### C2 — `adaptPosition` fabricates P&L via `(current − level) × size` when UPL is null — Trading Invariant #2 violation
`frontend/src/app/views/paper-trading/paper-trading.component.ts:578-580`

**What**: Cockpit P&L hero falls back to `(current - p.level) * p.size` when `upl == null`. Ignores spreads/multipliers/FX. Same pattern removed from backend per CLAUDE.md.

**Fix**: When `upl == null`, set `livePnl = 0` and render a dash. Same applies to `pnlPct` line 582.

---

### C3 — Auth interceptor module-level state `isRefreshing` + `refreshTokenSubject` survives logout/login
`frontend/src/app/core/interceptors/auth.interceptor.ts:14-15`

**What**: `let isRefreshing = false; const refreshTokenSubject = new BehaviorSubject<string | null>(null);` — module singletons. If refresh in flight at logout, `isRefreshing` stays `true`. New session 401s queue indefinitely. Old-session subscriptions fire on new-session token emission, replaying old requests under new credentials.

**Fix**: Move both inside interceptor function body (functional interceptors get fresh state per invocation), OR export `resetInterceptorState()` callable from `AuthService.clearAuth()`.

---

## HIGH

### H1 — `WebSocketService.disconnect()` triggers immediate reconnect on all 4 channels
`frontend/src/app/core/services/websocket.service.ts:236-244` + onclose at lines 119-228

**What**: `disconnect()` calls `.close()` → fires registered `onclose` callbacks → each schedules reconnect. All 4 timers fire after disconnect, all sockets reopen under logged-out user.

**Fix**: `private intentionalDisconnect = false`. Set `true` in `disconnect()`, reset in each `connectX()`. Guard `onclose` handlers: `if (this.intentionalDisconnect) return;`.

---

### H2 — `NotificationCenterService.ngOnDestroy` unreachable for root-scoped service; reconnect loop forever
`frontend/src/app/core/services/notification-center.service.ts:6-7, 173-176`

**What**: `@Injectable({ providedIn: 'root' })` services never get `ngOnDestroy` called. Notification WS reconnect-loop runs forever after logout. Combines with H1 — three WS chains survive every logout.

**Fix**: Remove `implements OnDestroy`. Add `disconnectWs()` public method called from `AuthService.logout()`. Guard `onclose` with same `intentionalDisconnect` flag.

---

### H3 — Four services use raw `HttpClient` instead of `ApiService`
`frontend/src/app/core/services/monitoring.service.ts:130, market-status.service.ts:24, news.service.ts:22, notification-center.service.ts:8`

**What**: CLAUDE.md: "API calls use `ApiService` (prepends apiUrl). Never raw `HttpClient`." When `environment.apiUrl` changes, these silently hit wrong base URL. `monitoring.service.ts` also duplicates `{success, data}` envelope unwrap.

**Fix**: Replace `inject(HttpClient)` with `inject(ApiService)` in all four. Remove manual `environment.apiUrl` concat.

---

### H4 — `trade-journal.openPositionsByEpic` keyed by epic, not deal_id (same bug class as C1)
`frontend/src/app/views/trade-journal/trade-journal.component.ts:358-364, 663`

**What**: `map.set(pos.epic, ...)` — last-write-wins on same epic. With two concurrent same-epic positions, journal "Live P&L" column shows wrong trade. `closedByEpic` (line 370-377) has same flaw.

**Fix**: Key maps by `deal_id`. Surface `deal_id` on `PaperSignal` from backend (already in DB).

---

## MEDIUM

### M1 — `positions.component` fallback live P&L uses `(price − entry) × size`
`frontend/src/app/views/positions/positions.component.ts:529-532`

**What**: When `pos.upl == null`, fabricates `live_pnl = diff * pos.size`. `totalPnl` strip sums these → inflated total.

**Fix**: Return `live_pnl: 0` + dash display when UPL null.

---

### M2 — Hardcoded hex colors in backtest template
`frontend/src/app/views/backtest/backtest.component.ts:307-309`

**What**: `lineColor="#00d97e"` etc. = `$mantis-green`.

**Fix**: Use `var(--mantis-green)` if `lightweight-charts` accepts, else TS const linking to token.

---

### M3 — `signals.component` casts `PaperSignal[]` to `any` in computed blocks
`frontend/src/app/views/signals/signals.component.ts:173, 177, 179, 186`

**Fix**: Remove `(x: any)` — inference sufficient.

---

## LOW

### L1 — `ai-models.component` bare `setTimeout` not tracked by `DestroyRef`
`frontend/src/app/views/ai-models/ai-models.component.ts:617, 627`

**Fix**: Store timer IDs, `clearTimeout` in `destroyRef.onDestroy(...)`.

---

## Coverage Gaps

- No e2e for double-position-same-epic drawer routing
- No tests for `(p.upl == null)` fallback rendering
- No test for refresh-token race across logout/login
- No test for WS reconnect storm after logout
- No test for `notification-center` lifecycle
- No env URL change test for raw-HttpClient services

---

## Summary

| Pri | ID | Location | Issue |
|-----|-----|----------|-------|
| **CRITICAL** | C1 | paper-trading.component.ts:482 | Heatmap drawer routes to wrong position via epic-only match |
| **CRITICAL** | C2 | paper-trading.component.ts:578 | Fabricated P&L on null UPL — Invariant #2 violation in cockpit |
| **CRITICAL** | C3 | auth.interceptor.ts:14 | Module-level interceptor state poisons new session post-logout |
| HIGH | H1 | websocket.service.ts:236 | disconnect() triggers reconnect storm on all channels |
| HIGH | H2 | notification-center.service.ts | Root-scoped service ngOnDestroy unreachable; reconnect forever |
| HIGH | H3 | 4 services | Raw HttpClient bypasses ApiService env contract |
| HIGH | H4 | trade-journal.component.ts:358 | openPositionsByEpic last-write-wins on same epic |
| MEDIUM | M1 | positions.component.ts:529 | Same Invariant #2 fallback in /positions list |
| MEDIUM | M2-M3 | backtest, signals | Hardcoded hex, any casts |
| LOW | L1 | ai-models | setTimeout not tracked |
