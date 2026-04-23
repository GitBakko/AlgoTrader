# Dashboard v2 — Audit dati visualizzati ↔ DB / endpoint esistenti

**Obiettivo**: per ogni dato mostrato in Dashboard v2 isolare:
(1) fonte attuale, (2) se già persistito/disponibile, (3) cosa va aggiunto.

**Legenda status**:
- ✅ **già disponibile** — endpoint + shape + dato in DB OK.
- ⚠ **derivabile** — dato esiste, manca solo aggregatore/query/endpoint.
- 🔴 **NEW data** — non esiste in DB/state, richiede nuova sorgente (esterna o in-memory).

---

## 1. Top command bar

| Elemento | Dato mostrato | Fonte attuale | Status |
|---|---|---|---|
| Timeframe tabs | selezione UI | `TimeframeService` (client) | ✅ FE-only |
| Wordmark | testo decorativo | — | ✅ |
| Live clock CET | `HH:MM:SS` | `Date.now()` client | ✅ FE-only |
| KILL SWITCH | azione | `POST /api/trading/emergency-stop` | ✅ esistente |

---

## 2. OperationalStrip (6 tile)

| # | Tile | Dato | Fonte | Status |
|---|---|---|---|---|
| 1 | Session label (LONDON/NY/TOKYO) | derivato UTC hour | client (sessioni globali fisse) | ⚠ canonicale backend? |
| 1 | Session open/closed + dot | `is_open` | `GET /api/markets/status/{epic}` (`MarketStatusService`) | ✅ esistente |
| 2 | WS connected | bool | `WebSocketService.connected()` | ✅ client |
| 2 | WS priceSource (LIVE/MOCK) | enum | `ws_status` WS message | ✅ esistente |
| 2 | WS latency ms | numero | — | 🔴 **NEW** (§2.3 plan) |
| 2 | pricesAreFresh | bool | 90s threshold client | ✅ client |
| 3 | Trades today | count opened UTC day | positions.opened_at >= today | ⚠ **query nuova** (aggiunta oggi — §2.5) |
| 4 | Circuit breakers tripped | count | `paperStatus.circuit_breakers_tripped` | ✅ esistente |
| 5 | Paper bot running | bool | `paperStatus.running` | ✅ esistente |
| 5 | Paper bot uptime | secs | `iteration_count × interval_seconds` | ⚠ approssimato (meglio: `loop.started_at`) |
| 6 | Model name + version | stringa | `models` table (name, version) | ⚠ endpoint nuovo (`/api/models/current`) |
| 6 | Model last_trained | ISO | `models.last_trained` | ⚠ idem |
| 6 | Model → strategy mapping | mapping | `paper_loop.models_loaded` in-memory | ⚠ join con DB |

---

## 3. Cockpit spine (equity + drawdown)

| Elemento | Dato | Fonte | Status |
|---|---|---|---|
| Equity line | `equity` per giorno | `GET /api/dashboard/equity-curve` + live broker equity | ✅ esistente |
| Drawdown overlay | `drawdown_pct` per giorno | `equity-curve.drawdown_pct` | ✅ esistente |
| Hero equity € | corrente | `overview.equity` | ✅ esistente |
| Delta % | `daily_pnl / equity × 100` | client | ✅ derivato |
| Peak/Max DD markers (mocks) | max equity + min dd | client compute da curve | ✅ derivabile |

---

## 4. KPI Rail (8 righe — right pane)

| # | Label | Dato | Fonte | Status |
|---|---|---|---|---|
| 1 | Daily P&L | `overview.daily_pnl` | `/api/dashboard/overview` | ✅ |
| 2 | Open positions | count paper positions | `/api/trading/positions` | ✅ |
| 3 | Unrealized P&L | Σ `upl` live | `paperPositions[].upl` (broker UPL) | ✅ |
| 4 | Net exposure € | Σ `size × level` | client compute da paperPositions | ✅ derivato |
| 5 | Drawdown % | `current_drawdown_pct × 100` | `/api/system/risk-status` | ✅ |
| 6 | Sharpe (30d) | `performance.sharpe_ratio` | `/api/trading/performance?days=30` | ✅ esistente |
| 7 | Win rate | `performance.win_rate` | idem | ✅ esistente |
| 8 | Hit rate TP | `performance.tp_hit_rate` | closed positions WHERE close_reason='TP' | ⚠ **query nuova** (aggiunta oggi — §2.5) |

---

## 5. Bottom row

### 5.1 Duration × PnL scatter

| Elemento | Dato | Fonte | Status |
|---|---|---|---|
| Punto scatter | `duration_minutes`, `profit_loss` | `/api/positions/closed` | ✅ esistente |
| Colore win/loss | segno P&L | client | ✅ |
| Mediana win duration | avg di duration su win | client aggrega | ✅ derivabile (OR aggregate backend) |
| Mediana loss duration | idem | client | ✅ idem |
| Alert late-exit bias | `loss_avg > win_avg × 1.3` | client | ✅ derivabile |

**Conclusione**: 100% dati esistono. Decisione: aggregare client-side vs nuovo endpoint con medie (backend costerebbe meno CPU client).

### 5.2 Funding ring (BYBIT · BTC)

| Elemento | Dato | Fonte | Status |
|---|---|---|---|
| rate_8h (−0.04%/8h) | funding rate corrente | 🚫 Bybit API | 🔴 **NEW external** |
| next_funding | timestamp next | 🚫 Bybit | 🔴 **NEW** |
| accumulated_7d € | Σ funding × notional | 🚫 Bybit history | 🔴 **NEW** |
| notional € | posizione × prezzo | positions Capital.com | ⚠ ma i nostri epici non hanno funding |
| side (long 0.12) | direzione esposizione | positions | ⚠ idem |

