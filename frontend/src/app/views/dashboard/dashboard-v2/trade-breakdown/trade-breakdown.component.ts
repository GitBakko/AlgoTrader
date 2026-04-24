import { Component, ChangeDetectionStrategy, computed, inject, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { TimeframeService } from '../../../../core/services/timeframe.service';
import { formatMoneyIt } from '../shared/currency.util';
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
  private readonly trading = inject(TradingService);
  readonly currency = computed<string>(() => this.trading.overview()?.currency ?? 'USD');

  /** Upstream data from parent. `null` = backend endpoint missing. */
  readonly days = input<TradeBreakdownDay[] | null>(null);

  readonly focusedIndex = signal<number | null>(null);

  readonly activeDays = computed<TradeBreakdownDay[]>(() => this.days() ?? []);

  readonly hasData = computed<boolean>(() => this.activeDays().length > 0);

  readonly isBackendMissing = computed<boolean>(() => this.days() === null);

  /**
   * Chart Y-axis scale = P90 of non-zero CLOSED-outcome side totals
   * (tp + sl only). `going` is excluded from the scale because it only
   * reflects the single currently-open position. Days whose tp+sl
   * exceed the P90 scale get clipped + tagged with an overflow badge.
   */
  readonly maxStack = computed<number>(() => {
    const arr = this.activeDays();
    if (arr.length === 0) return 1;
    const vals: number[] = [];
    for (const d of arr) {
      const b = d.buy.tp + d.buy.sl;
      const s = d.sell.tp + d.sell.sl;
      if (b > 0) vals.push(b);
      if (s > 0) vals.push(s);
    }
    if (vals.length === 0) return 5;
    vals.sort((a, b) => a - b);
    const idx = Math.min(vals.length - 1, Math.floor(vals.length * 0.9));
    const p90 = vals[idx] ?? vals[vals.length - 1];
    return Math.max(5, Math.ceil(p90 / 5) * 5);
  });

  /** Absolute max tp+sl — overflow detection + meta. */
  readonly trueMax = computed<number>(() => {
    const arr = this.activeDays();
    if (arr.length === 0) return 0;
    let max = 0;
    for (const d of arr) {
      max = Math.max(max, d.buy.tp + d.buy.sl, d.sell.tp + d.sell.sl);
    }
    return max;
  });

  readonly hasOverflow = computed<boolean>(() => this.trueMax() > this.maxStack());

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
  readonly tradeTotal = computed(() =>
    this.activeDays().reduce((sum, d) => sum + sideTotal(d.buy) + sideTotal(d.sell), 0),
  );

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

  /** Percentage height for a stacked segment, capped at 100% (overflow-safe). */
  segmentHeightPct(value: number): number {
    const max = this.maxStack();
    if (max <= 0) return 0;
    const pct = (value / max) * 100;
    return Math.round(Math.min(100, pct) * 10) / 10;
  }

  /** True if tp+sl for a side exceeds the chart's P75 scale. */
  isOverflow(side: TradeOutcomeSide): boolean {
    return (side.tp + side.sl) > this.maxStack();
  }

  /** Label displayed on overflow badge — total tp+sl for the overflowing side. */
  overflowValue(side: TradeOutcomeSide): number {
    return side.tp + side.sl;
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
    return formatMoneyIt(value, this.currency(), { minDec: 0, maxDec: 2 });
  }
}

function sideTotal(side: TradeOutcomeSide): number {
  return side.tp + side.sl + side.going;
}
