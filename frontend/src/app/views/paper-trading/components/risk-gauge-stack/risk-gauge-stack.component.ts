import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import type { GaugeStatus, RiskState } from '../../../../core/models/paper-trading';

/**
 * Risk Gauge Stack — left rail (HANDOFF §3.3).
 *
 * Four CARD-03 mini-rows (border-left 3px state color):
 *   1. Circuit Breakers · OK/WARN/ERROR + tripped count
 *   2. Equity Filter    · DD% / threshold + horizontal bar
 *   3. Kelly Sizing     · ATTIVO/PAUSED + avg/win/pnl
 *   4. Trading Stops    · OK + count
 */
@Component({
  selector: 'app-risk-gauge-stack',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DecimalPipe],
  templateUrl: './risk-gauge-stack.component.html',
  styleUrls: ['./risk-gauge-stack.component.scss'],
})
export class RiskGaugeStackComponent {
  readonly risk = input.required<RiskState>();

  readonly equityBarPct = computed(() => {
    const r = this.risk().equityFilter;
    if (!r.threshold) return 0;
    return Math.min(100, Math.max(0, (Math.abs(r.dd) / r.threshold) * 100));
  });

  statusClass(status: GaugeStatus): string {
    switch (status) {
      case 'OK':
      case 'ATTIVO':
        return 'is-ok';
      case 'WARN':
      case 'PAUSED':
        return 'is-warn';
      case 'ERROR':
        return 'is-error';
      default:
        return 'is-neutral';
    }
  }
}
