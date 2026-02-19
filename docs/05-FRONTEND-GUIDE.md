# MANTIS AI - Frontend Development Guide

## Tech Stack

- **Framework**: Angular 21 (standalone components, Signals, OnPush)
- **UI Kit**: CoreUI Free Angular Admin Template v5.6+
- **CSS Framework**: Bootstrap 5 (via CoreUI)
- **Charts**: Chart.js (via @coreui/angular-chartjs)
- **Icons**: @coreui/icons-angular
- **Theme**: Dark mode default — Brand green `#39FF14`, muted green `#00d97e`, dark `#0d1117`
- **Fonts**: Plus Jakarta Sans (display), IBM Plex Mono (code)

## Setup

```bash
cd frontend
npm install

# Development server (port 4321)
npx ng serve

# Production build
npx ng build --configuration=production
```

## Project Structure

```text
frontend/src/app/
├── core/                          # Singleton services
│   ├── guards/
│   │   └── auth.guard.ts          # Route protection (redirect to login)
│   ├── interceptors/
│   │   └── auth.interceptor.ts    # JWT token injection on HTTP requests
│   ├── services/
│   │   ├── api.service.ts         # HTTP client with ApiResponse<T> envelope
│   │   ├── auth.service.ts        # Login, register, JWT, avatar, currentUser signal
│   │   ├── trading.service.ts     # Trading state (positions, signals, paper status, closed history, performance)
│   │   └── websocket.service.ts   # WebSocket with exponential backoff reconnection
│   └── models/
│       ├── index.ts               # TypeScript interfaces (Position, Signal, etc.)
│       └── auth.models.ts         # User, Role, Permission, LoginRequest, etc.
│
├── shared/                        # Shared utilities
│   ├── components/
│   │   ├── avatar/                # Avatar display (initials fallback)
│   │   └── avatar-upload/         # Drag-drop avatar upload (5MB, 256x256)
│   ├── pipes/
│   │   └── price-format.pipe.ts   # Asset-specific decimal formatting
│   └── services/
│       └── notification.service.ts # Browser notifications for trades
│
├── views/                         # Pages (lazy loaded routes)
│   ├── dashboard/                 # Main overview (KPIs, live prices, positions)
│   ├── positions/                 # Open positions with live P&L
│   ├── signals/                   # ML signal history
│   ├── markets/                   # Market overview per asset
│   ├── paper-trading/             # Paper trading control + live monitor
│   ├── trade-journal/             # Signal history with filters & stats
│   ├── backtest/                  # Walk-forward backtest runner + results
│   ├── strategy/                  # Strategy configuration
│   ├── models/                    # ML model monitoring
│   └── settings/                  # App settings
│
├── layout/
│   └── default-layout/            # CoreUI sidebar + header
│       └── _nav.ts                # Sidebar navigation items
│
├── app.component.ts               # Root component (WS connect, notifications)
├── app.config.ts                  # App configuration
└── app.routes.ts                  # Route definitions (lazy loading)
```

## Key Patterns

### Standalone Components + OnPush

Every component is standalone with `changeDetection: ChangeDetectionStrategy.OnPush`:

```typescript
@Component({
  selector: 'app-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, CardModule, ...],
  template: `...`,
})
export class DashboardComponent { }
```

### Angular Signals for State

All reactive state uses Angular Signals (not RxJS Subjects):

```typescript
// In TradingService
readonly positions = signal<Position[]>([]);
readonly paperStatus = signal<PaperStatus | null>(null);

// Computed signals
readonly openCount = computed(() => this.positions().length);
```

### API Envelope Pattern

All backend responses follow `{ success: boolean, data: T }`. The `ApiService` unwraps automatically:

```typescript
// api.service.ts
get<T>(path: string): Observable<T> {
  return this.http.get<ApiResponse<T>>(`${this.baseUrl}${path}`)
    .pipe(map(res => res.data));
}
```

### WebSocket Service

Real-time prices via WebSocket with automatic reconnection:

```typescript
// websocket.service.ts
readonly prices = signal<Record<string, PriceTick>>({});
readonly lastTrade = signal<TradeEvent | null>(null);
readonly connected = signal(false);
```

Prices update on every tick from the backend WebSocket at `ws://localhost:8000/ws/stream`.

### Price Formatting

The `PriceFormatPipe` provides asset-specific decimal places:

