import { Component, ChangeDetectionStrategy, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';

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

  readonly bias = computed<BiasSummary | null>(() => {
    const arr = this.closed().filter(p => p.duration_minutes != null && p.profit_loss != null);
    if (arr.length < 2) return null;
    const wins = arr.filter(p => (p.profit_loss ?? 0) > 0);
    const losses = arr.filter(p => (p.profit_loss ?? 0) < 0);
    if (wins.length === 0 || losses.length === 0) return null;
    const avg = (xs: number[]) => xs.reduce((s, v) => s + v, 0) / xs.length;
    const winAvg  = avg(wins.map(p => p.duration_minutes ?? 0));
    const lossAvg = avg(losses.map(p => p.duration_minutes ?? 0));
    const bias = lossAvg > winAvg * 1.3;
    const biasPctOver = winAvg > 0 ? ((lossAvg - winAvg) / winAvg) * 100 : 0;
    return { winAvg, lossAvg, bias, biasPctOver };
  });

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
