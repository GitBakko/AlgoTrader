# MANTIS AI — Claude Instructions

AI-powered algo trading platform. Capital.com (demo). Python 3.12 backend + Angular 21 frontend. Repo: `GitBakko/AlgoTrader`, default branch `main` (renamed from `master` 2026-04-23).

## Prime Directive

**Before editing any file, read it first. Before modifying a function, grep for all callers. Research before you edit.**

## Golden Rules — DO NOT TOUCH

- **`backend/`** — off limits unless task explicitly says backend.
- **`frontend/src/app/core/services/`** — API/WS/auth logic. Change how data is *displayed*, never the service logic itself.
- **`frontend/src/app/shared/components/tv-chart/`** — `lightweight-charts` integration. Only style its container. Never replace, refactor, or touch data pipeline.
- **Routing** (`app.routes.ts`, view `routes.ts`) — don't change URLs/lazy-loading without explicit ask.
- **Auth** (guards, interceptors, JWT handling) — production-tested, don't touch.
- **`*.spec.ts`** — don't delete or alter unless fixing a broken test.

Free to edit: SCSS (`_palette.scss`, `_custom.scss` entry + themed partials `_sidebar/_header/_footer/_globals/_components/_auth/_mobile/_tables.scss`, component `.scss`), `.component.html`, component TS display logic only, `layout/default-layout/*`, `shared/components/*` (except tv-chart logic), new presentational components.

## Trading Invariants

1. **Never override strategy-level TP/SL in execution loops** (`paper_loop.py`). Respect `TP_MAX_ATR` and strategy config. When fixing a trade bug, walk full chain: strategy → signal → paper_loop → order.
2. **No hardcoded contract multipliers** in P&L math. Always take P&L from broker `Transaction.size` (TRADE row) or `Position.upl`. No `(exit-entry)*size` fallbacks.
3. **Close detection is 3-tier** — Tier 1 dealId match → Tier 2 10-min retry → Tier 3 UNRECONCILED (pnl=NULL + alert). No code path invents P&L.
4. **Emergency kill switch**: `POST /api/trading/emergency-stop` stops loop + closes all + fires CRITICAL alert.
5. **State recovery**: PAPER → Postgres only. DEMO/LIVE → broker `list_positions()` authoritative, DB fallback only if broker unreachable.
6. **SL/TP reconciliation rule** (post 2026-04-28 fix `745f2ee`): when a `TradingSignal` carries BOTH `suggested_stop` and `suggested_tp`, `RiskManager.check_trade` MUST use the pair as-is — strategy authors calibrate the R:R intentionally. Only when one side is missing does the risk-manager ATR default fill in. **Never** mix risk-mgr SL with strategy TP (or vice-versa) — that path produced inverted R:R 0.13–0.30 in production. For BUY-SL the *tighter* value is the LARGER one (closer to entry from below); for SELL-SL it is the SMALLER. See `src/risk/risk_manager.py` §4-bis.
7. **Two-tier sizing floors** (post 2026-04-29 fix `e6efede` + 2026-04-29 fixes `9723dfc`/`b9f31ba`): `MIN_NOTIONAL_USD` (default `$200`) lifts notional in `PositionSizer`/`KellySizer`. `MIN_RISK_AMOUNT_USD` (default `$5`) is the **post-sizing** floor in `RiskManager.check_trade` step 7-bis — uses pip-aware USD risk via `_compute_risk_usd(epic, entry, sl, size)` (USDJPY USD-base = `(size × stop) / entry` JPY→USD; EURUSD/GBPUSD USD-quote + non-forex = `size × stop` already USD). On under-floor: lift size proportionally; **if cap blocks the full lift → take `final_size = min(lifted_size, max_size_by_exposure)` and approve at residual risk** (audit `lift_bounded_by_cap=true`). Reject reserved for non-positive cap (zero/negative equity). USD-base forex pairs (USDJPY/USDCHF/USDCAD) use `_stop_distance_usd = stop_distance / entry` in PositionSizer/KellySizer for correct sizing AND `forex_usd_base_size_multiplier` (default 30, `FOREX_USD_BASE_SIZE_MULTIPLIER` env) on the cap to reflect broker's leverage tier — without it, USDJPY caps at ~14 units producing $0.02 risk per SL hit.
8. **Reconciler split** (post 2026-04-29 commits `5c2e7da`/`10fdd8c`/`9a1f16c`/`5233bbe`): broker-position reconciliation (`_detect_broker_closed` + `_update_trailing_stops` + `_check_stop_losses`) runs in a **dedicated 15s asyncio task** when `RECONCILER_DEDICATED_ENABLED=true` (now default in `.env`), decoupled from the 60s strategy tick. Cuts close-detection lag from up to 20 min (legacy) to <30s. Strategy loop's `_run_iteration` gates those three calls behind `if not self._reconciler_enabled`. Both loops share `self.*` state via asyncio cooperative-model atomicity (no locks needed for data); only re-entrancy lock `self._reconciler_lock` prevents overlapping reconciler ticks. Rollback: set `RECONCILER_DEDICATED_ENABLED=false` + restart → byte-identical legacy behavior. Plan: `docs/handoff/reconciler_split_PLAN.md`.
9. **Strategy-anchored trailing ladder** (post 2026-04-29 commits `8288cad`/`971907d`): `TrailingStopManager.register_position` and `restore_state` accept optional `take_profit`. When provided, TP1 = midpoint(entry, TP) and TP2 = TP — anchors the phase ladder to the strategy's actual target instead of the legacy `risk_multiple × risk_distance` formula. Without this, tight-R:R signals (e.g., MR strategies at 0.25R) had trailing TP1 BELOW the strategy TP, so the broker would TP-close the position before the trailing ladder ever advanced. `breakeven_offset_pct` default flipped `0.001 → 0.0` (pure breakeven, max buffer between current and SL): on tight-stop assets the 0.1% profit lock chopped the post-TP1 buffer to sub-spread and fired SL on noise for $0.02. Always pass `take_profit` from the signal at register time. State recovery looks up `positions.take_profit` and forwards on restart so legacy ladders are migrated.
10. **Idempotent CLOSE Trade row** (post 2026-04-30 fix `ce2c3e1`): `_persist_position_close` does SELECT-then-INSERT on `(position_id, trade_type='CLOSE')`. First writer wins, second caller skips Trade insert but still commits Position update. Prevents duplicate audit rows when v1 + v2 close detectors and dealId-rotation second-chance paths each fire `_finalize_close` for the same disappeared broker position (the duplicate row carried entry price as fallback because the second caller had lost broker context). Frontend audit drawer also dedupes defensively by `MAX(ABS(price - entry_price))` when API returns multiple CLOSE events.

