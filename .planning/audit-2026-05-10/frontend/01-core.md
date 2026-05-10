# Frontend Audit — Core Layer (2026-05-10)

## Stats
- Files reviewed: 18 (9 services, 2 interceptors, 3 guards, 4 model files, app.config.ts, app.routes.ts, app.component.ts)
- Total findings: 9 (CRITICAL: 1, HIGH: 4, MEDIUM: 3, LOW: 1)

---

## CRITICAL

### C1-CORE: WS teardown on logout is wired but never registered — both WebSockets reconnect indefinitely after logout

**Files**: `frontend/src/app/app.component.ts` (entire file) + `frontend/src/app/core/services/auth.service.ts:184-189`

**Issue**: `AuthService.clearAuth()` calls `this._wsLazy?.disconnect()` and `this._notifLazy?.disconnectWs()`, but `_wsLazy` and `_notifLazy` are initialized to `null` and are only populated via `registerLogoutTeardown()`. Grep confirms `registerLogoutTeardown` is **never called anywhere in the codebase**. `AppComponent` injects `WebSocketService` as `this.#ws` and `NotificationService` (the toast variant, not `NotificationCenterService`), but does not call `authService.registerLogoutTeardown(...)`. As a result, both the price/trade WS (4 channels in `WebSocketService`) and the notification WS stay connected and auto-reconnect after logout — exactly the bug H1-FE/H2-FE were meant to fix.

**Why bad**: After logout, `WebSocketService` reconnects all 4 channels with exponential backoff, streaming live price ticks and trade events to a de-authenticated session. `NotificationCenterService.connectWs()` also reconnects. If the user logs in again in the same tab, a second set of WS connections stacks on top of the first.

**Fix** — add to `AppComponent.ngOnInit()`:
```typescript
// inject at class level:
readonly #authService = inject(AuthService);
readonly #notifCenter = inject(NotificationCenterService);

// in ngOnInit():
this.#authService.registerLogoutTeardown({
  ws: this.#ws,
  notif: this.#notifCenter,
});
```
`WebSocketService` is already injected as `this.#ws`; only `AuthService` and `NotificationCenterService` need adding.

---

## HIGH

### H1-CORE: Raw `HttpClient` in four services bypasses `ApiService` — CLAUDE.md convention violation

**Files**:
- `frontend/src/app/core/services/news.service.ts:22`
- `frontend/src/app/core/services/notification-center.service.ts:14`
- `frontend/src/app/core/services/market-status.service.ts:24`
- `frontend/src/app/core/services/monitoring.service.ts:130`

**Issue**: CLAUDE.md mandates "API calls: use `ApiService` (prepends apiUrl). Never raw `HttpClient`." All four services inject `HttpClient` directly and manually construct `${environment.apiUrl}/api/...` paths. `AuthService` is the documented exception (DI-cycle avoidance). The others have no such justification.

**Why bad**: Envelope-unwrapping (`{success, data, error}`) is duplicated per-service. If `ApiService` gains cross-cutting behaviour (e.g., CSRF header injection, tracing), raw callers silently miss it. `monitoring.service.ts` and `market-status.service.ts` also re-implement `firstValueFrom` async patterns that `ApiService` already encapsulates.

**Fix**: Refactor each to inject `ApiService` and remove the manual base-URL prefix. Example:
```typescript
// market-status.service.ts
private readonly api = inject(ApiService);
const data = await firstValueFrom(this.api.get<MarketStatusResponse>(`/api/markets/status/${epic}`));
```

---

### H2-CORE: `refreshTokenSubject.complete()` on logout silently swallows queued 401-retry requests

**File**: `frontend/src/app/core/interceptors/auth.interceptor.ts:31-36`

**Issue**: `resetAuthInterceptorState()` calls `refreshTokenSubject.complete()`. Any concurrent request that entered the `.pipe(filter(token => token !== null), take(1), switchMap(token => next(...)))` queue at line 93 will receive a `complete` event instead of an error. RxJS `take(1)` on a completed subject emits nothing; the `switchMap` never fires; the outer observable completes without emitting — neither `next` nor `error` callback fires on the subscriber.

