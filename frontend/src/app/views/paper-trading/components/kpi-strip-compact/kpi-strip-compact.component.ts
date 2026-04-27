import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import type { KpiStrip } from '../../../../core/models/paper-trading';

/**
 * KPI Strip Compact — center hero (HANDOFF §3.5).
 *
 * Six CARD-02 cells in a horizontal grid:
 *   1. P&L Open    · sparkOpen
 *   2. P&L Today   · sparkToday
 *   3. Open Pos    · count only
 *   4. Win / Sig   · `WR% · Nsig`
 *   5. R:R Avg     · cyan
 *   6. DD Live     · `pct · gate%` + mini bar
 */
@Component({
  selector: 'app-kpi-strip-compact',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DecimalPipe],
  templateUrl: './kpi-strip-compact.component.html',
  styleUrls: ['./kpi-strip-compact.component.scss'],
})
export class KpiStripCompactComponent {
  readonly kpi = input.required<KpiStrip>();
  readonly currency = input<string>('USD');

  readonly currencySym = computed(() => {
    const code = (this.currency() ?? 'USD').replace(/d$/, '');
    switch (code) {
      case 'USD': return '$';
      case 'EUR': return '€';
      case 'GBP': return '£';
      default:    return code + ' ';
    }
  });

  readonly pnlOpenPath = computed(() => buildSparkPath(this.kpi().sparkOpen ?? []));
  readonly pnlTodayPath = computed(() => buildSparkPath(this.kpi().sparkToday ?? []));

  readonly pnlOpenSign = computed(() => Math.sign(this.kpi().pnlOpen));
  readonly pnlTodaySign = computed(() => Math.sign(this.kpi().pnlToday));

  /** DD bar fill — clamp to 0..100 of gate. */
  readonly ddBarPct = computed(() => {
    const k = this.kpi();
    if (!k.ddGate) return 0;
    return Math.min(100, Math.max(0, (Math.abs(k.ddLive) / k.ddGate) * 100));
  });
}

function buildSparkPath(data: number[]): string {
  if (data.length < 2) return '';
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = 100 / (data.length - 1);
  return data
    .map((v, i) => {
      const x = i * stepX;
      const y = 100 - ((v - min) / range) * 100;
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}
