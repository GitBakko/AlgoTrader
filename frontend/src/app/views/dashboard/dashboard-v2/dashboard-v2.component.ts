import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';

import { TradingService } from '../../../core/services/trading.service';
import { WebSocketService } from '../../../core/services/websocket.service';
import { NewsService } from '../../../core/services/news.service';
import { TimeframeService, TIMEFRAME_OPTIONS, Timeframe } from '../../../core/services/timeframe.service';
import { ConfirmDialogService } from '../../../shared/services/confirm-dialog.service';
import { ToastService } from '../../../shared/services/toast.service';

import { TvChartComponent, LineDataPoint, EquityTooltipPoint } from '../../../shared/components/tv-chart/tv-chart.component';

import { OperationalStripComponent } from './operational-strip/operational-strip.component';
import { CockpitLeftRailComponent } from './cockpit-rail/cockpit-left-rail.component';
import { CockpitRightRailComponent } from './cockpit-rail/cockpit-right-rail.component';
import { DurationScatterComponent } from './cockpit-bottom/duration-scatter.component';
import { OvernightSwapComponent } from './cockpit-bottom/overnight-swap.component';
import { CalendarHeatmapComponent } from './cockpit-bottom/calendar-heatmap.component';
import { TradeBreakdownComponent } from './trade-breakdown/trade-breakdown.component';
import { CbBannerComponent } from '../../../shared/components/cb-banner/cb-banner.component';
import { currencySymbol } from './shared/currency.util';

/**
 * DASHBOARD v2 — Deliverable A (Variant B "Cockpit")
 * Route: `/dashboard-v2` — affianco a `/dashboard` legacy.
 *
 * Tutti i tile ora sono wired a endpoint backend live:
 *   - /api/trading/performance/breakdown       → TradeBreakdown
 *   - /api/trading/performance (+ extensions)  → KPI rail + OperationalStrip
 *   - /api/markets/{epic}/overnight-swap       → OvernightSwap (replaces Bybit)
 *   - /api/models/current                      → OperationalStrip tile 6
 *   - /ws/prices ping/pong                     → OperationalStrip tile 2 latency
 */
