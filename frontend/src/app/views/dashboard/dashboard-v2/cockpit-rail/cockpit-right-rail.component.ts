import { Component, ChangeDetectionStrategy, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { formatMoneyIt } from '../shared/currency.util';

/**
 * Cockpit Right Rail — 3 KPIs aligned to the equity spine (Phase 2).
 *
 * Rows:
 *   1. Max Drawdown · N d dal peak · rec. in corso|completed
 *   2. Current DD   · €curr vs peak €X
 *   3. Win Rate     · NW · ML · ▲ delta
 */
@Component({
  selector: 'app-cockpit-right-rail',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './cockpit-right-rail.component.html',
  styleUrl: './cockpit-rail.shared.scss',
})
export class CockpitRightRailComponent {
  private readonly trading = inject(TradingService);

  readonly perf = this.trading.performance;
  readonly risk = this.trading.riskStatus;

  readonly maxDrawdownPct = computed<number | null>(() => {
    const md = this.perf()?.max_drawdown;
    if (md == null) return null;
    // backend emits fraction 0..1; render as percent.
    return md > 1 ? md : md * 100;
  });

  readonly currentDdPct = computed<number | null>(() => {
    const rs = this.risk();
    if (!rs) return null;
    return (rs.current_drawdown_pct ?? 0) * 100;
  });

  readonly peakEquity   = computed<number | null>(() => this.risk()?.peak_equity ?? null);
  readonly currentEquity = computed<number | null>(() => this.risk()?.current_equity ?? null);

  readonly recoveryInProgress = computed<boolean>(() => {
    const peak = this.peakEquity() ?? 0;
    const curr = this.currentEquity() ?? 0;
    if (!peak || !curr) return false;
    return curr < peak;
  });

  /** Days since peak equity — derived from equity curve argmax. */
  readonly daysSincePeak = computed<number | null>(() => {
    const curve = this.trading.equityCurve();
    if (curve.length === 0) return null;
    let peak = -Infinity;
    let peakIdx = 0;
    for (let i = 0; i < curve.length; i++) {
      if (curve[i].equity > peak) {
        peak = curve[i].equity;
        peakIdx = i;
      }
    }
    return curve.length - 1 - peakIdx;
  });

  readonly winRate = computed<number>(() => (this.perf()?.win_rate ?? 0) * 100);
  readonly winCount  = computed<number>(() => this.perf()?.win_count  ?? 0);
  readonly lossCount = computed<number>(() => this.perf()?.loss_count ?? 0);

  /** Win-rate delta (pp) vs retro-shifted previous period — Phase 4 §A. */
  readonly winRateDeltaPp = computed<number | null>(
    () => this.trading.performanceDelta()?.delta_pp ?? null,
  );

  readonly currency = computed<string>(() => this.trading.overview()?.currency ?? 'USD');

  formatEquity(n: number): string {
    return formatMoneyIt(n, this.currency(), { signed: false });
  }
}
