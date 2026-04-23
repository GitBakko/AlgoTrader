# Dashboard v2 — Sprint Plan (Variant B "Cockpit")

**Branch**: `ui/dashboard-v2`
**Route**: `/dashboard-v2` (affianco a `/dashboard` esistente, per transizione sicura)
**Handoff source**: `design_handoff_dashboard_v2/README.md` + `mocks/` (Variant B target)
**Scope**: FE-only questo sprint. Backend MANDATORIO prossimo sprint (§ "Backend Required — Next Sprint").

---

## 1. Scope sprint corrente (FE-only)

### Deliverable A — `DashboardV2Component`
Nuovo container `frontend/src/app/views/dashboard/dashboard-v2/`:
- Top command bar (timeframe tabs, kill switch, clock)
- `OperationalStripComponent` (B)
- Cockpit spine 2fr/1fr: equity curve (`app-tv-chart`) + KPI rail verticale 8 righe
- Bottom row 1/1/1.7: duration scatter · funding ring · calendar heatmap 90d
- `TradeBreakdownComponent` (C)

Wire-up:
- `TimeframeService` signal-based (custom range con date-picker). Mappatura days: 1D=1, 7D=7, 30D=30, 90D=90, YTD=calc, ALL=3650, Custom=range.
- Equity curve + drawdown riutilizza `app-tv-chart` da shared (no refactor).
- Kill switch → `trading.emergencyStop()` via `ConfirmDialogService`.

### Deliverable B — `OperationalStripComponent`
6 tile strip. 3 tile live oggi, 3 in skeleton con TODO esplicito in cima al componente:
- ✅ LIVE: Session (`marketStatus`), Circuit breakers (`paperStatus.circuit_breakers_tripped`), Paper bot (`paperStatus.running`+`iteration_count`→uptime derivato se assente)
- ⏳ SKELETON + TODO: Broker WS latency (`ws.latencyMs` non esiste), Trades today (`performance.daily_trade_count` non esiste), Model info (`AiModelService.currentModel()` non esiste)

### Deliverable C — `TradeBreakdownComponent`
Skeleton completo con TODO al top che specifica la shape richiesta:
```ts
GET /api/trading/performance/breakdown?tf={1D|7D|30D|90D|YTD|ALL|CUSTOM}&from=&to=
→ { timeframe, days: TradeBreakdownDay[] }
interface TradeBreakdownDay {
  date: string;  // YYYY-MM-DD
  buy:  { tp: number; sl: number; going: number; pnl: number };
  sell: { tp: number; sl: number; going: number; pnl: number };
}
```
Render: empty state + TODO banner. Nessuna derivazione client-side.

### Sub-components A
- `kpi-rail/kpi-rail.component` (right pane cockpit) — 8 righe
- `cockpit-bottom/duration-scatter.component` — **derivato da `closedPositions` + `duration_minutes` + `profit_loss`** (dati esistono)
- `cockpit-bottom/funding-ring.component` — skeleton + TODO (Bybit endpoint backend mancante)
- `cockpit-bottom/calendar-heatmap.component` — derivato da `equityCurve(90)` esistente

### Specs
Nuovi spec mirror pattern views esistenti:
- `dashboard-v2.component.spec.ts`
- `operational-strip/operational-strip.component.spec.ts`
- `trade-breakdown/trade-breakdown.component.spec.ts`

### Definition of Done (FE sprint)
- [ ] `ng build --configuration=development` verde
- [ ] Route `/dashboard-v2` raggiungibile, vecchia `/dashboard` intatta
- [ ] Tutti i tile wired a servizio reale O skeleton con TODO comment esplicito (no mock array)
- [ ] CSS vars `--mantis-*` / `$mantis-*` only — zero hex literal
- [ ] `prefers-reduced-motion` rispettato per tutte le animazioni
- [ ] Responsive ≥360px (bottom row stacks <1280px, single col <768px)
- [ ] Specs nuovi passano
- [ ] Commit per step, branch pushato

---

## 2. Backend Required — Next Sprint (MANDATORIO)

Questi lavori backend sono **bloccanti** per chiudere Definition of Done di `README.md §14` (ogni numero reale, zero hardcoded). Vanno schedulati subito dopo il merge del FE.