## Backend Gotchas

- `datetime.now(timezone.utc)` always. NEVER `datetime.utcnow()` (deprecated).
- **asyncpg rejects tz-aware datetimes** on `TIMESTAMP WITHOUT TIME ZONE` columns. For any Postgres write: `datetime.now(timezone.utc).replace(tzinfo=None)`.
- Technical indicators: **pure Polars/numpy**. Do NOT add `ta-lib`.
- Dependency manager is **pip** + venv (Windows: `.venv/Scripts/python.exe`). NOT poetry.
- Pydantic v2 for all I/O boundaries. Loguru for logs. `pydantic-settings` + `.env` for config — never commit secrets.
- All frontend-facing responses: `{success: bool, data: T, error?: string}`.
- Request correlation: `X-Request-ID` header auto-injected into log `extra` via `logger.contextualize`.

## Capital.com API Gotchas

- REST base: demo `https://demo-api-capital.backend-capital.com/`, live `https://api-capital.backend-capital.com/`. WS `wss://api-streaming-capital.backend-capital.com/connect`.
- Auth: api-key + email + password → CST + X-SECURITY-TOKEN, **10-min expiry**. Session manager handles refresh.
- Epic mapping (`EPIC_TO_BROKER`): `XAUUSD→GOLD`, `XAGUSD→SILVER`, `WTIUSD→OIL_CRUDE`. Transaction history uses **broker epics** (`OIL_CRUDE`, `DE40`, `NATURALGAS`) — NOT display names like "Oil - Crude".
- OHLC prices come as `{bid, ask}` dicts — always use mid-price.
- **`Position` model has NO `current_price` field** — only `level` (entry) and `upl`. Live mid-price comes from the WS quote stream, REST `get_market_details(epic).snapshot.{bid,offer}`, or UPL reconstruction (`current ≈ entry + sign*upl/size`). Never store `level` as live price.
- Rate limits: 10 req/sec, 40 WS subs, 1000 orders/hour (demo).
- `/history/transactions`:
  - Params `from`/`to` MUST be naive `yyyy-MM-dd'T'HH:mm:ss` (no `Z`, no offset). Server rejects tz suffix with `error.invalid.from` (HTTP 400).
  - `type=ALL` / `type=ALL_DEAL` → **returns 0** (broker silently rejects). Use `type=TRADE` (default in our client) or drop param.
  - TRADE row schema: `transactionType`, `dealId` (= Position.deal_id — **deterministic match key**), `reference` (internal txn id, NOT deal_reference), `size` (**string = realized P&L for TRADE rows**), `note`, `currency` ("USDd" on demo). No `openLevel`/`closeLevel`/`profitAndLoss` on current live responses.

