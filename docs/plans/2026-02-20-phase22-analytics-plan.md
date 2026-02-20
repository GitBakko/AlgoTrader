# Phase 22: Analytics & Dashboard Enhancement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add advanced analytics features: dashboard notification widget, notification preferences, performance analytics page with interactive charts, portfolio correlation heatmap, and backtest comparison view.

**Architecture:** Frontend-heavy phase. Uses existing `NotificationCenterService` for dashboard widget, `chart.js` (already installed) for bar/doughnut/heatmap charts alongside existing `lightweight-charts` for time-series. One new backend endpoint for correlation matrix. Settings page extended with notification filter preferences (localStorage-backed).

**Tech Stack:** Angular 21, CoreUI, chart.js 4.5 + @coreui/angular-chartjs, lightweight-charts 5.1, Python/FastAPI (1 new endpoint)

---

## Feature 22.3: Dashboard Notification Widget

### Task 1: Add notification widget to dashboard

**Files:**
- Modify: `frontend/src/app/views/dashboard/dashboard.component.ts`
- Modify: `frontend/src/app/views/dashboard/dashboard.component.html`
- Modify: `frontend/src/app/views/dashboard/dashboard.component.scss`

**Step 1: Import NotificationCenterService in dashboard component**

In `dashboard.component.ts`, add:
```typescript
import { NotificationCenterService } from '../../core/services/notification-center.service';
// In component class:
readonly #notifCenter = inject(NotificationCenterService);
readonly recentAlerts = computed(() =>
  this.#notifCenter.notifications()
    .filter(n => !n.is_read)
    .slice(0, 5)
);
readonly alertCount = this.#notifCenter.unreadCount;
```

Add `RouterLink` to imports array if not present.

**Step 2: Add notification card to dashboard HTML**

Insert after the Performance section divider and before the Markets section divider:

```html
<!-- Notification Widget -->
@if (recentAlerts().length > 0) {
  <c-col xs="12">
    <c-card class="border-top border-top-3 border-top-warning">
      <c-card-header class="d-flex align-items-center justify-content-between py-2">
        <span class="fw-semibold small text-body-secondary">
          <svg cIcon name="cilBell" size="sm" class="me-1"></svg>
          Notifiche Non Lette
        </span>
        <a routerLink="/notifications" class="small text-decoration-none">Vedi tutte</a>
      </c-card-header>
      <c-card-body class="p-0">
        @for (n of recentAlerts(); track n.id) {
          <div class="d-flex align-items-start gap-2 px-3 py-2 border-bottom border-opacity-10">
            <span class="fs-5">{{ n.emoji }}</span>
            <div class="flex-grow-1 min-w-0">
              <div class="small fw-medium text-truncate">{{ n.title }}</div>
              <div class="small text-body-secondary text-truncate">{{ n.message }}</div>
            </div>
            <c-badge [color]="n.severity === 'CRITICAL' ? 'danger' : n.severity === 'WARNING' ? 'warning' : 'info'" class="text-uppercase" style="font-size: 0.6rem">
              {{ n.severity }}
            </c-badge>
          </div>
        }
      </c-card-body>
    </c-card>
  </c-col>
}
```

**Step 3: Add minimal SCSS**

```scss
// No new SCSS needed — uses Bootstrap utilities + CoreUI card pattern
```

**Step 4: Build and verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: 0 errors, 0 warnings

**Step 5: Commit**

```bash
git add frontend/src/app/views/dashboard/
git commit -m "feat(dashboard): add unread notifications widget"
```

---

## Feature 22.4: Notification Preferences

### Task 2: Add notification filter preferences to Settings page

**Files:**
- Modify: `frontend/src/app/views/settings/settings.component.ts`

**Step 1: Add filter state with localStorage persistence**

In `settings.component.ts`, add:

