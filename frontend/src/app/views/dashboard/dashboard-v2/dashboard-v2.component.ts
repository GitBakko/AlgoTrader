import { Component, ChangeDetectionStrategy, computed, inject, signal, OnInit, OnDestroy, effect } from '@angular/core';
import { CommonModule } from '@angular/common';

import { TradingService } from '../../../core/services/trading.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { NewsService } from '../../../core/services/news.service';
import { TimeframeService, TIMEFRAME_OPTIONS, Timeframe } from '../../../core/services/timeframe.service';
import { ConfirmDialogService } from '../../../shared/services/confirm-dialog.service';
import { ToastService } from '../../../shared/services/toast.service';

import { TvChartComponent, LineDataPoint, EquityTooltipPoint } from '../../../shared/components/tv-chart/tv-chart.component';

import { OperationalStripComponent } from './operational-strip/operational-strip.component';
import { KpiRailComponent } from './kpi-rail/kpi-rail.component';
import { DurationScatterComponent } from './cockpit-bottom/duration-scatter.component';
import { FundingRingComponent } from './cockpit-bottom/funding-ring.component';
import { CalendarHeatmapComponent } from './cockpit-bottom/calendar-heatmap.component';
import { TradeBreakdownComponent } from './trade-breakdown/trade-breakdown.component';
import { TradeBreakdownDay } from './trade-breakdown/trade-breakdown.types';

/**
 * DASHBOARD v2 — Deliverable A (Variant B "Cockpit")
 * Route: `/dashboard-v2` — affianco a `/dashboard` legacy finché non si
 * decide il cutover finale.
 *
 * TODO — BACKEND (next sprint, MANDATORIO, sprint plan §2):
 *   - /api/trading/performance/breakdown (alimenta TradeBreakdown)
 *   - /api/funding/current (alimenta FundingRing)
 *   - /api/models/current (alimenta OperationalStrip tile 6)
 *   - performance.tp_hit_rate + performance.daily_trade_count
 *   - WS /ws/prices ping/pong per latency
 */
