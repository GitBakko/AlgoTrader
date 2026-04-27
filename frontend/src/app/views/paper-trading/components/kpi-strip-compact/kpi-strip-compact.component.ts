import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { SkeletonKpiCellComponent } from '../../../../shared/components/skeleton-kpi-cell/skeleton-kpi-cell.component';
import type { KpiStrip } from '../../../../core/models/paper-trading';

interface SkeletonCellSpec {
  accent: 'profit' | 'loss' | 'info' | 'warn' | 'neutral';
  spark: boolean;
}

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
  imports: [CommonModule, DecimalPipe, SkeletonKpiCellComponent],
  templateUrl: './kpi-strip-compact.component.html',
  styleUrls: ['./kpi-strip-compact.component.scss'],
})
export class KpiStripCompactComponent {
  readonly kpi = input.required<KpiStrip>();
  readonly currency = input<string>('USD');
  /** Render six skeleton cells in place of the strip while waiting for the
   *  first /trading/status response. Layout stays identical so resolved
   *  data drops in without shifting the cockpit grid. */
  readonly loading = input<boolean>(false);

  /** Six placeholder specs that mirror the resolved cell accents. */
  readonly skeletonCells: SkeletonCellSpec[] = [
    { accent: 'profit',  spark: true  }, // P&L Open
    { accent: 'profit',  spark: true  }, // P&L Today
    { accent: 'info',    spark: false }, // Open
    { accent: 'info',    spark: false }, // Win/Sig
    { accent: 'info',    spark: false }, // R:R
    { accent: 'loss',    spark: false }, // DD Live
  ];

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

  /** Open Positions cell — slot pips, filled for live, hollow for free. */
  readonly slotPips = computed(() => {
    const open = Math.max(0, this.kpi().openCount);
    const max = 5;
    return Array.from({ length: max }, (_, i) => i < open);
  });

  /** Win/Sig cell — stacked bar (win/miss) + signals intensity meter. */
  readonly winSigBars = computed(() => {
    const win = Math.min(100, Math.max(0, this.kpi().winRate));
    const intensity = Math.min(100, this.kpi().signalsTotal);
    return { win, miss: 100 - win, intensity };
  });

  /** R:R gauge — normalize 0..3 to 0..100% on a horizontal track. */
  readonly rrPct = computed(() => Math.min(100, Math.max(0, (this.kpi().rr / 3) * 100)));

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