```typescript
// Alert types that can be toggled
readonly alertTypes = [
  { key: 'TRADE_OPENED', label: 'Trade Aperte', emoji: '📈' },
  { key: 'TRADE_CLOSED', label: 'Trade Chiuse', emoji: '📉' },
  { key: 'SIGNAL_GENERATED', label: 'Segnali', emoji: '🎯' },
  { key: 'CIRCUIT_BREAKER', label: 'Circuit Breaker', emoji: '🔴' },
  { key: 'DRAWDOWN_EXCEEDED', label: 'Drawdown', emoji: '⚠️' },
  { key: 'BROKER_ERROR', label: 'Errori Broker', emoji: '❌' },
  { key: 'SYSTEM_ERROR', label: 'Errori Sistema', emoji: '🛑' },
];

// Load from localStorage
readonly mutedAlertTypes = signal<Set<string>>(
  new Set(JSON.parse(localStorage.getItem('mantis-muted-alerts') || '[]'))
);

toggleAlertType(key: string): void {
  const current = new Set(this.mutedAlertTypes());
  if (current.has(key)) current.delete(key);
  else current.add(key);
  this.mutedAlertTypes.set(current);
  localStorage.setItem('mantis-muted-alerts', JSON.stringify([...current]));
}

isAlertMuted(key: string): boolean {
  return this.mutedAlertTypes().has(key);
}
```

**Step 2: Expand the Notifiche card in settings template**

Replace the existing "Notifiche" card with expanded version that includes:
- Existing browser notification + sound toggles
- New section: "Filtra Notifiche In-App" with toggleable chips per alert type
- Each chip shows emoji + label, toggled on/off with muted style

```html
<c-card class="border-top border-top-3 border-top-primary">
  <c-card-header class="py-2">
    <span class="fw-semibold small text-body-secondary">Notifiche</span>
  </c-card-header>
  <c-card-body class="p-3">
    <!-- Existing toggles -->
    <div class="form-check form-switch mb-2">
      <input class="form-check-input" type="checkbox" id="browserNotif"
        [checked]="notifications.enabled()"
        (change)="notifications.requestPermission()">
      <label class="form-check-label small" for="browserNotif">Notifiche browser</label>
    </div>
    <div class="form-check form-switch mb-3">
      <input class="form-check-input" type="checkbox" id="soundNotif"
        [checked]="notifications.soundEnabled()"
        (change)="notifications.toggleSound()">
      <label class="form-check-label small" for="soundNotif">Suoni alert</label>
    </div>

    <!-- New: alert type filters -->
    <div class="small text-body-secondary mb-2">Filtra Notifiche In-App</div>
    <div class="d-flex flex-wrap gap-1">
      @for (t of alertTypes; track t.key) {
        <button class="btn btn-sm px-2 py-1"
          [class.btn-outline-secondary]="isAlertMuted(t.key)"
          [class.btn-primary]="!isAlertMuted(t.key)"
          [style.opacity]="isAlertMuted(t.key) ? '0.5' : '1'"
          (click)="toggleAlertType(t.key)">
          {{ t.emoji }} {{ t.label }}
        </button>
      }
    </div>
    <div class="small text-body-secondary mt-2">
      Click per silenziare/attivare. Le notifiche silenziate non appaiono nella campanella.
    </div>
  </c-card-body>
</c-card>
```

**Step 3: Wire filter into NotificationCenterService**

In `notification-center.service.ts`, add a filtered signal:

```typescript
// Read muted types from localStorage
private getMutedTypes(): Set<string> {
  return new Set(JSON.parse(localStorage.getItem('mantis-muted-alerts') || '[]'));
}

readonly filteredNotifications = computed(() => {
  const muted = this.getMutedTypes();
  return this.notifications().filter(n => !muted.has(n.alert_type));
});

readonly filteredUnreadCount = computed(() =>
  this.filteredNotifications().filter(n => !n.is_read).length
);
```

Update `NotificationDropdownComponent` to use `filteredNotifications` and `filteredUnreadCount` instead of raw signals.

**Step 4: Build and verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`
Expected: 0 errors, 0 warnings

**Step 5: Commit**

```bash
git add frontend/src/app/views/settings/ frontend/src/app/core/services/notification-center.service.ts frontend/src/app/layout/default-layout/default-header/notification-dropdown/
git commit -m "feat(settings): notification type filter preferences with localStorage"
```

---

## Feature 22.5: Performance Analytics Page

### Task 3: Create Performance Analytics page (backend — add Sharpe/Sortino to performance endpoint)

**Files:**
- Modify: `backend/src/database/repositories/position_repository.py`
- Modify: `backend/src/api/routers/trading.py`

**Step 1: Add Sharpe/Sortino/Calmar computation to `get_performance_stats`**

In `position_repository.py`, after computing `pnl_by_epic`, add:

```python
import numpy as np