## Frontend Conventions (Angular 21)

- Standalone components only (no NgModules). Strict TS. `ChangeDetectionStrategy.OnPush` everywhere.
- **Prefer Signals** over RxJS. HttpClient with `withFetch()`.
- **No `console.log`** in production code. `console.error`/`console.warn` only for real errors.
- API calls: use `ApiService` (prepends apiUrl). Never raw `HttpClient`.
- **Async action buttons**: use `<app-loading-button [loading]="isBusy()" (clicked)="…">`.
- **NO MOCK DATA NELLE MASCHERE** — invariant. Charts/sparklines/lists must source from persisted backend tables. No `syntheticSpark`, no in-memory ws-only ring buffers, no fabricated placeholders. KPI sparklines read `paperPnlHistory()`; position-card chart reads `positionPnlHistory()[deal_id]` (60s `paper_pnl_snapshots` / `position_pnl_snapshots`).
- **Never hardcode hex colors.** Always `var(--mantis-*)` or SCSS `$mantis-*` tokens from `_palette.scss`.
- Financial numbers MUST use `.mantis-mono` or `.mantis-kpi` class (tabular figures). Never UI font for prices.
- Icons: CoreUI only (`cil-*`). Do NOT add FontAwesome/Heroicons/other.
- SASS: `color.adjust()` only. `lighten()`/`darken()` deprecated.
- **Don't trigger fetches from `effect()` when the effect writes signals**: combined with other effects that read the same source signals, Angular's signal scheduler can re-evaluate endlessly (history-tab infinite-loop bug `1cdd48f`). Pattern: read-only effect that defers mutations via `queueMicrotask`, OR call fetch from explicit user action (click handler, `setTab`).
- **`livePosition` lookups MUST match by `deal_id`, not `epic`**: epic-only matching falsely flags closed audits as GOING when a newer position on the same epic is open (badge bug `dea2a29`).

### UI Anti-patterns

- `!important` (unless overriding inaccessible CoreUI default).
- Inline styles in templates.
- Fixed pixel heights on content containers (breaks responsive).
- `z-index > 1050` (CoreUI modals reserve 1050).
- Global element selectors (`div`, `span`, `p`) — always scope.
- `ViewChild` for styling. `setTimeout` for visual timing. Unsubscribed observables (use `takeUntilDestroyed` or signals).
- White background in dark mode. Neon green (`#39FF14`) on large areas — accent only.
- Animating frequently-updating data (tables, live P&L).
- Page-blocking spinners — use skeleton or inline.

### Design tokens (authoritative source: `frontend/src/scss/_palette.scss`)

> **Style Bible:** per regole di pattern (CARD-*, HDR-*, TBL-*, BTN-*, CHIP-*, FRM-*, KPI Pattern, Live Feed, Top 12 Violazioni VIO-*) la sorgente di verità è **`STYLE_BIBLE.md`** in root del repo (v1.0, 27/04/2026). I tokens elencati qui sotto restano in `_palette.scss`; la Bible aggiunge le regole di **composizione** dei tokens in pattern. Quando audisci una pagina, parti dalla `Top 12 Violazioni` (Bible §3) e dal pattern di pagina applicabile (HDR-01 cockpit, HDR-02 list, HDR-03 settings).

- Accent: `$mantis-neon` `#39FF14` (CTAs, active, hero), `$mantis-green` `#00d97e` (primary UI), `$mantis-cyan` `#00E5FF` (info).
- Semantic: profit=neon, loss=`#FF3D57`, warning=`#FFB020`, neutral=`#8B949E`.
- Surface elevation 0–5 (`#010409` → `#2d333b`). Use elevation for depth, not borders.
- Spacing scale tokens `var(--mantis-space-0..12)` (0, 4, 8, 12, 16, 20, 24, 32, 40, 48 px) — prefer over literal rem/px.
- Type scale tokens `var(--mantis-fs-xxs..5xl)` (9→48 px). Body 14 px = `fs-body`. Never inline `font-size: 0.875rem`.
- Radius tokens `var(--mantis-radius-sm|md|lg|xl|pill)` (4, 8, 12, 24, 100 px). Per le card di pagina la Bible standardizza su `sm` (4) e `md` (6-8) — evita `lg`/`xl` salvo modali/dropdown specifici.
- Shadow tokens `var(--mantis-shadow-sm|md|lg)` + glows `var(--mantis-glow-green|neon)` (nulled in light theme).
- Easing tokens `var(--mantis-ease-out-expo|out-back|ripple)`, duration `var(--mantis-dur-fast|normal|slow|reveal)`.
- Semantic role aliases `var(--fg1|fg2|fg3|fg-accent|fg-disabled|bg1..bg5)` re-resolve per theme via the vars above.
- Card pattern: `<c-card class="border-top border-top-3 border-top-primary">` (green accent line). Header `py-2 small text-body-secondary`. Body `p-3` (or `p-0` only when chart fills the card).
- KPI card pattern: `.xxx-kpi-card` wrapper + absolute `__accent` **top bar** (3 px height, full width) with `--primary`/`--profit`/`--loss`/`--warning` variant — **never** a left-bar (flipped 2026-04-23). See `dashboard.component.scss`, `paper-trading.component.scss` for reference.
- Mobile: bottom-nav <768px, sidebar hidden <992px, 44px touch targets, 16px min input font (iOS zoom guard), `.table-responsive-mobile` on every data table.
- Internal `/design-system` route renders live token values + all badge / pill / KPI / form previews for dev reference (not in sidebar).

