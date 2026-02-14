import { Component, ChangeDetectionStrategy, computed, inject, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent,
  TableDirective, AlertComponent,
} from '@coreui/angular';
import { TvChartComponent, LineDataPoint } from '../../shared/components/tv-chart/tv-chart.component';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { MarketStatusService, MarketStatusResponse } from '../../core/services/market-status.service';

@Component({
  templateUrl: 'dashboard.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, RouterLink,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent,
    TableDirective, AlertComponent,
    TvChartComponent,
    PriceFormatPipe,
  ]
})
export class DashboardComponent implements OnInit, OnDestroy {
  readonly trading = inject(TradingService);
  readonly ws = inject(WebSocketService);
  readonly marketStatus = inject(MarketStatusService);

  readonly overview = this.trading.overview;
  readonly riskStatus = this.trading.riskStatus;
  readonly paperStatus = this.trading.paperStatus;

  // Current epic for market status (default: XAUUSD)
  readonly currentEpic = signal<string>('XAUUSD');
  readonly currentMarketStatus = signal<MarketStatusResponse | null>(null);

  // Equity curve for TvChart
  readonly equityLineData = computed<LineDataPoint[]>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return [];
    return curve.map(p => ({
      time: p.date?.substring(0, 10) || '',
      value: p.equity,
    }));
  });

  // All live positions with real-time P&L from WebSocket
  readonly allLivePositions = computed(() => {
    const positions = this.trading.paperPositions();
    const prices = this.ws.prices();
    return positions.map(pos => {
      const tick = prices[pos.epic];
      if (!tick) return { ...pos, live_pnl: 0 };
      const currentPrice = pos.direction === 'BUY' ? tick.bid : tick.offer;
      const diff = pos.direction === 'BUY'
        ? currentPrice - pos.level
        : pos.level - currentPrice;
      return { ...pos, live_pnl: Math.round(diff * pos.size * 100) / 100 };
    });
  });

  // First 6 for table display
  readonly livePositions = computed(() => this.allLivePositions().slice(0, 6));

  // Real-time open position count (updates with every API poll)
  readonly openPositionCount = computed(() => this.allLivePositions().length);

  // Real-time unrealized P&L (updates with every WebSocket tick)
  readonly totalUnrealizedPnl = computed(() =>
    this.allLivePositions().reduce((sum, p) => sum + p.live_pnl, 0)
  );

  // Recent signals (last 8)
  readonly recentSignals = computed(() => {
    return this.trading.paperSignals().slice(0, 8);
  });

  // Asset price tickers from WebSocket
  readonly priceTickers = computed(() => {
    const prices = this.ws.prices();
    const epics = [
      'XAUUSD', 'BTCUSD', 'US500', 'WTIUSD', 'NVDA', 'TSLA', 'XAGUSD', 'DE40',
      'SOLUSD', 'ETHUSD', 'BNBUSD', 'DOGUSD', 'DASHUSD', 'ICPUSD',
      'NATGAS', 'COPPER', 'PLATINUM', 'GBPUSD', 'USDJPY', 'NAS100'
    ];
    return epics
      .filter(e => prices[e])
      .map(e => {
        const t = prices[e];
        const mid = (t.bid + t.offer) / 2;
        const spread = t.offer - t.bid;
        return { epic: e, bid: t.bid, offer: t.offer, mid, spread };
      });
  });

  // Drawdown percentage for progress bar
  readonly drawdownPct = computed(() => {
    const rs = this.riskStatus();
    return rs ? Math.min(rs.current_drawdown_pct * 100, 100) : 0;
  });

  // Polling interval based on market status (12s open, 5min closed)
  readonly pollingInterval = computed(() => {
    const status = this.currentMarketStatus();
    if (!status) return 30000; // 30s default
    if (!status.is_open) return 300000; // 5min if closed
    if (status.status === 'TRADEABLE') return 12000; // 12s if open
    return 60000; // 1min if suspended
  });

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.startSmartPolling();
    this.ws.connectPrices();
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private async startSmartPolling(): Promise<void> {
    const epic = this.currentEpic();

    // Initial fetch of market status and data
    try {
      const status = await this.marketStatus.getMarketStatus(epic);
      this.currentMarketStatus.set(status);
      this.loadAll();
    } catch (error) {
      console.error('Failed to fetch market status:', error);
      this.loadAll();
    }

    // Recursive polling with dynamic interval
    const poll = async () => {
      try {
        const status = await this.marketStatus.getMarketStatus(epic);
        this.currentMarketStatus.set(status);

        // Only load data if market is open, otherwise keep last available data
        if (status.is_open) {
          this.loadAll();
        }
      } catch (error) {
        console.error('Polling error:', error);
      }

      // Schedule next poll with dynamic interval
      this.pollTimer = setTimeout(() => poll(), this.pollingInterval());
    };

    // Start polling
    this.pollTimer = setTimeout(() => poll(), this.pollingInterval());
  }

  private loadAll(): void {
    this.trading.loadOverview();
    this.trading.loadEquityCurve();
    this.trading.loadPositions();
    this.trading.loadRiskStatus();
    this.trading.loadPaperStatus();
    this.trading.loadPaperPositions();
    this.trading.loadPaperSignals();
  }

  directionColor(dir: string): string {
    return dir === 'BUY' ? 'success' : dir === 'SELL' ? 'danger' : 'secondary';
  }

  statusColor(status: string): string {
    switch (status) {
      case 'executed': return 'success';
      case 'rejected': case 'exec_failed': return 'danger';
      case 'hold': return 'warning';
      case 'market_closed': return 'dark';
      default: return 'secondary';
    }
  }

  formatTime(iso: string): string {
    if (!iso) return '-';
    try {
      return new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
  }

  getCountdown(timestamp: number): string {
    const diff = timestamp - Date.now();
    if (diff < 0) return 'Soon';

    const hours = Math.floor(diff / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);

    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `${days}d ${hours % 24}h`;
    }
    return `${hours}h ${minutes}m`;
  }
}