# Compute daily returns from equity curve
if equity_curve and len(equity_curve) > 1:
    values = [p["value"] for p in equity_curve]
    returns = np.diff(values) / np.maximum(np.abs(values[:-1]), 1e-10)

    avg_return = float(np.mean(returns))
    std_return = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    downside_returns = returns[returns < 0]
    downside_std = float(np.std(downside_returns, ddof=1)) if len(downside_returns) > 1 else 0.0

    # Annualize (assuming ~252 trading days)
    sharpe_ratio = (avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0
    sortino_ratio = (avg_return / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

    # Max drawdown
    peak = np.maximum.accumulate(values)
    drawdowns = (peak - values) / np.maximum(peak, 1e-10)
    max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Calmar (annualized return / max drawdown)
    total_days = max(len(equity_curve), 1)
    annualized_return = ((values[-1] / max(values[0], 1e-10)) ** (252 / total_days) - 1) if total_days > 0 else 0.0
    calmar_ratio = (annualized_return / max_drawdown) if max_drawdown > 0 else 0.0
else:
    sharpe_ratio = sortino_ratio = max_drawdown = calmar_ratio = 0.0
```

Add these to the returned dict:
```python
"sharpe_ratio": round(sharpe_ratio, 3),
"sortino_ratio": round(sortino_ratio, 3),
"calmar_ratio": round(calmar_ratio, 3),
"max_drawdown": round(max_drawdown, 4),
```

**Step 2: Run backend tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q`
Expected: All pass

**Step 3: Commit**

```bash
git add backend/src/database/repositories/position_repository.py backend/src/api/routers/trading.py
git commit -m "feat(api): add Sharpe/Sortino/Calmar/MaxDD to performance endpoint"
```

### Task 4: Create Performance Analytics frontend page

**Files:**
- Create: `frontend/src/app/views/performance/performance.component.ts`
- Create: `frontend/src/app/views/performance/performance.component.html`
- Create: `frontend/src/app/views/performance/performance.component.scss`
- Create: `frontend/src/app/views/performance/routes.ts`
- Modify: `frontend/src/app/app.routes.ts`
- Modify: `frontend/src/app/layout/default-layout/_nav.ts`

**Step 1: Create route and nav entry**

`routes.ts`:
```typescript
import { Routes } from '@angular/router';
import { PerformanceComponent } from './performance.component';
export const routes: Routes = [{ path: '', component: PerformanceComponent }];
```

Add to `app.routes.ts` before `notifications`:
```typescript
{ path: 'performance', loadChildren: () => import('./views/performance/routes').then(m => m.routes) },
```

Add to `_nav.ts` in Analisi section after Backtest:
```typescript
{ name: 'Performance', url: '/performance', iconComponent: { name: 'cil-chart' } },
```

**Step 2: Create component with 5 sections**

The page layout:
1. **Period selector** (7d / 30d / 90d / All) + optional asset filter
2. **KPI Row** (8 cards): Trade Count, Win Rate, Profit Factor, Sharpe, Sortino, Calmar, Max DD, Total P&L
3. **Equity Curve** (full width): `app-tv-chart` mode="area"
4. **P&L Distribution** (lg="6"): chart.js bar chart — histogram of trade P&Ls
5. **P&L per Asset** (lg="6"): chart.js horizontal bar chart — total P&L by asset
6. **Trade Duration Analysis** (lg="6"): chart.js bar chart — avg holding time by asset
7. **Win Rate by Asset** (lg="6"): chart.js horizontal bar chart

Uses `@coreui/angular-chartjs` `ChartjsComponent` for charts (import `ChartjsModule`).
Uses `trading.loadPerformance(days, epic?)` for data.

**Step 3: Build and verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`

**Step 4: Commit**

```bash
git add frontend/src/app/views/performance/ frontend/src/app/app.routes.ts frontend/src/app/layout/default-layout/_nav.ts
git commit -m "feat: add Performance Analytics page with interactive charts"
```

---

## Feature 22.6: Portfolio Correlation Heatmap

### Task 5: Create correlation matrix backend endpoint

**Files:**
- Create: `backend/src/api/routers/analytics.py`
- Modify: `backend/src/api/main.py`

**Step 1: Create analytics router**

```python
from fastapi import APIRouter, Depends, Query
from src.api.dependencies import get_services
import numpy as np
import polars as pl
from pathlib import Path

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.get("/correlation-matrix")
async def get_correlation_matrix(
    days: int = Query(default=90, ge=7, le=365),
    timeframe: str = Query(default="1h"),
    services=Depends(get_services),
):
    """Compute pairwise return correlations across all traded assets."""
    epics = ["XAUUSD", "BTCUSD", "US500", "WTIUSD", "EURUSD", "NVDA", "TSLA",
             "XAGUSD", "DE40", "SOLUSD", "ETHUSD", "BNBUSD", "DOGUSD", "DASHUSD",
             "ICPUSD", "NATGAS", "COPPER", "PLATINUM", "GBPUSD", "USDJPY", "NAS100"]

    returns_dict = {}
    data_dir = Path("data/historical")

    for epic in epics:
        pattern = f"{epic}_{timeframe}_*.parquet"
        files = sorted(data_dir.glob(pattern))
        if not files:
            continue
        df = pl.read_parquet(files[-1])
        if "close" in df.columns and len(df) > 10:
            closes = df["close"].to_numpy()
            rets = np.diff(np.log(closes + 1e-10))
            # Trim to last N periods (days * periods_per_day)
            periods = days * (24 if timeframe == "1h" else 6 if timeframe == "4h" else 1)
            rets = rets[-periods:]
            returns_dict[epic] = rets

    # Build correlation matrix
    common_len = min(len(v) for v in returns_dict.values()) if returns_dict else 0
    if common_len < 10:
        return {"success": True, "data": {"epics": [], "matrix": []}}

    aligned_epics = sorted(returns_dict.keys())
    matrix = np.zeros((len(aligned_epics), len(aligned_epics)))
    for i, e1 in enumerate(aligned_epics):
        for j, e2 in enumerate(aligned_epics):
            r1 = returns_dict[e1][-common_len:]
            r2 = returns_dict[e2][-common_len:]
            matrix[i][j] = float(np.corrcoef(r1, r2)[0, 1])

    return {
        "success": True,
        "data": {
            "epics": aligned_epics,
            "matrix": matrix.round(3).tolist(),
            "period_days": days,
            "data_points": common_len,
        }
    }
```

**Step 2: Register router in main.py**

```python
from src.api.routers import analytics
app.include_router(analytics.router)
```

**Step 3: Run backend tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q`

**Step 4: Commit**

```bash
git add backend/src/api/routers/analytics.py backend/src/api/main.py
git commit -m "feat(api): add correlation matrix endpoint for portfolio analysis"
```

### Task 6: Create correlation heatmap frontend component

**Files:**
- Create: `frontend/src/app/views/performance/correlation-heatmap.component.ts` (inline template)

**Step 1: Create heatmap component**

A standalone component that renders a CSS Grid-based heatmap (no external lib needed). Each cell is colored on a diverging scale (red -1 → white 0 → green +1).

Data fetched from `GET /api/analytics/correlation-matrix?days=90`.

The component accepts `@Input() data: { epics: string[], matrix: number[][] }` and renders:
- Row/column headers with epic names (rotated for columns)
- Cells colored by correlation value
- Hover tooltip showing exact value
- Size: each cell ~32px, scrollable if > 15 assets

**Step 2: Add to Performance page**

Insert as a new section below the existing charts:
```html
<div class="section-divider">
  <span class="section-divider__label">Correlazione Portfolio</span>
  <div class="section-divider__line"></div>
</div>
<c-col xs="12">
  <c-card class="border-top border-top-3 border-top-primary">
    <c-card-header class="py-2">
      <span class="fw-semibold small text-body-secondary">Matrice di Correlazione (90g)</span>
    </c-card-header>
    <c-card-body class="p-2 overflow-auto">
      <app-correlation-heatmap [data]="correlationData()" />
    </c-card-body>
  </c-card>
</c-col>
```

**Step 3: Build and verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`

**Step 4: Commit**

```bash
git add frontend/src/app/views/performance/
git commit -m "feat: add portfolio correlation heatmap to performance page"
```

---

## Feature 22.7: Backtest Results Comparison

### Task 7: Add backtest comparison view

**Files:**
- Modify: `frontend/src/app/views/backtest/backtest.component.ts`
- Modify: `frontend/src/app/core/models/index.ts` (if needed for types)

**Step 1: Add multi-select for comparison**

In `backtest.component.ts`, add:

```typescript
readonly selectedForComparison = signal<string[]>([]);  // run IDs

toggleComparison(runId: string): void {
  const current = this.selectedForComparison();
  if (current.includes(runId)) {
    this.selectedForComparison.set(current.filter(id => id !== runId));
  } else if (current.length < 4) {  // max 4 comparisons
    this.selectedForComparison.set([...current, runId]);
  }
}

readonly comparisonRuns = computed(() => {
  const ids = this.selectedForComparison();
  return this.backtestRuns().filter(r => ids.includes(r.id));
});
```

**Step 2: Add comparison toggle in results table**

Add a checkbox column to the existing backtest results table:
```html
<td>
  <input type="checkbox" class="form-check-input"
    [checked]="selectedForComparison().includes(run.id)"
    (change)="toggleComparison(run.id)"
    [disabled]="!selectedForComparison().includes(run.id) && selectedForComparison().length >= 4">
</td>
```

**Step 3: Add comparison panel**

When `selectedForComparison().length >= 2`, show a comparison panel below the results table:

```html
@if (selectedForComparison().length >= 2) {
  <c-col xs="12">
    <c-card class="border-top border-top-3 border-top-primary mt-3">
      <c-card-header class="py-2 d-flex justify-content-between">
        <span class="fw-semibold small text-body-secondary">
          Confronto ({{ selectedForComparison().length }} run)
        </span>
        <button class="btn btn-sm btn-link p-0" (click)="selectedForComparison.set([])">
          Reset
        </button>
      </c-card-header>
      <c-card-body class="p-3">
        <table cTable [small]="true" [hover]="true" class="mb-0">
          <thead>
            <tr class="text-body-secondary">
              <th class="fw-semibold small">Metrica</th>
              @for (run of comparisonRuns(); track run.id) {
                <th class="fw-semibold small text-center">{{ run.summary.epic }} {{ run.config.timeframe }}</th>
              }
            </tr>
          </thead>
          <tbody>
            <!-- Rows: Return, Sharpe, Sortino, Win Rate, Profit Factor, Max DD, Trades -->
            <tr>
              <td class="small">Return %</td>
              @for (run of comparisonRuns(); track run.id) {
                <td class="mantis-mono text-center"
                  [class.text-success]="run.metrics.total_return > 0"
                  [class.text-danger]="run.metrics.total_return < 0">
                  {{ run.metrics.total_return | number:'1.2-2' }}%
                </td>
              }
            </tr>
            <!-- ... repeat for Sharpe, Sortino, Win Rate, Profit Factor, Max DD, Trades -->
          </tbody>
        </table>
      </c-card-body>
    </c-card>
  </c-col>
}
```

**Step 4: Build and verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -5`

**Step 5: Commit**

```bash
git add frontend/src/app/views/backtest/
git commit -m "feat(backtest): add side-by-side comparison view for multiple runs"
```

---

## Verification

After all tasks:

1. `cd frontend && npx ng build --configuration=development` — 0 errors
2. `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q` — 0 failures
3. Visual test: Dashboard shows notification widget when unread alerts exist
4. Visual test: Settings page shows alert type filter chips
5. Visual test: `/performance` page with KPIs, equity curve, charts, heatmap
6. Visual test: Backtest page comparison panel when 2+ runs selected
7. Final commit + push

---

## File Summary

| File | Type | Feature |
|------|------|---------|
| `frontend/src/app/views/dashboard/dashboard.component.*` | Modify | 22.3 Notification widget |
| `frontend/src/app/views/settings/settings.component.ts` | Modify | 22.4 Alert preferences |
| `frontend/src/app/core/services/notification-center.service.ts` | Modify | 22.4 Filtered signals |
| `frontend/src/app/layout/.../notification-dropdown/*` | Modify | 22.4 Use filtered signals |
| `backend/src/database/repositories/position_repository.py` | Modify | 22.5 Sharpe/Sortino/Calmar |
| `frontend/src/app/views/performance/*` | Create | 22.5 Performance page |
| `frontend/src/app/app.routes.ts` | Modify | 22.5 Route |
| `frontend/src/app/layout/default-layout/_nav.ts` | Modify | 22.5 Nav entry |
| `backend/src/api/routers/analytics.py` | Create | 22.6 Correlation endpoint |
| `backend/src/api/main.py` | Modify | 22.6 Register router |
| `frontend/src/app/views/performance/correlation-heatmap.component.ts` | Create | 22.6 Heatmap UI |
| `frontend/src/app/views/backtest/backtest.component.ts` | Modify | 22.7 Comparison view |