@Component({
  selector: 'app-dashboard-v2',
  standalone: true,
  imports: [
    CommonModule,
    TvChartComponent,
    OperationalStripComponent,
    CockpitLeftRailComponent,
    CockpitRightRailComponent,
    DurationScatterComponent,
    OvernightSwapComponent,
    CalendarHeatmapComponent,
    TradeBreakdownComponent,
    CbBannerComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard-v2.component.html',
  styleUrl: './dashboard-v2.component.scss',
})
export class DashboardV2Component implements OnInit {
  readonly trading = inject(TradingService);
  private readonly destroyRef = inject(DestroyRef);
  readonly ws = inject(WebSocketService);
  readonly timeframeSvc = inject(TimeframeService);
  private readonly news = inject(NewsService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  private readonly toast = inject(ToastService);

  readonly timeframes: readonly Timeframe[] = TIMEFRAME_OPTIONS;
  readonly activeTimeframe = this.timeframeSvc.current;

  private pollTimer: ReturnType<typeof setTimeout> | null = null;

  readonly killSwitchBusy = signal(false);
  readonly customOpen = signal(false);
  readonly customFrom = signal<string>(this.isoDaysAgo(30));
  readonly customTo   = signal<string>(this.today());

  /** Earliest date visible in the current equity curve — header subtitle. */
  readonly sinceDate = computed<string | null>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return null;
    const first = curve[0].date ?? '';
    return first.slice(0, 10) || null;
  });

  /** Total closed trades in the current timeframe — header subtitle. */
  readonly closedTrades = computed<number>(() => this.trading.performance()?.trade_count ?? 0);

  /** Broker-sourced currency symbol for the whole dashboard. */
  readonly currencySym = computed<string>(() => currencySymbol(this.trading.overview()?.currency ?? 'USD'));

  /** Pulls breakdown days straight from the TradingService signal so the
   *  child stays a dumb presenter. */
  readonly breakdownDays = computed(
    () => this.trading.tradeBreakdown()?.days ?? null,
  );

  /** User-picked epic for the overnight-swap tile. null = auto (first
   *  open paper position, then XAUUSD). Set by clicking a position card
   *  in the operational strip. Reset automatically when the picked epic
   *  has no live position anymore. */
  readonly userSwapEpic = signal<string | null>(null);

  /** Epic displayed in the overnight-swap tile. Prefers the user pick
   *  when it's still open at broker; falls back to the first open paper
   *  position; finally XAUUSD. */
  readonly swapEpic = computed<string>(() => {
    const positions = this.trading.paperPositions();
    const pick = this.userSwapEpic();
    if (pick && positions.some(p => p.epic === pick)) return pick;
    return positions[0]?.epic ?? 'XAUUSD';
  });

  selectSwapEpic(epic: string): void {
    // Toggle off when re-clicking the current pick so a user can revert
    // to automatic (first-open) behaviour without refreshing.
    if (this.userSwapEpic() === epic) {
      this.userSwapEpic.set(null);
    } else {
      this.userSwapEpic.set(epic);
    }
  }

  readonly headlineEquity = computed(() => this.trading.overview()?.equity ?? null);
  readonly headlineDailyPct = computed(() => {
    const ov = this.trading.overview();
    if (!ov || ov.equity === 0) return null;
    return (ov.daily_pnl / ov.equity) * 100;
  });

  /** Cumulative ROI % since the earliest point of the current equity curve. */
  readonly roiPct = computed<number | null>(() => {
    const curve = this.trading.equityCurve();
    const eq = this.headlineEquity();
    if (curve.length === 0 || eq == null) return null;
    const initial = curve[0].equity;
    if (!initial) return null;
    return ((eq - initial) / initial) * 100;
  });

  /**
   * Peak / Max-DD overlay markers for the equity spine.
   * Coords are percentages relative to the chart canvas, approximating
   * tv-chart's rendering (linear X by index, linear Y by equity range).
   */
  readonly chartRange = computed<{ min: number; max: number; n: number } | null>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length < 2) return null;
    let min = Infinity;
    let max = -Infinity;
    for (const p of curve) {
      if (p.equity < min) min = p.equity;
      if (p.equity > max) max = p.equity;
    }
    if (min === max) return null;
    return { min, max, n: curve.length };
  });

  readonly peakMarker = computed<{ xPct: number; yPct: number; equity: number; date: string } | null>(() => {
    const curve = this.trading.equityCurve();
    const range = this.chartRange();
    if (!range || curve.length < 2) return null;
    let idx = 0;
    for (let i = 1; i < curve.length; i++) {
      if (curve[i].equity > curve[idx].equity) idx = i;
    }
    const p = curve[idx];
    return {
      xPct: (idx / (range.n - 1)) * 100,
      yPct: (1 - (p.equity - range.min) / (range.max - range.min)) * 100,
      equity: p.equity,
      date: (p.date ?? '').slice(0, 10),
    };
  });

  readonly maxDdMarker = computed<{ xPct: number; yPct: number; ddPct: number; date: string } | null>(() => {
    const curve = this.trading.equityCurve();
    const range = this.chartRange();
    if (!range || curve.length < 2) return null;
    let idx = 0;
    for (let i = 1; i < curve.length; i++) {
      if (curve[i].drawdown_pct < curve[idx].drawdown_pct) idx = i;
    }
    const p = curve[idx];
    if (p.drawdown_pct >= 0) return null; // no drawdown → no marker
    return {
      xPct: (idx / (range.n - 1)) * 100,
      yPct: (1 - (p.equity - range.min) / (range.max - range.min)) * 100,
      ddPct: p.drawdown_pct,
      date: (p.date ?? '').slice(0, 10),
    };
  });

  /** Horizontal dashed peak-line y-position (pct from top). */
  readonly peakLineY = computed<number | null>(() => {
    const peak = this.peakMarker();
    return peak ? peak.yPct : null;
  });

  /** Breakeven line (initial equity) — only if in chart range. */
  readonly breakevenY = computed<number | null>(() => {
    const curve = this.trading.equityCurve();
    const range = this.chartRange();
    if (!range || curve.length === 0) return null;
    const initial = curve[0].equity;
    if (initial < range.min || initial > range.max) return null;
    return (1 - (initial - range.min) / (range.max - range.min)) * 100;
  });

  /** Annualized return, geometric: (1 + roi) ^ (365/days) - 1 */
  readonly annualizedPct = computed<number | null>(() => {
    const curve = this.trading.equityCurve();
    const roi = this.roiPct();
    if (curve.length < 2 || roi == null) return null;
    const days = Math.max(1, curve.length);
    const factor = 1 + roi / 100;
    if (factor <= 0) return null;
    const ann = Math.pow(factor, 365 / days) - 1;
    return ann * 100;
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
      const tf = this.timeframeSvc.current();
      const days = this.timeframeSvc.days();
      // Equity spine follows tf exactly — heatmap has its own fixed 90d load
      // in ngOnInit (see loadHeatmapCurve) so it stays 90d independent of tf.
      this.trading.loadEquityCurve(days);
      this.trading.loadPerformance(days);
      this.trading.loadClosedPositions({
        page: 1,
        page_size: 200,
        date_from: this.isoDaysAgo(days),
      });

      // Dashboard v2 breakdown — uses the active timeframe directly.
      const range = this.timeframeSvc.customRange();
      if (tf === 'CUSTOM' && range) {
        const from = range.from.toISOString().slice(0, 10);
        const to = range.to.toISOString().slice(0, 10);
        this.trading.loadPerformanceBreakdown('CUSTOM', from, to);
        this.trading.loadPerformanceDelta('CUSTOM', from, to);
      } else {
        this.trading.loadPerformanceBreakdown(tf);
        this.trading.loadPerformanceDelta(tf);
      }
    });
  }

  ngOnInit(): void {
    this.startPolling();
    this.ws.connectPrices();
    this.ws.connectMarkets();
    this.news.getNews('US500', 5, 7);
    this.trading.loadCurrentModels();

    this.destroyRef.onDestroy(() => {
      if (this.pollTimer) { clearTimeout(this.pollTimer); this.pollTimer = null; }
    });
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
    this.trading.emergencyStop().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
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
