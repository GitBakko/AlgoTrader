import { Component, ChangeDetectionStrategy, inject, OnInit, OnDestroy, computed, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective, BadgeComponent,
  ButtonGroupComponent, ButtonDirective,
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { MarketStatusService, MarketStatusResponse } from '../../core/services/market-status.service';
import { NewsService } from '../../core/services/news.service';
import { TvChartComponent, OhlcDataPoint } from '../../shared/components/tv-chart/tv-chart.component';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';
import { NewsWidgetComponent } from '../../shared/components/news-widget/news-widget.component';

const EPICS = [
  // Existing 8 assets (EURUSD excluded)
  'XAUUSD', 'BTCUSD', 'US500', 'WTIUSD', 'NVDA', 'TSLA', 'XAGUSD', 'DE40',
  // New 12 assets - Phase 12: Portfolio Expansion
  'SOLUSD', 'ETHUSD', 'BNBUSD', 'DOGUSD', 'DASHUSD', 'ICPUSD',
  'NATGAS', 'COPPER', 'PLATINUM',
  'GBPUSD', 'USDJPY',
  'NAS100',
] as const;
const TIMEFRAMES = [
  { value: 'HOUR', label: '1H' },
  { value: 'HOUR_4', label: '4H' },
  { value: 'DAY', label: '1D' },
] as const;

@Component({
  selector: 'app-markets',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective, BadgeComponent,
    ButtonGroupComponent, ButtonDirective,
    TvChartComponent, PriceFormatPipe, EpicLogoComponent, NewsWidgetComponent,
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <div class="d-flex align-items-center gap-2">
        <h5 class="mb-0 fw-semibold">Mercati</h5>
        @if (wsConnected()) {
          <c-badge color="success" class="badge-sm">WS Live</c-badge>
        } @else {
          <c-badge color="danger" class="badge-sm">WS Offline</c-badge>
        }
      </div>
      <span class="text-body-secondary small">{{ livePrices().length }} asset live</span>
    </div>

    <!-- Asset Cards Grid -->
    <c-row class="mb-4">
      @for (p of livePrices(); track p.epic) {
        <c-col xs="6" md="4" lg="3" class="mb-3">
          <c-card class="h-100 asset-card"
                  [class.border-start-3]="selectedEpic() === p.epic"
                  [class.border-start-success]="selectedEpic() === p.epic"
                  style="cursor: pointer;"
                  (click)="selectAsset(p.epic)">
            <c-card-body class="py-2">
              <div class="d-flex justify-content-between align-items-start">
                <div class="d-flex align-items-center gap-2">
                  <app-epic-logo [epic]="p.epic" [size]="32" [rounded]="true" />
                  <div>
                    <div class="fw-semibold">{{ p.epic }}</div>
                    <div class="text-body-secondary small">Spread: {{ p.spread | priceFormat:p.epic }}</div>
                  </div>
                </div>
                <div class="text-end">
                  <div class="font-monospace fw-bold" style="font-size: 1.05rem;">
                    {{ p.mid | priceFormat:p.epic }}
                  </div>
                  <div class="text-body-secondary small font-monospace">
                    {{ p.bid | priceFormat:p.epic }} / {{ p.offer | priceFormat:p.epic }}
                  </div>
                </div>
              </div>
            </c-card-body>
          </c-card>
        </c-col>
      }
    </c-row>

    <!-- Candlestick Chart -->
    @if (selectedEpic()) {
      <c-card class="mb-4">
        <c-card-header class="d-flex align-items-center justify-content-between py-2">
          <strong>{{ selectedEpic() }} - Grafico</strong>
          <c-button-group size="sm">
            @for (tf of timeframes; track tf.value) {
              <button cButton [color]="selectedTimeframe() === tf.value ? 'primary' : 'secondary'"
                      variant="outline" (click)="selectTimeframe(tf.value)">
                {{ tf.label }}
              </button>
            }
          </c-button-group>
        </c-card-header>
        <c-card-body class="p-0">
          @if (chartData().length > 0) {
            <app-tv-chart
              mode="candlestick"
              [ohlcData]="chartData()"
              [showVolume]="true"
              [height]="420"
            ></app-tv-chart>
          } @else if (chartLoading()) {
            <div class="text-center py-5 text-body-secondary">
              <div class="spinner-border spinner-border-sm me-2" role="status"></div>
              Caricamento dati {{ selectedEpic() }} {{ selectedTimeframe() }}...
            </div>
          } @else {
            <div class="text-center py-5 text-body-secondary small">
              Nessun dato disponibile. Connetti il backend per caricare i prezzi storici.
            </div>
          }
        </c-card-body>
      </c-card>

      <!-- News Widget for Selected Asset -->
      <c-card class="mb-4">
        <c-card-header class="py-2"><strong>Notizie {{ selectedEpic() }}</strong></c-card-header>
        <c-card-body class="p-3">
          <app-news-widget [news]="assetNews()" [maxItems]="5"></app-news-widget>
        </c-card-body>
      </c-card>
    }

    <!-- Markets Table (from API) -->
    @if (markets().length > 0) {
      <c-card class="mb-4">
        <c-card-header class="py-2"><strong>Dettagli Mercati</strong></c-card-header>
        <c-card-body class="p-0">
          <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
            <thead>
              <tr>
                <th>Epic</th>
                <th>Nome</th>
                <th class="text-end">Bid</th>
                <th class="text-end">Offer</th>
                <th class="text-end">High</th>
                <th class="text-end">Low</th>
                <th class="text-end">Change %</th>
              </tr>
            </thead>
            <tbody>
              @for (m of markets(); track m.epic) {
                <tr style="cursor: pointer;" (click)="selectAsset(m.epic)">
                  <td class="fw-semibold">{{ m.epic }}</td>
                  <td>{{ m.name }}</td>
                  <td class="text-end font-monospace">{{ m.bid != null ? (m.bid | priceFormat:m.epic) : '\u2014' }}</td>
                  <td class="text-end font-monospace">{{ m.offer != null ? (m.offer | priceFormat:m.epic) : '\u2014' }}</td>
                  <td class="text-end font-monospace">{{ m.high != null ? (m.high | priceFormat:m.epic) : '\u2014' }}</td>
                  <td class="text-end font-monospace">{{ m.low != null ? (m.low | priceFormat:m.epic) : '\u2014' }}</td>
                  <td class="text-end font-monospace"
                      [class.text-success]="m.change_pct != null && m.change_pct >= 0"
                      [class.text-danger]="m.change_pct != null && m.change_pct < 0">
                    {{ m.change_pct != null ? ((m.change_pct >= 0 ? '+' : '') + (m.change_pct | number:'1.2-2') + '%') : '\u2014' }}
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </c-card-body>
      </c-card>
    }
  `
})
export class MarketsComponent implements OnInit, OnDestroy {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  private readonly marketStatus = inject(MarketStatusService);
  private readonly newsService = inject(NewsService);
  readonly markets = this.trading.markets;
  readonly wsConnected = this.ws.connected;
  readonly timeframes = TIMEFRAMES;

  readonly selectedEpic = signal<string>('');
  readonly selectedTimeframe = signal<string>('HOUR');
  readonly assetNews = this.newsService.news;

  constructor() {
    // Fetch news when asset selected
    effect(() => {
      const epic = this.selectedEpic();
      if (epic) {
        this.newsService.getNews(epic, 5, 7);
      }
    });
  }
  readonly chartLoading = signal(false);
  readonly rawCandles = signal<{ timestamp: string; open: number; high: number; low: number; close: number; volume: number }[]>([]);
  readonly currentMarketStatus = signal<MarketStatusResponse | null>(null);

  // Smart polling interval (60s open, 5min closed)
  readonly pollingInterval = computed(() => {
    const status = this.currentMarketStatus();
    if (!status) return 60000; // 60s default
    if (!status.is_open) return 300000; // 5min if closed
    return 60000; // 60s if open (markets data doesn't change as fast)
  });

  readonly chartData = computed<OhlcDataPoint[]>(() => {
    return this.rawCandles().map(c => ({
      time: c.timestamp.substring(0, 10) === c.timestamp
        ? c.timestamp
        : Math.floor(new Date(c.timestamp).getTime() / 1000),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
    }));
  });

  readonly livePrices = computed(() => {
    const prices = this.ws.prices();
    return EPICS
      .filter(e => prices[e])
      .map(e => {
        const t = prices[e];
        return { epic: e, bid: t.bid, offer: t.offer, mid: (t.bid + t.offer) / 2, spread: t.offer - t.bid };
      });
  });

  private pollTimer: ReturnType<typeof setTimeout> | null = null;

  ngOnInit(): void {
    this.startSmartPolling();
    this.ws.connectPrices();
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private async startSmartPolling(): Promise<void> {
    // Use XAUUSD as representative asset for market hours detection
    const epic = 'XAUUSD';

    // Initial fetch
    try {
      const status = await this.marketStatus.getMarketStatus(epic);
      this.currentMarketStatus.set(status);
      this.trading.loadMarkets();
    } catch (error) {
      console.error('Failed to fetch market status:', error);
      this.trading.loadMarkets();
    }

    // Recursive polling with dynamic interval
    const poll = async () => {
      try {
        const status = await this.marketStatus.getMarketStatus(epic);
        this.currentMarketStatus.set(status);

        // Only load data if market is open
        if (status.is_open) {
          this.trading.loadMarkets();
        }
      } catch (error) {
        console.error('Polling error:', error);
      }

      this.pollTimer = setTimeout(() => poll(), this.pollingInterval());
    };

    this.pollTimer = setTimeout(() => poll(), this.pollingInterval());
  }

  selectAsset(epic: string): void {
    this.selectedEpic.set(epic);
    this.loadChart();
  }

  selectTimeframe(tf: string): void {
    this.selectedTimeframe.set(tf);
    this.loadChart();
  }

  private loadChart(): void {
    const epic = this.selectedEpic();
    const tf = this.selectedTimeframe();
    if (!epic) return;

    this.chartLoading.set(true);
    this.rawCandles.set([]);

    this.trading.getMarketPrices(epic, tf, 300).subscribe({
      next: candles => {
        this.rawCandles.set(candles);
        this.chartLoading.set(false);
      },
      error: () => {
        this.chartLoading.set(false);
      }
    });
  }
}
