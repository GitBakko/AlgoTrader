import { Component, ChangeDetectionStrategy, computed, inject, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TimeframeService } from '../../../../core/services/timeframe.service';
import { TradeBreakdownDay, TradeOutcomeSide } from './trade-breakdown.types';

/**
 * DASHBOARD v2 — Deliverable C
 *
 * Per-day BUY/SELL × TP/SL/Going breakdown chart. Columns above zero axis
 * stack BUY outcomes, columns below stack SELL outcomes. Focus panel on
 * the right reads the day currently under cursor / touch.
 *
 * TODO — BACKEND (next sprint, MANDATORY):
 *   GET /api/trading/performance/breakdown?tf={1D|7D|30D|90D|YTD|ALL|CUSTOM}
 *     &from=YYYY-MM-DD&to=YYYY-MM-DD    (solo se tf === CUSTOM)
 *   → TradeBreakdownResponse (shape in trade-breakdown.types.ts)
 *
 * Finché l'endpoint non esiste, il componente NON sintetizza numeri
 * (§14 Definition of Done) e mostra un banner di stato.
 */
@Component({
  selector: 'app-trade-breakdown',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './trade-breakdown.component.html',
  styleUrl: './trade-breakdown.component.scss',
})
export class TradeBreakdownComponent {
  private readonly timeframe = inject(TimeframeService);

  /** Upstream data from parent. `null` = backend endpoint missing. */
  readonly days = input<TradeBreakdownDay[] | null>(null);

  readonly focusedIndex = signal<number | null>(null);

  readonly activeDays = computed<TradeBreakdownDay[]>(() => this.days() ?? []);

  readonly hasData = computed<boolean>(() => this.activeDays().length > 0);

  readonly isBackendMissing = computed<boolean>(() => this.days() === null);

  readonly maxStack = computed<number>(() => {
    const arr = this.activeDays();
    if (arr.length === 0) return 1;
    let max = 1;
    for (const d of arr) {
      max = Math.max(max, sideTotal(d.buy), sideTotal(d.sell));
    }
    return max;
  });

  readonly focused = computed<TradeBreakdownDay | null>(() => {
    const arr = this.activeDays();
    if (arr.length === 0) return null;
    const idx = this.focusedIndex() ?? arr.length - 1;
    return arr[Math.max(0, Math.min(idx, arr.length - 1))] ?? null;
  });

  readonly focusedDayPnl = computed<number>(() => {
    const d = this.focused();
    if (!d) return 0;
    return d.buy.pnl + d.sell.pnl;
  });

  readonly focusedStillOpen = computed<number>(() => {
    const d = this.focused();
    if (!d) return 0;
    return d.buy.going + d.sell.going;
  });

  readonly timeframeLabel = computed(() => this.timeframe.label());
  readonly daysCount = computed(() => this.activeDays().filter(d => sideTotal(d.buy) + sideTotal(d.sell) > 0).length);

  readonly firstDate = computed<string>(() => this.activeDays()[0]?.date ?? '');
  readonly lastDate  = computed<string>(() => {
    const arr = this.activeDays();
    return arr[arr.length - 1]?.date ?? '';
  });
  readonly midDate = computed<string>(() => {
    const arr = this.activeDays();
    if (arr.length <= 14) return '';
    return arr[Math.floor(arr.length / 2)]?.date ?? '';
  });

  setFocus(i: number): void {
    this.focusedIndex.set(i);
  }

  clearFocus(): void {
    this.focusedIndex.set(null);
  }

  /** Percentage height for a stacked segment, rounded to the nearest 0.1%. */
  segmentHeightPct(value: number): number {
    const max = this.maxStack();
    if (max <= 0) return 0;
    return Math.round((value / max) * 1000) / 10;
  }

  sideTotal = sideTotal;

  formatShortDate(iso: string): string {
    if (!iso) return '';
    try {
      const d = new Date(iso + 'T00:00:00Z');
      return d.toLocaleDateString('it-IT', { day: '2-digit', month: 'short', timeZone: 'UTC' });
    } catch { return iso; }
  }

  formatFocusDate(iso: string): string {
    if (!iso) return '';
    try {
      const d = new Date(iso + 'T00:00:00Z');
      return d.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
    } catch { return iso; }
  }

  formatMoney(value: number): string {
    const sign = value > 0 ? '+' : value < 0 ? '−' : '';
    return `${sign}€${Math.abs(value).toLocaleString('it-IT', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  }
}

function sideTotal(side: TradeOutcomeSide): number {
  return side.tp + side.sl + side.going;
}