| Asset                        | Decimals | Example  |
| ---------------------------- | -------- | -------- |
| BTCUSD                       | 0        | 91,235   |
| US500, DE40                  | 1        | 6,012.3  |
| XAUUSD, WTIUSD, NVDA, TSLA  | 2        | 2,934.56 |
| XAGUSD                       | 3        | 32.456   |
| EURUSD                       | 5        | 1.07234  |

Usage: `{{ price | priceFormat:epic }}`

### Browser Notifications

`NotificationService` watches Angular signals and fires native browser notifications:

- **Trade executed**: shows epic, direction, size, entry price
- **Circuit breaker activated**: warning notification with reason

## MANTIS AI Theme

CoreUI dark mode is set by default. Custom MANTIS theme in `_custom.scss`:

```scss
// Brand colors
$mantis-neon:    #39FF14;   // Primary brand (neon green)
$mantis-muted:   #00d97e;   // Muted green (accents)
$mantis-dark:    #0d1117;   // Background
$mantis-surface: #161b22;   // Cards, surfaces

// Fonts: Plus Jakarta Sans (display) + IBM Plex Mono (code)

// P&L flash animations
.pnl-flash-positive { animation: flash-green 0.6s ease-out; }
.pnl-flash-negative { animation: flash-red 0.6s ease-out; }
```

### Auth Pages (Glassmorphism Design)

Login and register pages use a split-screen layout:
- **Left**: Hero section with animated SVG mantis logo, floating gradient blobs
- **Right**: Glassmorphism form (`backdrop-filter: blur(20px)`)
- **Animations**: `gradient-shift` (15s), `float-blob` (20-30s), `glow-pulse` (2s)
- **Registration**: Password strength meter (weak/medium/strong) with animated bars

### Avatar System

- `AvatarComponent` — Displays user avatar with initials fallback (computed from username)
- `AvatarUploadComponent` — Drag-and-drop upload zone with file validation
  - Accepts: JPG, PNG, GIF, WEBP (max 5MB)
  - Backend resizes to 256x256 via Pillow
  - Integrated in user dropdown and profile page

## Pages Overview

| Page          | Route            | Description                                         |
| ------------- | ---------------- | --------------------------------------------------- |
| Dashboard     | `/dashboard`     | Equity curve, 8-asset grid, risk metric cards       |
| Posizioni     | `/positions`     | Open + closed positions (tabs), live P&L, history   |
| Segnali       | `/signals`       | ML signal feed with confidence scores               |
| Mercati       | `/markets`       | Market overview per asset (21 assets)               |
| Paper Trading | `/paper-trading` | Start/stop trading, live signals & positions        |
| Trade Journal | `/trade-journal` | Full signal history with filters, sorting, stats    |
| Backtest      | `/backtest`      | Run walk-forward backtests, view equity curves      |
| Strategia     | `/strategy`      | Strategy and risk configuration                     |
| Modelli AI    | `/models`        | ML model performance monitoring                     |
| Impostazioni  | `/settings`      | App settings, API configuration                     |
| Login         | `/login`         | Glassmorphism auth with animated mantis logo        |
| Registrazione | `/register`      | Registration with password strength meter           |
| Profilo       | `/profile`       | User profile, avatar upload, permissions            |

## Docker

The frontend has a multi-stage Dockerfile:

1. **Build stage**: `node:22-alpine` runs `ng build --configuration=production`
2. **Serve stage**: `nginx:alpine` serves the built files on port 4321

Nginx handles:
- SPA routing (`try_files $uri $uri/ /index.html`)
- API reverse proxy (`/api/` → `http://backend:8000/api/`)
- WebSocket proxy (`/ws/` → `http://backend:8000/ws/`)
- Gzip compression, security headers, static asset caching

## Testing

```bash
# Run tests
npx ng test --watch=false

# Test files:
# - shared/pipes/price-format.pipe.spec.ts (14 tests)
# - core/services/trading.service.spec.ts (12 tests)
# - core/services/websocket.service.spec.ts (5 tests)
# - shared/services/notification.service.spec.ts (2 tests)
```

## CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`):
1. **backend-tests**: Python 3.12 + PostgreSQL 16 + Redis 7, pytest with coverage
2. **frontend-build**: Node 22, production build verification
3. **docker-build**: Build both Docker images (depends on tests passing)