**Why bad**: `TradingService` methods subscribe with `{ next: ..., error: () => {} }`. When the observable completes silently, the signal is never updated and no error is shown. Any pending request during a logout-during-refresh race vanishes without trace.

**Fix**:
```typescript
export function resetAuthInterceptorState(): void {
  isRefreshing = false;
  try { refreshTokenSubject.error(new Error('Session terminated')); } catch { /* already errored/completed */ }
  refreshTokenSubject = new BehaviorSubject<string | null>(null);
}
```

---

### H3-CORE: `logout()` clears auth state **after** the backend round-trip — 200-500ms window where the user is "still logged in"

**File**: `frontend/src/app/core/services/auth.service.ts:130-138`

**Issue**: `logout()` fires `POST /api/auth/logout`, then calls `clearAuth()` inside `.subscribe()`. During the HTTP round-trip, `isAuthenticated()` is still `true`, guards pass, and WS messages continue processing. Double-click logout fires two concurrent HTTP calls; both subscribe callbacks call `resetAuthInterceptorState()` and replace the `BehaviorSubject` concurrently.

**Why bad**: User sees authenticated UI for up to 500ms after clicking logout; race on double-click corrupts interceptor state.

**Fix**: Optimistic local state clear before the HTTP call:
```typescript
logout(): void {
  // Immediately block further auth — guards and UI react instantly
  this.authState.set({ isAuthenticated: false, currentUser: null, token: null });
  this.http.post(`${this.baseUrl}/api/auth/logout`, {}).pipe(
    catchError(() => of(null))
  ).subscribe(() => {
    this.clearAuth();           // clears localStorage + WS + interceptor
    this.router.navigate(['/login']);
  });
}
```

---

### H4-CORE: `MarketStatusService.getMultiStatus()` allocates a new `computed()` node on every call — unbounded signal graph growth

**File**: `frontend/src/app/core/services/market-status.service.ts:84-96`

**Issue**: `getMultiStatus(epics: string[])` calls Angular's `computed(() => …)` inside the function body and returns the resulting `Signal`. Every invocation creates a new node in the signal dependency graph. If a component calls this inside an `effect()`, a template expression, or a re-rendering cycle, the graph grows without bound. The old nodes are never destroyed since the caller may hold the reference but Angular has no way to GC them.

**Why bad**: Memory growth proportional to call frequency; each `computed` node holds a closure over `epics` and a reactive dependency on `statusCache`.

**Fix**: Expose the raw cache signal and let callers derive locally (single computed per component field), or accept an `epics` input signal for memoization:
```typescript
// Service: expose readonly signal
readonly statusSnapshot = this.statusCache.asReadonly();

// Component: one computed per component, not per call
readonly multiStatus = computed(() => {
  const cache = this.marketStatusService.statusSnapshot();
  return ['BTCUSD', 'ETHUSD'].reduce((acc, epic) => { ... }, {});
});
```

---

## MEDIUM

### M1-CORE: `getNews()` can leave `isLoading` permanently `true` on network errors

**File**: `frontend/src/app/core/services/news.service.ts:44-59`

**Issue**: The pattern is `pipe(tap(...), catchError(...)).subscribe(() => this.isLoading.set(false))`. `catchError` swallows the error and returns `of({success: false, data: []})`, so the subscribe callback fires and clears `isLoading`. However, if the `catchError` handler itself throws (unlikely but possible on `JSON.parse` failures upstream), or if the HTTP error path skips the catchError (timeout AbortError in `withFetch()` mode), `isLoading` sticks at `true` permanently. Additionally `getInsiderSentiment()` at line 65 calls `.subscribe()` with no error handler at all — an uncaught error from a root-scoped service subscription is silently swallowed by RxJS but `insiderSentiment` is never reset.

