import { Component, ChangeDetectionStrategy, computed, inject, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent,
  TableDirective, AlertComponent, TooltipDirective,
  PlaceholderDirective, PlaceholderAnimationDirective,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { TvChartComponent, LineDataPoint } from '../../shared/components/tv-chart/tv-chart.component';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { MarketStatusService, MarketStatusResponse } from '../../core/services/market-status.service';
import { NewsService } from '../../core/services/news.service';
import { NotificationCenterService } from '../../core/services/notification-center.service';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';
import { NewsWidgetComponent } from '../../shared/components/news-widget/news-widget.component';
import { SkeletonCardComponent } from '../../shared/components/skeleton-card/skeleton-card.component';
import { SkeletonTableComponent } from '../../shared/components/skeleton-table/skeleton-table.component';

@Component({
  templateUrl: 'dashboard.component.html',
  styleUrl: 'dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, RouterLink,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent,
    TableDirective, AlertComponent, TooltipDirective,
    PlaceholderDirective, PlaceholderAnimationDirective,
    TvChartComponent, IconDirective,
    PriceFormatPipe, EpicLogoComponent, NewsWidgetComponent,
    SkeletonCardComponent, SkeletonTableComponent,
  ]
})
export class DashboardComponent implements OnInit, OnDestroy {
  readonly trading = inject(TradingService);
  readonly ws = inject(WebSocketService);
  readonly marketStatus = inject(MarketStatusService);
  readonly newsService = inject(NewsService);
  private readonly notifCenter = inject(NotificationCenterService);

  /** Recent unread alerts for dashboard widget (max 5) */
  readonly recentAlerts = computed(() =>
    this.notifCenter.notifications()
      .filter(n => !n.is_read)
      .slice(0, 5)
  );
  readonly alertCount = this.notifCenter.unreadCount;

  readonly Math = Math; // expose for template
  readonly overview = this.trading.overview;
  readonly riskStatus = this.trading.riskStatus;
  readonly paperStatus = this.trading.paperStatus;

  /** Circuit breaker type → Italian label + icon */
  readonly cbTypeMap: Record<string, { label: string; icon: string }> = {
    'daily_loss':         { label: 'Perdita Giornaliera',  icon: 'cilArrowBottom' },
    'consecutive_losses': { label: 'Perdite Consecutive',  icon: 'cilChartLine' },
    'max_positions':      { label: 'Max Posizioni',        icon: 'cilLayers' },
    'slippage_anomaly':   { label: 'Anomalia Slippage',    icon: 'cilBolt' },
    'heartbeat_timeout':  { label: 'Timeout Heartbeat',    icon: 'cilReload' },
    'volatility_spike':   { label: 'Spike Volatilita',     icon: 'cilChartPie' },
  };

  /** Parsed circuit breakers with Italian labels and icons */
  readonly circuitBreakersTripped = computed(() => {
    const raw = this.paperStatus()?.circuit_breakers_tripped;
    if (!raw || Array.isArray(raw)) return [];
    return Object.entries(raw).map(([key, reason]) => ({
      key,
      label: this.cbTypeMap[key]?.label ?? key,
      icon: this.cbTypeMap[key]?.icon ?? 'cilShieldAlt',
      reason: String(reason),
    }));
  });

  /** True until the first overview data arrives. */
  readonly loading = computed(() => this.overview() === null);

  // Market headlines (US500 news)
  readonly marketNews = this.newsService.news;

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

  private pollTimer: ReturnType<typeof setTimeout> | null = null;
  private newsTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.startSmartPolling();
    this.ws.connectPrices();

    // Fetch market headlines (US500 news) - refresh every 5 minutes
    this.newsService.getNews('US500', 5, 7);
    this.newsTimer = setInterval(() => this.newsService.getNews('US500', 5, 7), 5 * 60 * 1000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.newsTimer) {
      clearInterval(this.newsTimer);
      this.newsTimer = null;
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

  // Performance data
  readonly performance = this.trading.performance;

  // P&L by asset sorted by absolute value (for bar chart display)
  readonly pnlByAsset = computed(() => {
    const perf = this.performance();
    if (!perf?.pnl_by_epic) return [];
    return Object.entries(perf.pnl_by_epic)
      .map(([epic, pnl]) => ({ epic, pnl }))
      .sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl))
      .slice(0, 10);
  });

  // Max absolute P&L for bar width calculation
  readonly maxAbsPnl = computed(() => {
    const items = this.pnlByAsset();
    if (items.length === 0) return 1;
    return Math.max(...items.map(i => Math.abs(i.pnl)));
  });

  private loadAll(): void {
    this.trading.loadOverview();
    this.trading.loadEquityCurve();
    this.trading.loadPositions();
    this.trading.loadRiskStatus();
    this.trading.loadPaperStatus();
    this.trading.loadPaperPositions();
    this.trading.loadPaperSignals();
    this.trading.loadPerformance(30);
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