### 2.1 `GET /api/trading/performance/breakdown` — **NEW endpoint**
Input: `tf` (string enum), `from`, `to` (ISO date, solo se `tf=Custom`).
Output:
```json
{
  "success": true,
  "data": {
    "timeframe": "30D",
    "days": [
      {
        "date": "2026-04-22",
        "buy":  { "tp": 3, "sl": 1, "going": 1, "pnl": 180.40 },
        "sell": { "tp": 2, "sl": 2, "going": 0, "pnl": -40.10 }
      }
    ]
  }
}
```
Logica:
- Group `closed_positions` per `date(closed_at)` + `direction` + `close_reason` (`tp`/`sl`/other).
- `going` = open `paper_positions` per direction con `opened_at` in giornata corrente.
- Weekend + giorni vuoti inclusi con counts a 0.
- Timezone UTC. Pydantic v2 model.
- Test: `tests/api/test_performance_breakdown.py` — DB reale, no mock.

### 2.2 Funding rate — **NEW `FundingService` + endpoints**
- Provider: Bybit REST `/v5/market/funding/history` (no auth necessaria per read pubblico).
- `GET /api/funding/current?epic=BTCUSD` → `{ rate_8h, next_funding_utc, notional_eur, side, accumulated_7d }`.
- Mapping epic → Bybit symbol (BTCUSD→BTCUSDT, ETHUSD→ETHUSDT). Solo perp.
- Cache 60s (Redis se disponibile, else in-memory), graceful degradation.
- WebSocket tick opzionale (bonus): broadcast su `/ws/funding`.

### 2.3 WS latency ping — **extend `/ws/prices`**
- Server emette `{ type: 'ping', server_ts: <ms> }` ogni 10s.
- Client risponde `{ type: 'pong', server_ts: <echo>, client_ts: <ms> }`.
- Server calcola RTT, broadcast `{ type: 'ws_status', latency_ms, ... }` a tutti i client.
- FE: `WebSocketService.latencyMs: Signal<number | null>`.

### 2.4 `GET /api/models/current` — **NEW endpoint**
Output:
```json
{
  "success": true,
  "data": {
    "primary":   { "model_id": "ml_primary_v2_3", "version": "v2.3", "last_trained": "2026-04-20T14:00:00Z" },
    "squeeze":   { ... },
    "vwap":      { ... }
  }
}
```
Implementazione: leggi `models_loaded` dal loop state + metadata da DB.

### 2.5 `performance.tp_hit_rate` + `performance.daily_trade_count`
Estendi `TradingPerformance`:
```python
class TradingPerformance(BaseModel):
    # ... existing
    tp_hit_rate: float  # closed trades hitting TP / total closed
    daily_trade_count: int  # count trades opened in current UTC day
```

### 2.6 Test baseline
- No new failures rispetto a `project_test_baseline_2026-04-20.md` (20 pre-existing).
- Integration tests colpiscono DB reale (CLAUDE.md: "Mock DB = vietato").

---

## 3. File layout finale

```
frontend/src/app/views/dashboard/
  dashboard.component.ts              (INTATTO — route '/dashboard' resta)
  routes.ts                           (INTATTO)
  dashboard-v2/
    dashboard-v2.component.ts         (Deliverable A)
    dashboard-v2.component.html
    dashboard-v2.component.scss
    dashboard-v2.component.spec.ts
    routes.ts                         (route child '')
    operational-strip/
      operational-strip.component.{ts,html,scss,spec.ts}  (Deliverable B)
    trade-breakdown/
      trade-breakdown.component.{ts,html,scss,spec.ts}    (Deliverable C)
    kpi-rail/
      kpi-rail.component.{ts,html,scss}
    cockpit-bottom/
      duration-scatter.component.{ts,html,scss}
      funding-ring.component.{ts,html,scss}
      calendar-heatmap.component.{ts,html,scss}

frontend/src/app/core/services/
  timeframe.service.ts                (NEW singleton signal-based)

frontend/src/app/app.routes.ts        (+ '/dashboard-v2' path)
```

---

## 4. Ordine commit

1. `feat(fe): add TimeframeService + Timeframe model`
2. `feat(fe): add OperationalStripComponent (Deliverable B) with skeleton TODOs`
3. `feat(fe): add TradeBreakdownComponent (Deliverable C) with backend TODO`
4. `feat(fe): add kpi-rail/duration-scatter/funding-ring/calendar-heatmap sub-components`
5. `feat(fe): add DashboardV2Component (Deliverable A) + route /dashboard-v2`
6. `test(fe): specs for DashboardV2, OperationalStrip, TradeBreakdown`
7. `docs: dashboard-v2 sprint plan + mandatory backend todo`

Push su `ui/dashboard-v2`, poi user decide merge/PR.
