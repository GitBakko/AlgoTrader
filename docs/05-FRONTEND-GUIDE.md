# AlgoTrader AI - Frontend Development Guide

## Tech Stack

- **Framework**: Angular 21 (standalone components, Signals)
- **UI Kit**: CoreUI Free Angular Admin Template v5.6+
- **CSS Framework**: Bootstrap 5 (via CoreUI)
- **Charts**: Chart.js (via @coreui/angular-chartjs) + TradingView Lightweight Charts (for candlesticks)
- **Icons**: @coreui/icons-angular
- **Theme**: Dark mode as default

## Setup

```bash
# Option 1: Clone CoreUI template and customize
git clone https://github.com/coreui/coreui-free-angular-admin-template.git frontend
cd frontend
npm install

# Option 2: Start fresh Angular 21 project and add CoreUI
ng new algotrader-dashboard --standalone --style=scss --routing
cd algotrader-dashboard
npm install @coreui/angular @coreui/angular-chartjs @coreui/icons-angular chart.js
npm install lightweight-charts  # TradingView charts for candlesticks
```

## Project Structure (within frontend/)

```
frontend/src/app/
├── core/                          # Singleton services, guards, interceptors
│   ├── services/
│   │   ├── api.service.ts         # HTTP client wrapper
│   │   ├── websocket.service.ts   # WebSocket connection manager
│   │   ├── auth.service.ts        # JWT auth management
│   │   └── notification.service.ts # Toast notifications
│   ├── interceptors/
│   │   ├── auth.interceptor.ts    # Attach JWT token
│   │   └── error.interceptor.ts   # Global error handling
│   ├── guards/
│   │   └── auth.guard.ts          # Route protection
│   └── models/                    # TypeScript interfaces
│       ├── position.model.ts
│       ├── signal.model.ts
│       ├── trade.model.ts
│       └── market-data.model.ts
│
├── features/                      # Feature modules (lazy loaded)
│   ├── dashboard/                 # Main overview page
│   │   ├── dashboard.component.ts
│   │   ├── widgets/
│   │   │   ├── equity-curve.component.ts
│   │   │   ├── pnl-summary.component.ts
│   │   │   ├── active-positions.component.ts
│   │   │   └── recent-trades.component.ts
│   │   └── dashboard.routes.ts
│   │
│   ├── markets/                   # Real-time charts
│   │   ├── markets.component.ts
│   │   ├── components/
│   │   │   ├── candlestick-chart.component.ts  # TradingView Lightweight
│   │   │   ├── indicator-overlay.component.ts
│   │   │   └── price-ticker.component.ts
│   │   └── markets.routes.ts
│   │
│   ├── signals/                   # ML signals view
│   │   ├── signals.component.ts
│   │   ├── components/
│   │   │   ├── signal-card.component.ts
│   │   │   ├── confidence-meter.component.ts
│   │   │   └── model-breakdown.component.ts
│   │   └── signals.routes.ts
│   │
│   ├── positions/                 # Position management
│   │   ├── positions.component.ts
│   │   ├── components/
│   │   │   ├── position-table.component.ts
│   │   │   ├── position-detail.component.ts
│   │   │   └── sl-tp-editor.component.ts
│   │   └── positions.routes.ts
│   │
│   ├── backtest/                  # Backtesting interface
│   │   ├── backtest.component.ts
│   │   ├── components/
│   │   │   ├── backtest-form.component.ts
│   │   │   ├── results-viewer.component.ts
│   │   │   ├── equity-chart.component.ts
│   │   │   └── metrics-table.component.ts
│   │   └── backtest.routes.ts
│   │
│   ├── strategy/                  # Strategy configuration
│   │   ├── strategy.component.ts
│   │   ├── components/
│   │   │   ├── strategy-list.component.ts
│   │   │   ├── risk-settings.component.ts
│   │   │   └── allocation-editor.component.ts
│   │   └── strategy.routes.ts
│   │
│   ├── models/                    # ML model monitoring
│   │   ├── models.component.ts
│   │   ├── components/
│   │   │   ├── model-performance.component.ts
│   │   │   ├── training-history.component.ts
│   │   │   └── drift-indicator.component.ts
│   │   └── models.routes.ts
│   │
│   └── settings/                  # App settings
│       ├── settings.component.ts
│       └── settings.routes.ts
│
├── shared/                        # Shared components, pipes, directives
│   ├── components/
│   │   ├── loading-spinner.component.ts
│   │   ├── asset-badge.component.ts  # Gold/BTC/SP500 colored badge
│   │   └── direction-arrow.component.ts
│   ├── pipes/
│   │   ├── currency.pipe.ts
│   │   └── pnl-color.pipe.ts
│   └── directives/
│       └── highlight-change.directive.ts  # Flash on price change
│
├── layouts/
│   └── default-layout/            # CoreUI sidebar + header layout
│
├── app.component.ts
├── app.config.ts
└── app.routes.ts
```

## Key Angular Patterns

### Standalone Components (Angular 21)