**⚠ PROBLEMA DESIGN**: MANTIS trade **Capital.com CFDs**, che **NON hanno funding rate come i perp di Bybit**. Capital.com ha **"overnight swap"** (rollover cost) che è un dato diverso e disponibile via broker.

**Opzioni**:
- **A**: Rimuovere tile (semplificare)
- **B**: Sostituire con "Overnight swap EUR/USD CFD" — dato Capital.com esistente ma non esposto frontend
- **C**: Integrare Bybit come riferimento market-wide (non legato alle nostre posizioni) — valore decorativo/info
- **D**: Tenere mock/skeleton finché non si decide

**Raccomandazione**: B o A. Il design Bybit non combacia col nostro stack.

### 5.3 Calendar heatmap 90d

| Elemento | Dato | Fonte | Status |
|---|---|---|---|
| Cell date + daily_pnl | `equity_curve[i].daily_pnl` | `/api/dashboard/equity-curve?days=90` | ✅ |
| Cell trade_count | `equity_curve[i].trade_count` | idem | ✅ |
| Cell win_count | idem | idem | ✅ |
| Best/worst stats | max/min daily_pnl in periodo | client compute | ✅ derivato |

**100% coverage.** Nessuna modifica backend.

---

## 6. TradeBreakdown (per-day × BUY/SELL × TP/SL/Going)

| Elemento | Dato | Fonte esistente | Status |
|---|---|---|---|
| date | UTC day | `positions.closed_at` | ✅ |
| BUY/SELL direction | `positions.direction` | ✅ | ✅ |
| TP count (per day per dir) | `WHERE close_reason='TP'` | positions | ⚠ aggregato nuovo |
| SL count | `WHERE close_reason='SL'` | positions | ⚠ idem |
| Going count | positions OPEN at end-of-day | positions (aggregazione) | ⚠ query più complessa |
| pnl (per day per dir) | Σ `profit_loss` | positions | ⚠ aggregato |

**Tutti i dati esistono in DB** → serve solo nuovo endpoint con aggregatore.

---

## 7. Riepilogo: cosa è VERAMENTE nuovo

### 7.1 Dati nuovi da registrare (NEW) — richiedono sorgente esterna o state nuovo

1. **WS latency**: transient, ping/pong o timestamp, **no DB**.
2. **Funding Bybit** (se si mantiene il tile): esterno, richiederebbe:
   - REST cache in-memory
   - Eventuale `funding_snapshots` table se serve storico → valuta on-demand fetch
3. **Loop `started_at`** (per uptime preciso): in-memory, **no DB**.

### 7.2 Dati esistenti — serve solo nuovo endpoint/aggregatore

1. **`tp_hit_rate`** — +1 campo su `/performance` (già implementato oggi).
2. **`tp_count`** — idem.
3. **`daily_trade_count`** — +1 campo su `/performance` (già implementato oggi).
4. **Trade breakdown per-day** — nuovo `/api/trading/performance/breakdown`.
5. **Current model per strategy** — nuovo `/api/models/current` (legge `paper_loop.models_loaded` + `models` table).
6. **Session venue canonica** (opzionale) — `/api/markets/sessions/current`.
7. **Duration medians** (opzionale) — aggregato client OK così com'è.

### 7.3 Nessuna nuova tabella DB necessaria

Lo schema esistente (`positions`, `models`, `signals`, `trades`) copre **tutti** i dati del dashboard. Serve solo:
- estendere `get_performance_stats` (fatto oggi)
- aggiungere aggregatori (breakdown per-day, opened-today count)
- estendere endpoint (performance, new breakdown, new models/current)

Eccezione: **Funding Bybit** richiederebbe la sua tabella se si vuole storico 7d. Ma dipende dalla scelta design (§5.2).

---

## 8. Prossimi passi — richieste decisioni

Prima di procedere con backend implementation, servono **3 decisioni**:

### D1. Funding ring
- A) Rimuovere tile
- B) Sostituire con "Overnight swap Capital.com" (dato broker-side)
- C) Integrare Bybit come reference esterno (scollegato dalle nostre posizioni)
- D) Skeleton permanente

### D2. WS latency
- A) Ping/pong round-trip (più preciso, più lavoro WS)
- B) Server timestamp nel tick → client compute `Date.now() - server_ts` (più semplice, meno preciso per clock skew)

### D3. Session label canonico
- A) Canonicalizzare backend (`/api/markets/sessions/current`)
- B) Tenere client UTC-hour heuristic (già implementato)

### D4. Duration medians
- A) Aggregato backend (+ nuovo endpoint / campo in `/performance`)
- B) Client compute (già implementato nel componente)

---

## 9. Impact tabella sprint plan

Rispetto al plan originale [`2026-04-23_dashboard-v2-sprint.md`](./2026-04-23_dashboard-v2-sprint.md) §2:

| Plan item | Status post-audit |
|---|---|
| §2.1 `/performance/breakdown` | ✅ Confermato — tutti i dati in DB |
| §2.2 Funding Bybit service | ⚠ **bloccato da D1** |
| §2.3 WS latency ping/pong | ⚠ **bloccato da D2** (scope potrebbe scendere) |
| §2.4 `/api/models/current` | ✅ Confermato — join in-memory + DB |
| §2.5 `tp_hit_rate` + `daily_trade_count` | ✅ **già implementato oggi** (non ancora committato) |