@Component({
  selector: 'app-dashboard-v2',
  standalone: true,
  imports: [
    CommonModule,
    TvChartComponent,
    OperationalStripComponent,
    KpiRailComponent,
    DurationScatterComponent,
    FundingRingComponent,
    CalendarHeatmapComponent,
    TradeBreakdownComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-v2.component.html',
  styleUrl: './dashboard-v2.component.scss',
})
export class DashboardV2Component implements OnInit, OnDestroy {
  readonly trading = inject(TradingService);
  readonly ws = inject(WebSocketService);
  readonly timeframeSvc = inject(TimeframeService);
  private readonly news = inject(NewsService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  private readonly toast = inject(ToastService);

  readonly timeframes: readonly Timeframe[] = TIMEFRAME_OPTIONS;
  readonly activeTimeframe = this.timeframeSvc.current;

  readonly clockTick = signal<number>(Date.now());
  private clockTimer: ReturnType<typeof setInterval> | null = null;
  private pollTimer: ReturnType<typeof setTimeout> | null = null;

  readonly killSwitchBusy = signal(false);
  readonly customOpen = signal(false);
  readonly customFrom = signal<string>(this.isoDaysAgo(30));
  readonly customTo   = signal<string>(this.today());

  /**
   * Trade breakdown data source. `null` until the backend endpoint
   * from sprint plan §2.1 lands. Child renders TODO banner when null.
   */
  readonly breakdownDays = signal<TradeBreakdownDay[] | null>(null);

  readonly now = computed(() => {
    this.clockTick();
    return new Date();
  });

  readonly clockLabel = computed(() =>
    this.now().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  );

  readonly headlineEquity = computed(() => this.trading.overview()?.equity ?? null);
  readonly headlineDailyPct = computed(() => {
    const ov = this.trading.overview();
    if (!ov || ov.equity === 0) return null;
    return (ov.daily_pnl / ov.equity) * 100;
  });

  readonly equityLineData = computed<LineDataPoint[]>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return [];
    const byDay = new Map<string, number>();
    for (const p of curve) {
      const day = (p.date ?? '').slice(0, 10);
      if (day) byDay.set(day, p.equity);
    }
    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([time, value]) => ({ time, value }));
  });

  readonly drawdownLineData = computed<LineDataPoint[]>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return [];
    const byDay = new Map<string, number>();
    for (const p of curve) {
      const day = (p.date ?? '').slice(0, 10);
      if (day) byDay.set(day, p.drawdown_pct);
    }
    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([time, value]) => ({ time, value }));
  });

  readonly equityTooltipData = computed<EquityTooltipPoint[]>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return [];
    const byDay = new Map<string, typeof curve[number]>();
    for (const p of curve) {
      const day = (p.date ?? '').slice(0, 10);
      if (day) byDay.set(day, p);
    }
    return Array.from(byDay.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([day, p]) => ({
        date: day,
        equity: p.equity,
        daily_pnl: p.daily_pnl ?? 0,
        drawdown_pct: p.drawdown_pct ?? 0,
        trade_count: p.trade_count ?? 0,
        win_count: p.win_count ?? 0,
        cumulative_trades: p.cumulative_trades ?? 0,
        cumulative_win_rate: p.cumulative_win_rate ?? 0,
      }));
  });

  readonly pollingInterval = computed(() =>
    this.trading.paperStatus()?.running ? 10_000 : 60_000,
  );

  constructor() {
    // Re-fetch timeframe-sensitive data whenever the user switches tabs.
    effect(() => {
      const days = this.timeframeSvc.days();
      // 90d heatmap needs at least 90 points; force ≥ 90 when tf is short so
      // the bottom-row heatmap always has 90d worth of history.
      const curveDays = Math.max(days, 90);
      this.trading.loadEquityCurve(curveDays);
      this.trading.loadPerformance(days);
      this.trading.loadClosedPositions({
        page: 1,
        page_size: 200,
        date_from: this.isoDaysAgo(days),
      });
    });
  }

  ngOnInit(): void {
    this.clockTimer = setInterval(() => this.clockTick.set(Date.now()), 1_000);
    this.startPolling();
    this.ws.connectPrices();
    this.news.getNews('US500', 5, 7);
  }

  ngOnDestroy(): void {
    if (this.clockTimer) { clearInterval(this.clockTimer); this.clockTimer = null; }
    if (this.pollTimer)  { clearTimeout(this.pollTimer);   this.pollTimer = null; }
  }

  private startPolling(): void {
    this.loadLive();
    const tick = () => {
      this.loadLive();
      this.pollTimer = setTimeout(tick, this.pollingInterval());
    };
    this.pollTimer = setTimeout(tick, this.pollingInterval());
  }

  private loadLive(): void {
    this.trading.loadOverview();
    this.trading.loadRiskStatus();
    this.trading.loadPaperStatus();
    this.trading.loadPaperPositions();
  }

  setTimeframe(tf: Timeframe): void {
    if (tf === 'CUSTOM') {
      this.customOpen.set(true);
      return;
    }
    this.timeframeSvc.set(tf);
  }

  applyCustomRange(): void {
    try {
      const from = new Date(this.customFrom() + 'T00:00:00Z');
      const to   = new Date(this.customTo() + 'T23:59:59Z');
      if (isNaN(from.getTime()) || isNaN(to.getTime())) return;
      this.timeframeSvc.setCustomRange(from, to);
      this.customOpen.set(false);
    } catch {
      this.toast.error('Range custom non valido');
    }
  }

  cancelCustom(): void {
    this.customOpen.set(false);
  }

  async killSwitch(): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: 'KILL SWITCH — Emergency stop',
      message: 'Chiudere TUTTE le posizioni aperte e fermare il loop? Questa azione non è reversibile.',
      confirmText: 'Emergency stop',
      cancelText: 'Annulla',
      color: 'danger',
    });
    if (!confirmed) return;
    this.killSwitchBusy.set(true);
    this.trading.emergencyStop().subscribe({
      next: (res) => {
        const closed = res.positions_closed?.length ?? 0;
        this.toast.success(`Emergency stop: ${closed} posizioni chiuse`);
        this.killSwitchBusy.set(false);
        this.loadLive();
      },
      error: (err) => {
        this.toast.error(err?.error?.error || 'Emergency stop fallito');
        this.killSwitchBusy.set(false);
      },
    });
  }

  private today(): string {
    return new Date().toISOString().slice(0, 10);
  }

  private isoDaysAgo(days: number): string {
    const d = new Date(Date.now() - days * 86_400_000);
    return d.toISOString().slice(0, 10);
  }
}
