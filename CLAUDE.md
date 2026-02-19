# MANTIS AI - Claude Code Instructions

## Project Overview
MANTIS AI is an AI-powered algorithmic trading platform for **21 assets** across Forex, Crypto, Commodities, Indices, and Stocks using Capital.com as broker (demo).

**Assets**: XAUUSD, BTCUSD, US500, WTIUSD, EURUSD, NVDA, TSLA, XAGUSD, DE40, SOLUSD, ETHUSD, BNBUSD, DOGUSD, DASHUSD, ICPUSD, NATGAS, COPPER, PLATINUM, GBPUSD, USDJPY, NAS100

## Tech Stack
- **Backend**: Python 3.12+ (FastAPI, PyTorch, XGBoost, Polars, numpy)
- **Frontend**: Angular 21 + CoreUI Free Template (Bootstrap 5, TradingView Lightweight Charts, dark mode)
- **Broker**: Capital.com REST API + WebSocket (demo mode)
- **Database**: PostgreSQL (trades, users, RBAC) + DuckDB (market data analytics)
- **Cache/Queue**: Redis (real-time state, pub/sub events) — all DBs optional, graceful degradation
- **ML Models**: XGBoost 3-class (F1 0.53-0.61), 220+ features (technical + sentiment + macro), Optuna tuning, isotonic calibration
- **External APIs**: Finnhub (equity data), Marketaux (news sentiment), yfinance (VIX/DXY/10Y yield)

## Repository & GitHub
- **Repo**: `https://github.com/GitBakko/AlgoTrader`
- **Main branch**: `master`
- **UI migration branch**: `ui/mantis-template-integration`

---

## Project Structure
```
AlgoTrader/
├── backend/
│   ├── src/
│   │   ├── api/               # FastAPI endpoints + middleware (GZip, CORS, rate limiting)
│   │   ├── auth/              # Authentication (JWT, RBAC, models, schemas, dependencies)
│   │   ├── audit/             # Audit logging system
│   │   ├── broker/            # Capital.com API wrapper (REST + WebSocket)
│   │   ├── data/              # Data pipeline (collection, cleaning, storage)
│   │   ├── database/          # PostgreSQL session, repositories, backup manager
│   │   ├── features/          # Feature engineering (220 features: technical, candlestick, fibonacci, keltner, vwap, market structure)
│   │   ├── execution/         # Order execution engine + state recovery + partial close (DEMO: close-then-reopen)
│   │   ├── models/            # ML models (XGBoost, LSTM, calibration, tuner, versioning)
│   │   ├── monitoring/        # Health checks, trade logger, log analyzer, alerting (Email/Slack/Telegram/Webhook), metrics
│   │   ├── risk/              # Risk management (circuit breakers, Kelly, trailing stops, equity curve filter)
│   │   ├── security/          # Encrypted secrets (Fernet), security models
│   │   ├── strategy/          # Strategies (ML, squeeze, VWAP, pairs, strategy router)
│   │   ├── trading/           # Paper/demo trading loop + emergency stop
│   │   └── utils/             # Config, avatar handler, event bus, sanitization
│   ├── tests/                 # 1136+ pytest tests (69% coverage, 80%+ on critical modules)
│   ├── scripts/               # init_permissions.py, promote_user_to_god.py, train/download scripts
│   ├── alembic/               # Database migrations
│   └── data/                  # Local storage (historical, models, avatars, logs, backups)
├── frontend/                  # Angular 21 + CoreUI (MANTIS AI theme)
│   ├── src/app/
│   │   ├── core/              # Services (auth, trading, websocket, market-status, news, monitoring)
│   │   │   ├── guards/        # Auth guard, permission guard (RBAC)
│   │   │   ├── interceptors/  # Auth interceptor (JWT), error interceptor
│   │   │   └── services/      # All injectable services
│   │   ├── shared/            # Reusable components (avatar, avatar-upload, epic-logo, tv-chart, news-widget)
│   │   ├── views/             # Page components (dashboard, markets, positions, signals, backtest, etc.)
│   │   └── layout/            # Default layout with sidebar, header, user dropdown
│   └── src/scss/              # MANTIS AI theme (_custom.scss, _palette.scss)
├── infra/                     # Prometheus config, Grafana dashboards
├── docs/                      # Project documentation
│   ├── architecture/          # System design, API reference, state recovery
│   ├── trading/               # ML strategy, Capital.com API, trading concepts
│   ├── guides/                # Setup guide, frontend guide
│   ├── planning/              # Development roadmap, next steps
│   └── archive/               # Historical research docs
├── docker-compose.yml         # Dev stack (PG, Redis, backend, frontend, pgAdmin, Redis Commander)
└── docker-compose.prod.yml    # Production override (4 workers, memory limits, no bind mounts)
```