## Backend data contracts

- **60s P&L snapshot system** — `paper_pnl_snapshots` (global figures) + `position_pnl_snapshots` (per deal). `PnlSnapshotScheduler` in `backend/src/data/pnl_snapshot_scheduler.py` (APScheduler 60s + 04:30 UTC prune). Live prices via WS quote cache (`broker_ws._quote_listeners` fan-out) → REST `get_market_details` fallback → UPL reconstruction. Endpoints: `/api/trading/pnl-history`, `/api/trading/positions/{deal_id}/pnl-history`. Migration `c3d8e9f0a1b2`.
- **Logo service resilience** — `LogoService.getLogoUrls(epic): string[]` returns a static fallback chain (no API calls). `EpicLogoComponent` walks chain via `<img onerror>`. Final entry is always an inline SVG `data:` URI. Cache key `mantis-logos-v2`.

## Active revamp tracks

Stato delle 14 pagine MANTIS al 29/04/2026 — Style Bible audit pass complete.

| # | Pagina | Stato | Commit |
|---|---|---|---|
| 01 | Dashboard | ✅ DONE (v2 cockpit, in `views/dashboard-v2/`) | — |
| 02 | Paper Trading | ✅ DONE (PR #8/9/10/11 + Bible §3 audit `a8971b6`) | `docs/handoff/paper-trading/STYLE_BIBLE_AUDIT_2026-04-29.md` |
| 03 | Posizioni | ✅ DONE (HDR-02 + sticky thead + zebra off) | `a26b558` |
| 04 | Trade Journal | ✅ DONE (HDR-02 + Bible buttons) | `2f0d273` |
| 05 | Segnali AI | ✅ DONE (HDR-02 + Bible buttons + zebra off) | `ada2af9` |
| 06 | Backtest | ✅ DONE (HDR-02 + Bible buttons + skeleton loading + form labels) | `592c017` |
| 07 | Strategia | ✅ DONE (HDR-03 + form tokens) | `81de886` |
| 08 | Modelli AI | ✅ DONE (HDR-03 + Bible buttons + VIO-08 fix) | `96e7041` |
| 09 | Risk Manager | ✅ COVERED (no standalone view — content in Strategia + Settings) | — |
| 10 | Broker | ✅ COVERED (Capital.com config in Settings) | — |
| 11 | Notifications | ✅ DONE (HDR-02 + Bible buttons + FRM-01 labels) | `0724dd9` |
| 12 | Settings | ✅ DONE (HDR-03 + Bible buttons + form tokens) | `c8d1724` |
| 13 | Login | ✅ CONFORME | — |
| 14 | System Logs | ✅ CONFORME | — |

**Audit complete.** Tutte le pagine ora CONFORME alla Bible §3 (VIO-01..12). Future audit: applicare check on each new view.

CoreUI template demo purge 2026-04-29 (`1acc795`): rimossi `views/notifications/{alerts,badges,modals,toasters}/` + `src/components/{docs-callout,docs-components,docs-example,docs-icons,docs-link}/` (zero consumer esterni).

## Git / CI

- Branch prefixes: `feature/ fix/ refactor/ docs/ ui/`. UI work on `ui/mantis-template-integration`.
- Commit prefix matches branch: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `style:`, `ui:`. Never force-push to `main`; direct push without PR is OK while pre-production (repo still <10 users, 0 external stakeholders).
- Never commit: `.env`, `data/historical/`, `data/models/`, `__pycache__/`, `node_modules/`.
- CI (`.github/workflows/ci.yml`): ruff + black → pytest (coverage floor 80%) → docker build. Pre-commit: ruff, black, mypy, bandit.
- After frontend change: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`. If red, fix before moving on. One task fully done → commit → next.

## Testing

- Patch at **source module**, not where imported.
- Mock `check_exposure_dynamic` (NOT static `check_exposure`).
- Integration tests: hit real DB, not mocks — prior incident where mocked DB tests passed but prod migration failed.
- **Strategy-manager tests must mock `get_settings`** to set `mr_primary_enabled=False` / `ml_primary_enabled=False` if they want the legacy `_process_default()` path. Production `.env` ships both flags `true` so any test that doesn't mock will route through MR/ML primary chains and hit HOLD when market_data is sparse. Pre-existing baseline ~28 fails are stuck on this pattern + incomplete async mocks (`MagicMock` where `AsyncMock` is required).

## Local Ops Cheatsheet

- Backend run: `cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
- Backend tests: `.venv/Scripts/python.exe -m pytest tests/ -v`
- Frontend dev: `cd frontend && npx ng serve --port 4321`
- Retrain all models: `curl -X POST http://localhost:8000/api/models/retrain-all` (uses orchestrator).
- Initial capital default: `$11,000` (`INITIAL_CAPITAL` env).
- GitHub CLI: `"/c/Program Files/GitHub CLI/gh.exe" run list -R GitBakko/AlgoTrader`.

## Graceful Degradation

App runs without Postgres, Redis, or DuckDB. Don't add hard dependencies on them — always guard with try/except and fall back to in-memory state + log at DEBUG.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

## Ruflo Integration (optional)

Ruflo MCP server is registered globally (`~/.claude.json`) and project-locally (`.mcp.json`). Project-level assets live in `.claude-flow/` (runtime), `.claude/agents/` (98 agent templates), `.claude/commands/`, `.claude/helpers/`. Memory DB: `.swarm/memory.db` (primary, sqlite + HNSW + temporal decay) + `.claude/memory.db` (mirror). Vector DB: `ruvector.db`. Daemon PID: `.claude-flow/daemon.pid`. **Do NOT run `ruflo init --force` again** — it overwrites `CLAUDE.md`, `.mcp.json`, `.claude/settings.json` regardless of `--skip-claude`/`--minimal`/`--no-global`/`--preset` flags (v3.7.0-alpha.14 AND .38 both confirmed bugged). Use `ruflo init upgrade` for future updates.

Services bootstrap (after init):
```bash
ruflo daemon start    # background workers (PID written to .claude-flow/daemon.pid)
ruflo memory init     # sqlite schema + HNSW + controllers (15/23 activated)
ruflo memory stats    # health check
ruflo daemon stop     # stop daemon
```

### Agent Comms (SendMessage-First)

Named agents coordinate via `SendMessage`, not polling or shared state. ALL agents in ONE message with `run_in_background: true`; lead kicks off pipeline via `SendMessage`.

Patterns: **Pipeline** A→B→C (sequential dependencies) · **Fan-out** Lead→A,B,C→Lead (independent parallel) · **Supervisor** Lead↔workers (ongoing coordination).

### Memory & Routing

```bash
# Before any task
ruflo memory search --query "[task keywords]" --namespace patterns
ruflo hooks route --task "[task description]"

# After success
ruflo memory store --namespace patterns --key "[name]" --value "[what worked]"
ruflo hooks post-task --task-id "[id]" --success true --store-results true
```

### Key MCP Tools (discover via `ToolSearch("ruflo <keyword>")`)

| Category | Key tools |
|----------|-----------|
| Memory | `memory_store`, `memory_search`, `memory_search_unified` |
| Swarm | `swarm_init`, `swarm_status`, `swarm_health` |
| Agents | `agent_spawn`, `agent_list`, `agent_status` |
| Hooks | `hooks_route`, `hooks_post-task`, `hooks_worker-dispatch` |
| Security | `aidefence_scan`, `aidefence_is_safe`, `aidefence_has_pii` |
| Hive-Mind | `hive-mind_init`, `hive-mind_consensus`, `hive-mind_spawn` |

### When to Swarm

- **YES**: 3+ files, new features, cross-module refactor, API changes, security, performance
- **NO**: single file edits, 1-2 line fixes, docs updates, config, questions

### Background Workers (`ruflo hooks worker dispatch --trigger X`)

| Worker | When |
|--------|------|
| `audit` | After security changes |
| `optimize` | After performance work |
| `testgaps` | After adding features |
| `map` | Every 5+ file changes |
| `document` | After API changes |
