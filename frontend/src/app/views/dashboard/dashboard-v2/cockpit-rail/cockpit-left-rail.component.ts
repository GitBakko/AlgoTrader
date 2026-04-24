import { Component, ChangeDetectionStrategy, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { formatMoneyIt, formatMoneyCompactIt } from '../shared/currency.util';

/**
 * Cockpit Left Rail — 3 KPIs aligned to the equity spine (Phase 2).
 *
 * Rows:
 *   1. Profit Factor  · gross +X / −Y · soglia 1.3 ✓
 *   2. Calmar         · Sharpe X · Sortino Y
 *   3. Expectancy     · per trade · N closed
 *
 * All numbers read live from TradingService.performance() signal.
 */
@Component({
  selector: 'app-cockpit-left-rail',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './cockpit-left-rail.component.html',
  styleUrl: './cockpit-rail.shared.scss',
})
export class CockpitLeftRailComponent {
  private readonly trading = inject(TradingService);

  readonly perf = this.trading.performance;

  readonly profitFactor = computed<number | null>(() => this.perf()?.profit_factor ?? null);

  readonly grossProfit = computed<number>(() => {
    const p = this.perf();
    if (!p) return 0;
    return (p.avg_win ?? 0) * (p.win_count ?? 0);
  });

  readonly grossLoss = computed<number>(() => {
    const p = this.perf();
    if (!p) return 0;
    return (p.avg_loss ?? 0) * (p.loss_count ?? 0);
  });

  readonly profitFactorMeetsThreshold = computed<boolean>(() => (this.profitFactor() ?? 0) >= 1.3);

  readonly calmar  = computed<number | null>(() => this.perf()?.calmar_ratio  ?? null);
  readonly sharpe  = computed<number | null>(() => this.perf()?.sharpe_ratio  ?? null);
  readonly sortino = computed<number | null>(() => this.perf()?.sortino_ratio ?? null);

  /** Expectancy = win_rate × avg_win + (1-win_rate) × avg_loss */
  readonly expectancy = computed<number | null>(() => {
    const p = this.perf();
    if (!p) return null;
    const wr = p.win_rate ?? 0;
    const aw = p.avg_win  ?? 0;
    const al = p.avg_loss ?? 0;
    return wr * aw + (1 - wr) * al;
  });

  readonly tradeCount = computed<number>(() => this.perf()?.trade_count ?? 0);
  readonly currency = computed<string>(() => this.trading.overview()?.currency ?? 'USD');

  formatCompactMoney(n: number): string {
    return formatMoneyCompactIt(n, this.currency());
  }

  formatMoney(n: number): string {
    return formatMoneyIt(n, this.currency());
  }

  formatRatio(n: number | null): string {
    if (n == null) return '—';
    return n.toFixed(2);
  }
}
