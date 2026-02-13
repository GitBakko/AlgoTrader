import { Component, ChangeDetectionStrategy, computed, inject, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent,
  TableDirective,
} from '@coreui/angular';
import { TvChartComponent, LineDataPoint } from '../../shared/components/tv-chart/tv-chart.component';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';

@Component({
  templateUrl: 'dashboard.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, RouterLink,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent,
    TableDirective,
    TvChartComponent,
  ]
})
export class DashboardComponent implements OnInit, OnDestroy {
  readonly trading = inject(TradingService);
  readonly ws = inject(WebSocketService);

  readonly overview = this.trading.overview;
  readonly riskStatus = this.trading.riskStatus;
  readonly paperStatus = this.trading.paperStatus;

  // Equity curve for TvChart
  readonly equityLineData = computed<LineDataPoint[]>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return [];
    return curve.map(p => ({
      time: p.date?.substring(0, 10) || '',
      value: p.equity,
    }));
  });

  // Live positions (from paper trading)
  readonly livePositions = computed(() => {
    const positions = this.trading.paperPositions();
    const prices = this.ws.prices();
    return positions.slice(0, 6).map(pos => {
      const tick = prices[pos.epic];
      if (!tick) return { ...pos, live_pnl: 0 };
      const currentPrice = pos.direction === 'BUY' ? tick.bid : tick.offer;
      const diff = pos.direction === 'BUY'
        ? currentPrice - pos.level
        : pos.level - currentPrice;
      return { ...pos, live_pnl: Math.round(diff * pos.size * 100) / 100 };
    });
  });

  // Recent signals (last 8)
  readonly recentSignals = computed(() => {
    return this.trading.paperSignals().slice(0, 8);
  });

  // Asset price tickers from WebSocket
  readonly priceTickers = computed(() => {
    const prices = this.ws.prices();
    const epics = ['XAUUSD', 'BTCUSD', 'US500', 'WTIUSD', 'NVDA', 'TSLA', 'XAGUSD', 'DE40'];
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

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.loadAll();
    this.ws.connectPrices();
    this.pollTimer = setInterval(() => this.loadAll(), 30_000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
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
}