---

## ⚠️ GOLDEN RULES — Read Before EVERY Task

### What You MUST NOT Touch
1. **Backend code** — `backend/` is OFF LIMITS unless explicitly asked
2. **Business logic in services** — Files in `core/services/` contain API integration, WebSocket, auth logic. NEVER modify the logic, only the way data is displayed
3. **TradingView chart** — `shared/components/tv-chart/` uses `lightweight-charts` library. DO NOT replace, remove, or refactor this component. Only style its container
4. **Routing structure** — `app.routes.ts` and view-level `routes.ts` files define the app navigation. Do not change URLs or lazy-loading unless explicitly asked
5. **Auth flow** — Guards, interceptors, JWT handling are production-tested. Do not touch
6. **Test files** — Do not delete or modify `*.spec.ts` files unless fixing a broken test

### What You CAN Modify Freely
1. **SCSS files** — `src/scss/_custom.scss`, `src/scss/_palette.scss`, component `.scss` files
2. **HTML templates** — Any `.component.html` file (layout, structure, classes)
3. **Component TypeScript** — Display logic, signal bindings, UI state only (not service calls)
4. **Layout components** — `layout/default-layout/` (header, footer, sidebar, nav)
5. **Shared UI components** — `shared/components/` (excluding tv-chart logic)
6. **New components** — Create new shared/presentational components as needed

### The One-Task Rule
- Complete ONE task fully before starting the next
- After each change, verify the app compiles: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`
- If build fails, FIX IT before proceeding. Never leave broken builds
- Commit after each successful task with conventional commit message

---

## Development Conventions

### Python (Backend)
- Use **Python 3.12+** with type hints everywhere
- Follow **PEP 8** with max line length 100
- Use **async/await** for I/O-bound operations (API calls, WebSocket, DB)
- Use **Pydantic v2** models for all data validation and serialization
- Use **pytest** for testing with minimum 80% coverage on critical paths
- Use **loguru** for structured logging
- Configuration via **pydantic-settings** with `.env` files (never commit secrets)
- Use **pip** (venv) for dependency management — NOT poetry
- Use `datetime.now(timezone.utc)` — NEVER `datetime.utcnow()` (deprecated)
- **CRITICAL**: For PostgreSQL writes, use `datetime.now(timezone.utc).replace(tzinfo=None)` — asyncpg rejects timezone-aware datetimes with `TIMESTAMP WITHOUT TIME ZONE` columns
- Technical indicators: pure **Polars/numpy** — no ta-lib dependency

### Angular (Frontend)
- Angular 21 with **standalone components** (no NgModules)
- CoreUI Free template as base, MANTIS AI dark theme
- **Strict TypeScript** mode enabled
- Use **Angular Signals** for reactive state management
- Use **Angular HttpClient** with `withFetch()` for API communication
- All components use `ChangeDetectionStrategy.OnPush`
- Use **RxJS** sparingly, prefer Signals where possible
- No `console.log` in production code — use `console.error`/`console.warn` only for real errors

### Git Conventions
- Branch naming: `feature/`, `fix/`, `refactor/`, `docs/`, `ui/`
- Commit messages: conventional commits (feat:, fix:, refactor:, docs:, test:, style:, ui:)
- Never commit: `.env`, `data/historical/`, `data/models/`, `__pycache__/`, `node_modules/`
- For UI work: use prefix `ui:` in commit messages (e.g., `ui: redesign dashboard KPI cards`)

### API Design
- Backend exposes REST API via FastAPI on port 8000
- Frontend on port 4321
- All API responses follow envelope: `{ success: bool, data: T, error?: string }`
- Auth: JWT tokens (Bearer), RBAC with roles (VIEWER, TRADER, ADMIN)
- Rate limiting: slowapi on auth endpoints (10/min login, 5/hour register)
- GZip compression on responses > 1KB
- WebSocket for real-time price streaming and trade updates
- Security headers: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, HSTS (production only)
- CORS: explicit `allow_methods`/`allow_headers` (not wildcards)
- Request correlation: `X-Request-ID` header on all responses, injected via `logger.contextualize`

### Logging & Monitoring

- **Loguru** structured logging: text sink (`logs/mantis.log`) + JSON sink (`logs/mantis.json.log`, `serialize=True`)
- **Request correlation IDs**: UUID per request in `X-Request-ID` header, auto-injected into log `extra`
- **Prometheus metrics**: `/metrics` endpoint (guarded by `ENABLE_METRICS=true`), MetricsCollector wired into signals, executions, predictions, circuit breakers
- **Grafana dashboards**: `docker-compose --profile monitoring up` → Prometheus (:9090) + Grafana (:3000)

### CI/CD

- `.github/workflows/ci.yml`: pip-based (not Poetry), `backend-lint` (ruff+black) → `backend-tests` (pytest, coverage 80%) → `docker-build`
- Pre-commit hooks (backend): ruff, black, mypy, bandit

---

## Key Design Decisions
1. **Risk-first design** - Every trade must pass risk management checks before execution
2. **Regime detection** - Separate strategies for trending vs ranging markets (StrategyRouter)
3. **Walk-forward optimization** - Rolling window training to avoid overfitting
4. **Paper trading first** - Always validate on demo before live trading
5. **Graceful degradation** - App works without PostgreSQL, Redis, or DuckDB
6. **State recovery** - PAPER→PostgreSQL, DEMO/LIVE→Broker API+DB fallback
7. **Alert system** - TradeLogger fires alerts (Email/Slack/Telegram/Webhook) in DEMO/LIVE mode; off by default (`ALERTS_ENABLED=false`)
8. **Emergency kill switch** - `POST /api/trading/emergency-stop` stops loop + closes all positions + fires CRITICAL alert

---

## Environment Setup
```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt  # Windows
# OR: py -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest tests/ -v  # Run tests

