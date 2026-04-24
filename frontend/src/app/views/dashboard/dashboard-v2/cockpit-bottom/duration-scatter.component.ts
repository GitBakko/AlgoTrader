import { Component, ChangeDetectionStrategy, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { currencySymbol } from '../shared/currency.util';

interface ScatterPoint {
  x: number;       // normalized x 0..1 (duration)
  y: number;       // normalized y -1..1 (pnl sign × magnitude)
  win: boolean;
  highlight: boolean;
}

interface BiasSummary {
  winAvg: number;
  lossAvg: number;
  bias: boolean;
  biasPctOver: number;
  winEurPerHour: number;
  lossEurPerHour: number;
}

/**
 * Duration × PnL scatter — reveals late-exit bias.
 * Reads from TradingService.closedPositions (parent triggers the load).
 */
@Component({
  selector: 'app-duration-scatter',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './duration-scatter.component.html',
  styleUrl: './duration-scatter.component.scss',
})
export class DurationScatterComponent {
  private readonly trading = inject(TradingService);

  /** Clamp x axis to 180 minutes like the mock. */
  private readonly MAX_DURATION = 180;

  readonly closed = this.trading.closedPositions;

  readonly points = computed<ScatterPoint[]>(() => {
    const arr = this.closed();
    if (arr.length === 0) return [];
    const maxPnl = Math.max(
      1,
      ...arr.map(p => Math.abs(p.profit_loss ?? 0)),
    );
    return arr
      .filter(p => p.duration_minutes != null && p.profit_loss != null)
      .map(p => {
        const dur = Math.min(p.duration_minutes ?? 0, this.MAX_DURATION);
        const pnl = p.profit_loss ?? 0;
        return {
          x: dur / this.MAX_DURATION,
          y: pnl / maxPnl,
          win: pnl > 0,
          highlight: Math.abs(pnl) / maxPnl > 0.7,
        } as ScatterPoint;
      });
  });

  readonly hasData = computed(() => this.points().length > 0);
  readonly tradeCount = computed(() => this.points().length);

  /**
   * Prefer the backend aggregate (`performance.duration_medians`) added in
   * §2.6 — avoids recomputing the whole closed-positions list client-side
   * every tick. Fall back to client-side aggregation when the backend
   * hasn't shipped yet (old builds / empty response).
   */
  readonly bias = computed<BiasSummary | null>(() => {
    const perf = this.trading.performance();
    const medians = perf?.duration_medians;
    const avgWinPnl  = perf?.avg_win  ?? 0;
    const avgLossPnl = perf?.avg_loss ?? 0; // typically negative
    const eurPerHour = (pnl: number, mins: number) =>
      mins > 0 ? pnl / (mins / 60) : 0;

    if (medians && (medians.win_count > 0 || medians.loss_count > 0)) {
      if (medians.win_count === 0 || medians.loss_count === 0) return null;
      return {
        winAvg:  medians.win_avg_min,
        lossAvg: medians.loss_avg_min,
        bias:    medians.late_exit_bias,
        biasPctOver: medians.bias_pct_over,
        winEurPerHour:  eurPerHour(avgWinPnl,  medians.win_avg_min),
        lossEurPerHour: eurPerHour(avgLossPnl, medians.loss_avg_min),
      };
    }
    const arr = this.closed().filter(p => p.duration_minutes != null && p.profit_loss != null);
    if (arr.length < 2) return null;
    const wins = arr.filter(p => (p.profit_loss ?? 0) > 0);
    const losses = arr.filter(p => (p.profit_loss ?? 0) < 0);
    if (wins.length === 0 || losses.length === 0) return null;
    const avg = (xs: number[]) => xs.reduce((s, v) => s + v, 0) / xs.length;
    const winAvg  = avg(wins.map(p => p.duration_minutes ?? 0));
    const lossAvg = avg(losses.map(p => p.duration_minutes ?? 0));
    const winPnlAvg  = avg(wins.map(p => p.profit_loss ?? 0));
    const lossPnlAvg = avg(losses.map(p => p.profit_loss ?? 0));
    const bias = lossAvg > winAvg * 1.3;
    const biasPctOver = winAvg > 0 ? ((lossAvg - winAvg) / winAvg) * 100 : 0;
    return {
      winAvg, lossAvg, bias, biasPctOver,
      winEurPerHour:  eurPerHour(winPnlAvg,  winAvg),
      lossEurPerHour: eurPerHour(lossPnlAvg, lossAvg),
    };
  });

  readonly currency = computed<string>(() => this.trading.overview()?.currency ?? 'USD');
  readonly currencySym = computed<string>(() => currencySymbol(this.currency()));

  formatEurPerHour(n: number): string {
    const sign = n > 0 ? '+' : n < 0 ? '−' : '';
    const abs = Math.abs(n);
    return `${sign}${this.currencySym()}${abs.toFixed(abs >= 100 ? 0 : 2)}/h`;
  }

  readonly winMedianX = computed(() => {
    const b = this.bias();
    return b ? Math.min(b.winAvg, this.MAX_DURATION) / this.MAX_DURATION : null;
  });

  readonly lossMedianX = computed(() => {
    const b = this.bias();
    return b ? Math.min(b.lossAvg, this.MAX_DURATION) / this.MAX_DURATION : null;
  });

  readonly formatDuration = (minutes: number): string => {
    const m = Math.round(minutes);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    const r = m % 60;
    return r === 0 ? `${h}h` : `${h}h ${r}m`;
  };
}