**Fix**: Add explicit `error` callbacks:
```typescript
.subscribe({
  next: () => this.isLoading.set(false),
  error: () => { this.isLoading.set(false); this.error.set('Network error'); }
});
```

---

### M2-CORE: `ApiService` uses `params as any` — type safety bypass allows silent wrong query strings

**File**: `frontend/src/app/core/services/api.service.ts:14, 32`

**Issue**: `{ params: params as any }` suppresses TypeScript's check. The declared param type is `Record<string, string | number>`. Angular's `HttpClient` will call `.toString()` on each value at runtime, but `boolean` values (e.g. `is_read` in `NotificationCenterService.loadPage`) passed by callers become `"true"/"false"` without type-level enforcement. Arrays silently produce repeated params or stringified arrays depending on how Angular's `HttpParams` handles them.

**Fix**:
```typescript
get<T>(path: string, params?: Record<string, string | number | boolean>): Observable<T> {
  let httpParams = new HttpParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      httpParams = httpParams.set(k, String(v));
    }
  }
  return this.http.get<ApiResponse<T>>(`${this.baseUrl}${path}`, { params: httpParams })
    .pipe(map(res => res.data));
}
```

---

### M3-CORE: `NotificationCenterService.init()` is called from two independent entry points — duplicate REST calls on startup

**Files**: `frontend/src/app/layout/default-layout/default-header/default-header.component.ts:97` and `frontend/src/app/views/dashboard/dashboard.component.ts` (injecting the service)

**Issue**: `init()` calls `loadUnreadCount()` + `loadRecent()` + `connectWs()` unconditionally. `connectWs()` has a guard (`if (this.ws) return`), but the two REST calls fire every time. Both `DefaultHeaderComponent` and `DashboardComponent` inject `NotificationCenterService` and call `init()` — so on dashboard load, two pairs of REST calls hit `/api/notifications/` within milliseconds.

**Fix**: Add a single-init guard:
```typescript
private initialized = false;
init(): void {
  if (this.initialized) return;
  this.initialized = true;
  this.loadUnreadCount();
  this.loadRecent();
  this.connectWs();
}
```

---

## LOW

### L1-CORE: `permissionGuard` is fail-open when route data is misconfigured

**File**: `frontend/src/app/core/guards/permission.guard.ts:26-29`

**Issue**: When `route.data['resource']` or `route.data['action']` is missing, the guard logs `console.error` but returns `true` (allow access). This is fail-open: a developer adding `canActivate: [permissionGuard]` without the required data silently grants unrestricted access to that route.

**Fix**: Return `false` and redirect to `/403`:
```typescript
if (!resource || !action) {
  console.error('[PermissionGuard] Route missing resource/action — denying access');
  router.navigate(['/403']);
  return false;
}
```

---

## Notes

- `AuthService.isTokenExpired()` always returns `false` (line 292). Intentional — rely on backend 401. Acceptable for current project scale but means every expired token makes a full round-trip before detection.
- `WebSocketService.intentionalDisconnect` flag is correctly set before `.close()` in `disconnect()` and reset in each `connectX()` — the fix itself is sound; only the wiring to `registerLogoutTeardown` is missing (C1-CORE above).
- The `effect()` in `AuthService` constructor (lines 48-60) reads `authState()` and writes to `localStorage` only — no signal writes inside the effect, so the CLAUDE.md infinite-loop anti-pattern is avoided correctly.
- `TradingService` correctly uses `ApiService` for all calls — fully compliant.
- `NavUsageService` correctly uses `DestroyRef` + `takeUntilDestroyed` for the router subscription — clean.
- `LogoService` SVG builder interpolates string constants from internal maps into SVG markup. Since the values come from hardcoded `COMMODITY_SVG`/`EMOJI_MAP` constants (not user input), there is no XSS vector currently. Would become a risk if the maps ever become user-configurable.