# Frontend
cd frontend
npm install
npx ng serve --port 4321

# Auth setup (after DB migration)
cd backend
.venv/Scripts/python.exe scripts/init_permissions.py   # Create RBAC roles/permissions
.venv/Scripts/python.exe scripts/promote_user_to_god.py # Promote user to ADMIN
```

## Capital.com API
- Demo: `https://demo-api-capital.backend-capital.com/`
- Live: `https://api-capital.backend-capital.com/`
- WebSocket: `wss://api-streaming-capital.backend-capital.com/connect`
- Auth: API key + email + password → CST + X-SECURITY-TOKEN (10min expiry)
- Epic mapping: XAUUSD→GOLD, XAGUSD→SILVER, WTIUSD→OIL_CRUDE
- OHLC prices: `{bid, ask}` dicts → use mid-price
- Rate limit: 10 req/sec, max 40 WebSocket subscriptions, 1000 orders/hour (demo)

---
---

# 🎨 UI DESIGN SYSTEM — MANTIS AI

> **This section is the single source of truth for ALL visual decisions.**
> When in doubt about any UI choice, refer here FIRST.

---

## Design Philosophy

MANTIS AI follows a **"Bloomberg meets modern fintech"** design language:
- **Dark-first**: Trading platforms are used in dark environments. Light theme supported via `_light-theme.scss` but dark is the primary design target
- **Data-dense but not cluttered**: Every pixel serves a purpose
- **Hierarchy through elevation**: Use surface levels, not borders, to create depth
- **Neon accent as signal**: Green (#39FF14) draws attention to actionable/important elements — use sparingly
- **Numbers are sacred**: All financial data uses monospace font with tabular figures

---

## Color Palette Reference

All colors are defined in `src/scss/_palette.scss`. NEVER hardcode hex values in components — always use CSS variables or SCSS variables.

### Primary Colors
| Token                  | Value      | Usage                                      |
|------------------------|------------|---------------------------------------------|
| `$mantis-neon`         | `#39FF14`  | Hero accent, active states, CTAs            |
| `$mantis-green`        | `#00d97e`  | Primary UI color, links, buttons            |
| `$mantis-cyan`         | `#00E5FF`  | Secondary accent, info states               |

### Semantic Colors
| Token                  | Value      | Usage                                      |
|------------------------|------------|---------------------------------------------|
| `$mantis-profit`       | `#39FF14`  | Positive P&L, BUY signals, success          |
| `$mantis-loss`         | `#FF3D57`  | Negative P&L, SELL signals, errors          |
| `$mantis-warning`      | `#FFB020`  | Alerts, caution states, HOLD signals        |
| `$mantis-neutral`      | `#8B949E`  | Muted text, disabled states                 |

### Surface Elevation System (6 levels)
| Level | Token              | Value      | Usage                                    |
|-------|--------------------|------------|------------------------------------------|
| 0     | `$mantis-surface-0`| `#010409`  | Void / deepest background                |
| 1     | `$mantis-surface-1`| `#0d1117`  | Body background                          |
| 2     | `$mantis-surface-2`| `#161b22`  | Cards, sidebar                           |
| 3     | `$mantis-surface-3`| `#1c2128`  | Dropdowns, popovers                      |
| 4     | `$mantis-surface-4`| `#21262d`  | Modals, toasts                           |
| 5     | `$mantis-surface-5`| `#2d333b`  | Tooltips                                 |

### Border System
| Token                    | Value                           | Usage                   |
|--------------------------|----------------------------------|-------------------------|
| `$mantis-border-subtle`  | `rgba(255,255,255,0.06)`        | Dividers between items  |
| `$mantis-border-default` | `rgba(255,255,255,0.10)`        | Card borders            |
| `$mantis-border-accent`  | `rgba($mantis-green, 0.15)`     | Active card borders     |
| `$mantis-border-strong`  | `rgba($mantis-green, 0.30)`     | Focused/hover states    |

### Usage Rules
```
✅ DO: color: var(--mantis-profit);
✅ DO: background: $mantis-surface-2;
✅ DO: border: 1px solid var(--mantis-border-accent);

❌ DON'T: color: #39FF14;              (hardcoded)
❌ DON'T: background: #161b22;         (magic number)
❌ DON'T: border: 1px solid green;     (generic)
```

---

## Typography

### Font Stacks (already loaded via Google Fonts)
| Purpose       | Font              | Variable               | Usage                                  |
|---------------|-------------------|------------------------|-----------------------------------------|
| UI text       | Plus Jakarta Sans | `$mantis-font-ui`     | All labels, headings, body text         |
| Numbers/KPIs  | IBM Plex Mono     | `$mantis-font-mono`   | Prices, P&L, percentages, timestamps   |

### Type Scale
| Element           | Size      | Weight | Font        |
|-------------------|-----------|--------|-------------|
| Page title (h1)   | 1.5rem    | 700    | UI          |
| Section title (h2)| 1.125rem  | 600    | UI          |
| Card title (h3)   | 0.9375rem | 600    | UI          |
| Body text          | 0.875rem  | 400    | UI          |
| Small/caption      | 0.75rem   | 400    | UI          |
| KPI large          | 1.75rem   | 700    | Mono        |
| KPI medium         | 1.25rem   | 700    | Mono        |
| Price/number       | inherit   | 600    | Mono        |
| Badge/tag          | 0.6875rem | 600    | UI          |

### Rules
- ALL numbers displaying financial data MUST use `.mantis-mono` or `.mantis-kpi` class
- Never mix UI font for prices — inconsistent digit widths cause layout shifts
- Use `font-feature-settings: "tnum" 1` for tabular figures (already in `.mantis-mono`)

---

## Spacing System

Use Bootstrap 5 spacing utilities mapped to an 8px grid:

| Class    | Value  | Usage                                      |
|----------|--------|--------------------------------------------|
| `.p-1`   | 4px    | Tight inner padding (badges)               |
| `.p-2`   | 8px    | Default inner padding                      |
| `.p-3`   | 16px   | Card body padding                          |
| `.p-4`   | 24px   | Section padding                            |
| `.gap-2` | 8px    | Default flex gap                           |
| `.gap-3` | 16px   | Card grid gap                              |
| `.mb-3`  | 16px   | Default bottom margin between sections     |
| `.mb-4`  | 24px   | Between major page sections                |

### Rules
- Minimum card body padding: `p-3` (16px)
- Minimum gap between cards: `gap-3` (16px)
- Content never touches card edges — always has padding
- Consistent vertical rhythm: use `mb-3` between related items, `mb-4` between sections

---

## Component Patterns

### Cards (Primary Container)
Every content block is wrapped in a CoreUI card. Pattern:

```html
<c-card class="border-top border-top-3 border-top-primary">
  <c-card-header class="d-flex align-items-center justify-content-between py-2">
    <span class="fw-semibold small text-body-secondary">Card Title</span>
    <!-- Optional: badge, action button -->
  </c-card-header>
  <c-card-body class="p-3">
    <!-- Content here -->
  </c-card-body>
</c-card>
```

Rules:
- Cards always have `border-top border-top-3 border-top-primary` for the green accent line
- Card headers are compact: `py-2`, small font, `text-body-secondary`
- Card bodies: `p-3` minimum padding
- Use `.mantis-card-gradient` class for hero/featured cards only (sparingly)

### KPI Cards
```html
<c-card class="border-top border-top-3 border-top-primary h-100">
  <c-card-body class="p-3">
    <div class="text-body-secondary small mb-1">Label</div>
    <div class="mantis-kpi fs-4">$12,345.67</div>
    <div class="small mt-1">
      <span class="text-success">▲ +2.34%</span>
      <span class="text-body-secondary ms-1">24h</span>
    </div>
  </c-card-body>
</c-card>
```

Rules:
- KPI value ALWAYS uses `.mantis-kpi` class
- Profit: `text-success` or `color: var(--mantis-profit)`
- Loss: `text-danger` or `color: var(--mantis-loss)`
- Always include a comparison context (24h, vs yesterday, etc.)

### Tables
```html
<table cTable [hover]="true" [small]="true" class="mb-0">
  <thead>
    <tr class="text-body-secondary">
      <th class="fw-semibold small">Column</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="mantis-mono">Value</td>
    </tr>
  </tbody>
</table>
```

Rules:
- Always use `[small]="true"` for data-dense tables
- Always use `[hover]="true"` for interactive tables
- Header text: `.text-body-secondary .fw-semibold .small`
- Numeric cells: `.mantis-mono`
- P&L cells: Add `.text-success` or `.text-danger` dynamically
- Wrap in `.table-responsive-mobile` for mobile support
- Hide non-essential columns on mobile with `.d-mobile-none`

### Buttons
```html
<!-- Primary action -->
<button cButton color="primary" size="sm" class="mantis-btn-primary">Action</button>

<!-- Secondary action -->
<button cButton color="primary" variant="outline" size="sm" class="mantis-btn-secondary">Cancel</button>

<!-- Danger action -->
<button cButton color="danger" size="sm">Close Position</button>
```

Rules:
- Default size: `size="sm"` for data-dense interfaces
- Use `.mantis-btn-primary` for the neon green glow effect
- Destructive actions (close position, delete): red `color="danger"`
- Max 2 buttons per card header
- Icon-only buttons: use `cButton [variant]="'ghost'" size="sm"`
- **Async action buttons**: Use `<app-loading-button>` (shows inline spinner, disables during operation):

```html
<app-loading-button color="danger" size="sm" [loading]="isClosing()" (clicked)="close()">
  Chiudi
</app-loading-button>
```

### Direction Indicators (BUY/SELL)
```html
<span class="dir-indicator dir-indicator--buy">▲ BUY</span>
<span class="dir-indicator dir-indicator--sell">▼ SELL</span>
```

### Signal Status Badges
```html
<span class="signal-status signal-status--executed">
  <span class="signal-status__dot"></span> Executed
</span>
```

Available modifiers: `--executed`, `--rejected`, `--exec_failed`, `--predicted`, `--hold`

### Empty States
```html
<div class="empty-state">
  <div class="empty-state__icon">📊</div>
  <div class="empty-state__text">Nessun segnale attivo</div>
  <div class="empty-state__hint">I segnali appariranno quando il modello genererà previsioni</div>
</div>
```

### Live Indicators
```html
<span class="pulse-dot"></span>           <!-- Green pulsing dot — market open -->
<span class="pulse-dot pulse-dot--danger"></span>  <!-- Red pulsing dot — error/alert -->
```

### Section Dividers
```html
<div class="section-divider">
  <span class="section-divider__label">Trading</span>
  <div class="section-divider__line"></div>
</div>
```

---

## Layout Rules

### Dashboard Grid
- Use Bootstrap 5 grid: `c-row` + `c-col`
- Default layout: 12-column grid
- KPI row: 4 columns on desktop (`c-col-md-6 c-col-xl-3`), 2 on tablet, scroll-strip on mobile
- Chart area: full width (`c-col-12`) or 8+4 split with sidebar info
- Tables: full width (`c-col-12`)
- Always use `.g-3` or `.g-4` for gutters

### Responsive Breakpoints
| Breakpoint | Width    | Behavior                              |
|------------|----------|---------------------------------------|
| xs         | < 576px  | Single column, scroll strips, bottom nav |
| sm         | ≥ 576px  | Minor adjustments                     |
| md         | ≥ 768px  | 2-column layouts begin                |
| lg         | ≥ 992px  | Sidebar visible, 3-column possible    |
| xl         | ≥ 1200px | Full layout, 4-column KPI row         |
| xxl        | ≥ 1400px | Extra breathing room                  |

### Mobile Rules
- Bottom navigation (`bottom-nav` component) visible below 768px
- Sidebar hidden below 992px
- All tables wrapped in `.table-responsive-mobile`
- Touch targets: minimum 44px (enforced in CSS)
- Input font: 16px minimum on mobile (prevents iOS zoom)
- KPI cards: horizontal scroll strip on mobile (`.kpi-scroll-strip`)

### Sidebar Navigation
Navigation is defined in `layout/default-layout/_nav.ts`. Structure:
```
Dashboard
─── Trading ───
Posizioni | Segnali | Mercati | News Feed | Paper Trading | Trade Journal
─── Analisi ───
Backtest | Strategia | Modelli AI
─── Sistema ───
Impostazioni | System Logs
```

Rules:
- Active item has green left border (`.nav-link.active::before`)
- Icons use CoreUI icon set (`cil-*`)
- Group titles are uppercase separators (`title: true`)
- Do NOT add new nav items without explicit request

---

## TradingView Chart Integration

The TradingView chart lives in `shared/components/tv-chart/tv-chart.component.ts` and uses the `lightweight-charts` library (v5.1+).

### DO NOT
- Replace the charting library
- Modify the chart's data pipeline or WebSocket connection
- Change how candles are rendered
- Remove or refactor the component

### YOU CAN
- Style the chart container (padding, border, border-radius)
- Add/modify controls OUTSIDE the chart container (timeframe selector, fullscreen button)
- Style the parent card that wraps the chart
- Adjust container height/width via CSS

### Chart Container Pattern
```html
<c-card class="border-top border-top-3 border-top-primary">
  <c-card-header class="d-flex align-items-center justify-content-between py-2">
    <span class="fw-semibold small text-body-secondary">
      <app-epic-logo [epic]="selectedEpic" [size]="20"></app-epic-logo>
      {{ selectedEpic }}
    </span>
    <!-- Timeframe buttons, fullscreen toggle etc. -->
  </c-card-header>
  <c-card-body class="p-0"> <!-- p-0 so chart fills the card -->
    <app-tv-chart [epic]="selectedEpic" [height]="400"></app-tv-chart>
  </c-card-body>
</c-card>
```

---

## Animations & Transitions

### Allowed Animations
| Animation            | Duration | Usage                           |
|----------------------|----------|---------------------------------|
| `pulse-glow`         | 2s       | Live indicator dots             |
| `badge-pop`          | 0.3s     | New signal/notification badge   |
| `local-risk-pulse`   | 3s       | Warning risk badge              |
| `glow-pulse`         | 3s       | Auth page hero title            |
| `gradient-shift`     | 15s      | Auth page background            |
| `float-blob`         | 20-30s   | Auth page decorative blobs      |

### Rules
- All animations respect `prefers-reduced-motion: reduce` (already handled in CSS)
- No animations on data tables or content that updates frequently
- Transitions on interactive elements: `150ms ease` for hover, `250ms ease` for state changes
- NEVER add loading spinners that block the entire page — use skeleton loaders or inline spinners

---

## Accessibility

- All interactive elements must be keyboard-navigable
- Color is NEVER the only indicator — always pair with icon/text (e.g., ▲/▼ with green/red)
- Minimum contrast ratio: 4.5:1 for body text on `$mantis-surface-2`
- All images/icons in meaningful context need `aria-label` or `alt`
- Tables need `<thead>` and proper `<th>` scope

---

## Icons

The project uses **CoreUI Icons** (`@coreui/icons`). Icon reference:

### Navigation Icons (already defined in _nav.ts)
```
cil-speedometer     → Dashboard
cil-layers          → Posizioni
cil-bolt            → Segnali
cil-chart-line      → Mercati
cil-newspaper       → News Feed
cil-media-play      → Paper Trading
cil-book            → Trade Journal
cil-history         → Backtest
cil-settings        → Strategia
cil-puzzle          → Modelli AI
cil-applications-settings → Impostazioni
cil-clipboard       → System Logs
```

### Usage Pattern
```html
<svg cIcon [name]="'cil-chart-line'" size="sm"></svg>
```

### Rules
- Always use CoreUI icons — do NOT add FontAwesome, Heroicons, or other icon libs
- Size: `size="sm"` in cards/tables, `size="lg"` in empty states
- Color inherits from parent — use text color utilities

---

## Page-Specific Design Guidelines

### Dashboard (`views/dashboard/`)
The main page. Must show at-a-glance trading status:

1. **KPI Row** (top): Account balance, Daily P&L, Open positions count, Win rate
2. **Chart Section**: TradingView chart with asset selector
3. **Positions Summary**: Mini table of open positions with live P&L
4. **Recent Signals**: Last 5 signals with status badges
5. **Market Status**: Market open/closed indicator with next open time
6. **Performance Section**: Win Rate, Profit Factor, Total P&L, Best/Worst Trade KPIs + P&L per Asset bars

### Positions (`views/positions/`)
- Tab-based view: "Aperte" (open) + "Storico" (history)
- **Open tab**: Asset, Direction, Size, Entry, Live Price, P&L, SL/TP, Duration, Actions
- **History tab**: Filter bar (asset, close_reason, date range), KPI summary, paginated table
- Close reason badges: SL (red), TP (green), MANUAL (cyan), EXTERNAL (amber)
- Row highlight: green tint for profit, red tint for loss
- Action buttons: Close (danger), Modify SL/TP

### Signals (`views/signals/`)
- Card-based or table layout of ML signals
- Show: Asset, Direction, Confidence %, Strategy, Timestamp, Status
- Filter bar: by status, asset, direction, date range

### Markets (`views/markets/`)
- Grid of asset cards with live prices
- Each card: Asset icon, price, 24h change, mini sparkline
- Click → navigates to chart view

### Backtest (`views/backtest/`)
- Configuration form (left) + results (right) on desktop
- Form: asset selector, date range, strategy, parameters
- Results: equity curve chart, trade log table, performance metrics

---

## MCP GitHub Operations

Claude Code has access to the GitHub MCP server. Use it for all git operations:

### Branch Operations
```
# Create the UI migration branch
mcp__github__create_branch(owner="GitBakko", repo="AlgoTrader", branch="ui/mantis-template-integration", from_branch="master")

# Create feature branches off the UI branch
mcp__github__create_branch(owner="GitBakko", repo="AlgoTrader", branch="ui/redesign-dashboard", from_branch="ui/mantis-template-integration")
```

### Commit & Push
```
# After local changes, commit and push
git add -A
git commit -m "ui: redesign dashboard KPI cards with Mantis design system"
git push origin ui/mantis-template-integration
```

### Pull Request
```
mcp__github__create_pull_request(
  owner="GitBakko",
  repo="AlgoTrader",
  title="UI: Mantis template integration - Phase 1 (Layout Shell)",
  body="## Changes\n- Migrated sidebar to Mantis design\n- Updated header with glassmorphism\n- Applied new color palette\n\n## Screenshots\n...",
  head="ui/mantis-template-integration",
  base="master"
)
```

### Reading Reference Files
When you need to reference the Mantis template from CodedThemes:
```
# Clone reference template into a temp directory
mcp__github__get_file_contents(owner="codedthemes", repo="mantis-free-angular-admin-template", path="src/")
```

### Rules for MCP Operations
- ALWAYS work on `ui/mantis-template-integration` branch for UI changes
- NEVER push directly to `master`
- Commit messages MUST use `ui:` prefix for UI changes
- Create PRs for review before merging to master
- Use `mcp__github__get_file_contents` to read reference template files when needed

---

## UI Migration Plan (CoreUI → Mantis-Enhanced)

> **Strategy**: We keep CoreUI as the base framework but adopt Mantis template's design patterns, component styles, and layout improvements. This is NOT a full framework migration — it's a design uplift.

### Phase 1: Layout Shell ✦ Priority: HIGH
**Goal**: Modernize the outer frame (sidebar, header, footer)

Tasks:
1. Update sidebar styling: add glassmorphism, improve active state
2. Redesign header: add account balance widget, notifications bell, market status
3. Update footer: minimal, with version and connection status
4. Improve sidebar brand area with animated logo

Files to modify:
- `layout/default-layout/default-layout.component.html`
- `layout/default-layout/default-header/default-header.component.*`
- `layout/default-layout/default-footer/default-footer.component.*`
- `scss/_custom.scss` (sidebar/header sections)

### Phase 2: Dashboard Redesign ✦ Priority: HIGH
**Goal**: Transform dashboard into a professional trading terminal

Tasks:
1. Redesign KPI cards row with proper Mantis design tokens
2. Improve chart section container and controls
3. Add positions summary widget
4. Add recent signals widget
5. Add market status overview

Files to modify:
- `views/dashboard/dashboard.component.*`
- `scss/_custom.scss` (add dashboard-specific styles)

### Phase 3: Trading Views ✦ Priority: MEDIUM
**Goal**: Polish positions, signals, and markets pages

Tasks:
1. Redesign positions table with live P&L styling
2. Improve signals page with filter bar and status badges
3. Create asset card grid for markets page
4. Style paper trading controls

### Phase 4: Analysis & System Views ✦ Priority: LOW
**Goal**: Complete remaining pages

Tasks:
1. Backtest page: form + results layout
2. Strategy configuration page
3. AI models overview page
4. Settings page
5. System logs viewer

### Phase 5: Polish & Mobile ✦ Priority: MEDIUM
**Goal**: Responsive behavior and animations

Tasks:
1. Mobile bottom navigation refinement
2. Scroll strips for KPIs on mobile
3. Touch-friendly table interactions
4. Loading skeletons
5. Smooth page transitions

### Migration Rules
- ONE phase at a time, ONE task at a time
- Each phase ends with a commit and build verification
- Reference the Mantis template (CodedThemes) for design inspiration
- Use screenshots/mockups for complex layouts — ask the user if unsure
- KEEP all existing data bindings and service integrations
- ONLY change HTML structure, CSS classes, and display logic

---

## Anti-Patterns — NEVER Do These

### CSS Anti-Patterns
```
❌ !important (unless overriding CoreUI defaults that can't be changed otherwise)
❌ Inline styles in HTML templates
❌ Hardcoded colors (use variables)
❌ Fixed pixel heights on content containers (breaks responsiveness)
❌ z-index above 1050 (CoreUI modals use 1050)
❌ Global element selectors (div, span, p) — always scope to component or class
```

### Angular Anti-Patterns
```
❌ Using ViewChild to manipulate DOM directly for styling
❌ Adding new dependencies/libraries without explicit approval
❌ Using setTimeout for visual timing (use CSS transitions)
❌ Subscribing to observables without unsubscribing (use takeUntilDestroyed or signals)
❌ Creating components with inline templates for complex layouts
```

### Design Anti-Patterns
```
❌ More than 3 accent colors on one page
❌ Neon green (#39FF14) for large areas (only for accents/highlights)
❌ White background in dark mode (use CSS variables, light theme handles white surfaces via _light-theme.scss)
❌ Inconsistent border-radius (use 4px, 8px, or 12px only)
❌ Shadows on dark backgrounds (use border or elevation instead)
❌ Animating table rows or data that updates frequently
```

---

## Debugging Checklist

When something looks wrong in the UI:

1. **Build error?** → Run `npx ng build --configuration=development` and fix TypeScript/template errors first
2. **Styles not applying?** → Check component encapsulation: use `::ng-deep` cautiously, prefer global styles in `_custom.scss`
3. **Layout broken on mobile?** → Check Bootstrap breakpoints, ensure `.table-responsive-mobile` wrapper on tables
4. **Colors wrong?** → Verify `[data-coreui-theme="dark"]` is active on `<html>` tag
5. **Fonts wrong?** → Ensure Google Fonts are loaded in `index.html`, check `.mantis-mono`/`.mantis-kpi` classes
6. **CoreUI component not styled?** → Override via CSS custom properties (`--cui-*`) in `_custom.scss`

---

## Quick Reference: File Locations

| What                    | Where                                                |
|-------------------------|------------------------------------------------------|
| Color palette           | `frontend/src/scss/_palette.scss`                    |
| Global custom styles    | `frontend/src/scss/_custom.scss`                     |
| Light theme             | `frontend/src/scss/_light-theme.scss`                |
| Theme overrides         | `frontend/src/scss/_theme.scss`                      |
| Chart styles            | `frontend/src/scss/_charts.scss`                     |
| Main style entry        | `frontend/src/scss/styles.scss`                      |
| Navigation items        | `frontend/src/app/layout/default-layout/_nav.ts`     |
| Layout components       | `frontend/src/app/layout/default-layout/`            |
| Shared components       | `frontend/src/app/shared/components/`                |
| Page views              | `frontend/src/app/views/`                            |
| App routes              | `frontend/src/app/app.routes.ts`                     |
| Services                | `frontend/src/app/core/services/`                    |
| Guards/Interceptors     | `frontend/src/app/core/guards/`, `interceptors/`     |
| TradingView chart       | `frontend/src/app/shared/components/tv-chart/`       |
| Package.json            | `frontend/package.json`                              |