```typescript
// Every component is standalone - no NgModules
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, ChartModule, ...],
  template: `...`,
})
export class DashboardComponent {
  // Use Angular Signals for state
  equity = signal<number>(0);
  positions = signal<Position[]>([]);

  // Computed signals
  totalPnl = computed(() =>
    this.positions().reduce((sum, p) => sum + p.unrealizedPnl, 0)
  );
}
```

### WebSocket Service with Signals

```typescript
@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private ws: WebSocket | null = null;

  // Reactive price signals
  goldPrice = signal<PriceTick | null>(null);
  btcPrice = signal<PriceTick | null>(null);
  sp500Price = signal<PriceTick | null>(null);

  connect(): void {
    this.ws = new WebSocket('ws://localhost:8000/ws/prices');

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.epic) {
        case 'GOLD': this.goldPrice.set(data); break;
        case 'BITCOIN': this.btcPrice.set(data); break;
        case 'US500': this.sp500Price.set(data); break;
      }
    };
  }
}
```

### API Service

```typescript
@Injectable({ providedIn: 'root' })
export class ApiService {
  private baseUrl = environment.apiUrl; // http://localhost:8000/api

  constructor(private http: HttpClient) {}

  getDashboard(): Observable<ApiResponse<DashboardData>> {
    return this.http.get<ApiResponse<DashboardData>>(`${this.baseUrl}/dashboard`);
  }

  getPositions(): Observable<ApiResponse<Position[]>> {
    return this.http.get<ApiResponse<Position[]>>(`${this.baseUrl}/positions`);
  }

  getSignals(): Observable<ApiResponse<Signal[]>> {
    return this.http.get<ApiResponse<Signal[]>>(`${this.baseUrl}/signals`);
  }

  runBacktest(params: BacktestParams): Observable<ApiResponse<BacktestResult>> {
    return this.http.post<ApiResponse<BacktestResult>>(`${this.baseUrl}/backtest`, params);
  }
}
```

## Chart Integration

### Candlestick Chart (TradingView Lightweight Charts)

```typescript
import { createChart, IChartApi, CandlestickSeries } from 'lightweight-charts';

@Component({
  selector: 'app-candlestick-chart',
  standalone: true,
  template: `<div #chartContainer class="chart-container"></div>`,
  styles: [`.chart-container { width: 100%; height: 500px; }`],
})
export class CandlestickChartComponent implements AfterViewInit, OnDestroy {
  @ViewChild('chartContainer') container!: ElementRef;
  @Input() asset = signal<string>('GOLD');

  private chart!: IChartApi;
  private candleSeries!: CandlestickSeries;

  ngAfterViewInit() {
    this.chart = createChart(this.container.nativeElement, {
      layout: {
        background: { color: '#1e1e2d' },  // Dark theme
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#2B2B43' },
        horzLines: { color: '#2B2B43' },
      },
      timeScale: { timeVisible: true },
    });

    this.candleSeries = this.chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });
  }

  updateData(candles: OhlcData[]) {
    this.candleSeries.setData(candles);
  }

  addTick(candle: OhlcData) {
    this.candleSeries.update(candle);
  }
}
```

### P&L Chart (Chart.js via CoreUI)

```typescript
// Using CoreUI's Chart.js wrapper for simpler charts
@Component({
  selector: 'app-equity-curve',
  standalone: true,
  imports: [ChartjsModule],
  template: `<c-chart type="line" [data]="chartData()" [options]="chartOptions" />`,
})
export class EquityCurveComponent {
  equityHistory = input<EquityPoint[]>([]);

  chartData = computed(() => ({
    labels: this.equityHistory().map(p => p.date),
    datasets: [{
      label: 'Equity',
      data: this.equityHistory().map(p => p.value),
      borderColor: '#20c997',
      backgroundColor: 'rgba(32, 201, 151, 0.1)',
      fill: true,
    }],
  }));

  chartOptions = {
    scales: {
      y: { ticks: { color: '#d1d4dc' }, grid: { color: '#2B2B43' } },
      x: { ticks: { color: '#d1d4dc' }, grid: { color: '#2B2B43' } },
    },
    plugins: { legend: { labels: { color: '#d1d4dc' } } },
  };
}
```

## Dark Theme Configuration

CoreUI supports dark mode natively. Set as default:

```typescript
// In app.component.ts or theme service
document.body.setAttribute('data-coreui-theme', 'dark');
```

Custom dark theme variables (override in styles.scss):
```scss
[data-coreui-theme="dark"] {
  --cui-body-bg: #1a1a2e;
  --cui-card-bg: #16213e;
  --cui-sidebar-bg: #0f3460;

  // Trading-specific colors
  --profit-color: #26a69a;
  --loss-color: #ef5350;
  --gold-color: #ffd700;
  --btc-color: #f7931a;
  --sp500-color: #4dabf7;
}
```

## Responsive Design

CoreUI's grid system handles responsiveness. Key breakpoints:
- **Desktop (>1200px)**: Full dashboard with sidebar
- **Tablet (768-1200px)**: Collapsible sidebar, stacked widgets
- **Mobile (<768px)**: Bottom nav, single column, mini charts

## Build & Deploy

```bash
# Development
ng serve --port 4200

# Production build
ng build --configuration production

# Output in dist/ folder, serve via nginx or similar
```
