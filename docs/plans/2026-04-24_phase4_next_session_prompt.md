# Prompt per sessione Phase 4 (Dashboard v2)

**Invoca**: incollare il blocco qui sotto come primo messaggio della nuova sessione.

---

## Context (incolla da qui)

Sono MANTIS AI, continuazione di lavoro su Dashboard v2. Sessione precedente mergiata in `main` (commit `25444fd`).

**Stato corrente** (verified via Playwright):
- Phase 1-3 completate. Phase 4 da fare.
- Backend running: `cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
- Frontend running: `cd frontend && npx ng serve --port 4321`
- URL dashboard: `http://localhost:4321/#/dashboard-v2` (hash router)
- Auth Playwright: user `Bakko^` / pass `PassBakko1983@`. Login endpoint `POST /api/auth/login` → `{data.access_token}`. LocalStorage keys `mantis_auth_token` + `mantis_current_user`.

**Lavoro Phase 4 — 2 endpoint backend nuovi**:

### Task A — `/api/trading/performance/delta` (~1h)

**Scopo**: surface `win_rate` delta vs periodo precedente per il tile "Win Rate" del `CockpitRightRail` (mock: `258W · 154L · ▲ +1.8pp`).

**Spec**:
- Endpoint: `GET /api/trading/performance/delta?tf={1D|7D|30D|90D|YTD|ALL|CUSTOM}&from=YYYY-MM-DD&to=YYYY-MM-DD`
- Body: `{ win_rate_current: 0.472, win_rate_previous: 0.455, delta_pp: 1.7, n_current: 287, n_previous: 245, source: "db" }`
- Implementation: chiama `position_repository.get_performance_stats()` due volte — una per current range, una per previous range (stesso N giorni retro-shifted). Calcola delta in percentage points.
- Router: `backend/src/api/routers/trading.py` (vicino a `/performance/breakdown` già esistente).
- Schema: aggiungi `PerformanceDeltaResponse` in `backend/src/api/schemas.py`.
- Esporre via frontend: aggiungi `loadPerformanceDelta(tf)` in `TradingService` + signal `performanceDelta`. Usare in `CockpitRightRail` per mostrare `▲ +1.7pp` nella sub del Win Rate tile.
- Test: `backend/tests/api/test_performance_delta.py` — hit real DB, assert schema + edge cases (no data previous period → `null`).

### Task B — `/api/markets/{epic}/swap-accum` (~3h)

**Scopo**: sostituire la stima client `rate × notional × 7` con storico reale accumulato 7d per il tile OvernightSwap (mock: `−€127.40` `7d accum`).

**Spec**:
- Endpoint: `GET /api/markets/{epic}/swap-accum?days=7`
- Body: `{ epic: "NVDA", currency: "USD", period_days: 7, total_accum: -127.40, per_day: [{date:"...", rate_pct: -0.0215, notional: 4400, swap: -0.95}, ...], source: "db" }`
- Implementation: snapshot giornaliero dei rates + notional delle posizioni aperte. Richiede NUOVO sistema storico:
  - Nuova tabella `swap_daily_snapshots` (epic, date, long_rate_pct, short_rate_pct, avg_notional, realized_swap)
  - Scheduled job che salva daily snapshot (scheduler.py)
  - Oppure: computa `rate × notional × days` ma con rates storici interpolati + notional medio delle posizioni aperte quel giorno (proxy da `positions` DB).
- Alternativa MINIMAL: se storico troppo costoso, API ritorna stima basata su rate corrente Capital.com + notional corrente × `days`. Sarebbe comunque fedele al reale se posizione non cambia.
- Frontend: rimuovere calcolo client-side `swap7dAccum` in `overnight-swap.component.ts`, chiamare endpoint via `TradingService.loadSwapAccum(epic)` + signal `swapAccum`.

### Golden rules da rispettare
- **NON toccare** `frontend/src/app/shared/components/tv-chart/` (lightweight-charts pipeline).
- **NON toccare** routing (`app.routes.ts`, `routes.ts`).
- **NON toccare** `core/services/` (ApiService/AuthService/WebSocketService) tranne aggiunta nuovi metodi `TradingService.load*`.
- `datetime.now(timezone.utc).replace(tzinfo=None)` per Postgres writes (asyncpg timezone rule).
- P&L NULL rows always excluded tramite `close_reason != 'UNRECONCILED'` AND `profit_loss IS NOT NULL`.

### Verifica
- Build: `cd frontend && npx ng build --configuration=development 2>&1 | tail -8`
- Tests: `cd backend && .venv/Scripts/python.exe -m pytest tests/api/test_performance_delta.py -v`
- Manual: Playwright probe in `d:/tmp/verify_spine.mjs` estendibile per check Win Rate sub + 7d accum rendering.

### DB stato (già pulito sessione precedente)
- `positions_cascade_backup_20260420` contiene 429 rows `UNRECONCILED` (cascade 2026-04-20 15:01-15:04). **NON ripristinare.** Sono spurious.
- `STALE_CLEANUP` rows (537): automaticamente escluse da `get_breakdown_by_day.going` + `get_performance_stats.pnls`.

### Pronto dopo Phase 4
- Scheduling agent per weekly cleanup check su data quality (cascade/stale detection)
- Phase 5 possibile: websocket live updates per overnight-swap (refresh senza polling)

---

## Note finali
- Caveman mode default `full` (drop fluff).
- User prefers Italian comms, direct push to `main` pre-prod OK.
- Commit convention: `feat(dashboard-v2): ...` — include `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- Ultimo commit main: `25444fd feat(dashboard-v2): fidelity audit pass — mock-aligned cockpit + bug fixes`.

**Audit ref**: `docs/plans/2026-04-24_dashboard-v2-fidelity-audit.md` §10 (Phase 4 opzionali).

**Memoria sessione**: vedi `project_dashboard_v2_fidelity_2026-04-24.md` nell'auto-memory.
