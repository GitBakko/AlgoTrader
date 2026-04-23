# MANTIS AI — Claude Instructions

AI-powered algo trading platform. Capital.com (demo). Python 3.12 backend + Angular 21 frontend. Repo: `GitBakko/AlgoTrader`, main branch `master`, UI branch `ui/mantis-template-integration`.

## Prime Directive

**Before editing any file, read it first. Before modifying a function, grep for all callers. Research before you edit.**

## Golden Rules — DO NOT TOUCH

- **`backend/`** — off limits unless task explicitly says backend.
- **`frontend/src/app/core/services/`** — API/WS/auth logic. Change how data is *displayed*, never the service logic itself.
- **`frontend/src/app/shared/components/tv-chart/`** — `lightweight-charts` integration. Only style its container. Never replace, refactor, or touch data pipeline.
- **Routing** (`app.routes.ts`, view `routes.ts`) — don't change URLs/lazy-loading without explicit ask.
- **Auth** (guards, interceptors, JWT handling) — production-tested, don't touch.
- **`*.spec.ts`** — don't delete or alter unless fixing a broken test.

Free to edit: SCSS (`_custom.scss`, `_palette.scss`, component `.scss`), `.component.html`, component TS display logic only, `layout/default-layout/*`, `shared/components/*` (except tv-chart logic), new presentational components.

## Trading Invariants

1. **Never override strategy-level TP/SL in execution loops** (`paper_loop.py`). Respect `TP_MAX_ATR` and strategy config. When fixing a trade bug, walk full chain: strategy → signal → paper_loop → order.
2. **No hardcoded contract multipliers** in P&L math. Always take P&L from broker `Transaction.size` (TRADE row) or `Position.upl`. No `(exit-entry)*size` fallbacks.
3. **Close detection is 3-tier** — Tier 1 dealId match → Tier 2 10-min retry → Tier 3 UNRECONCILED (pnl=NULL + alert). No code path invents P&L.
4. **Emergency kill switch**: `POST /api/trading/emergency-stop` stops loop + closes all + fires CRITICAL alert.
5. **State recovery**: PAPER → Postgres only. DEMO/LIVE → broker `list_positions()` authoritative, DB fallback only if broker unreachable.

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
- **Never hardcode hex colors.** Always `var(--mantis-*)` or SCSS `$mantis-*` tokens from `_palette.scss`.
- Financial numbers MUST use `.mantis-mono` or `.mantis-kpi` class (tabular figures). Never UI font for prices.
- Icons: CoreUI only (`cil-*`). Do NOT add FontAwesome/Heroicons/other.
- SASS: `color.adjust()` only. `lighten()`/`darken()` deprecated.

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

- Accent: `$mantis-neon` `#39FF14` (CTAs, active, hero), `$mantis-green` `#00d97e` (primary UI), `$mantis-cyan` `#00E5FF` (info).
- Semantic: profit=neon, loss=`#FF3D57`, warning=`#FFB020`, neutral=`#8B949E`.
- Surface elevation 0–5 (`#010409` → `#2d333b`). Use elevation for depth, not borders.
- 8px spacing grid via Bootstrap utilities. Min card body `p-3`, min grid gap `gap-3`.
- Card pattern: `<c-card class="border-top border-top-3 border-top-primary">` (green accent line). Header `py-2 small text-body-secondary`. Body `p-3` (or `p-0` only when chart fills the card).
- Mobile: bottom-nav <768px, sidebar hidden <992px, 44px touch targets, 16px min input font (iOS zoom guard), `.table-responsive-mobile` on every data table.

## Git / CI

- Branch prefixes: `feature/ fix/ refactor/ docs/ ui/`. UI work on `ui/mantis-template-integration`.
- Commit prefix matches branch: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `style:`, `ui:`. Never push directly to `master`.
- Never commit: `.env`, `data/historical/`, `data/models/`, `__pycache__/`, `node_modules/`.
- CI (`.github/workflows/ci.yml`): ruff + black → pytest (coverage floor 80%) → docker build. Pre-commit: ruff, black, mypy, bandit.
- After frontend change: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`. If red, fix before moving on. One task fully done → commit → next.

## Testing

- Patch at **source module**, not where imported.
- Mock `check_exposure_dynamic` (NOT static `check_exposure`).
- Integration tests: hit real DB, not mocks — prior incident where mocked DB tests passed but prod migration failed.

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
