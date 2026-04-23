import { Injectable, signal, computed } from '@angular/core';

export type Timeframe = '1D' | '7D' | '30D' | '90D' | 'YTD' | 'ALL' | 'CUSTOM';

export const TIMEFRAME_OPTIONS: readonly Timeframe[] = [
  '1D', '7D', '30D', '90D', 'YTD', 'ALL', 'CUSTOM',
] as const;

export interface CustomRange {
  from: Date;
  to: Date;
}

/**
 * Shared signal-based timeframe state for the v2 dashboard.
 * Every cockpit child (equity chart, KPI rail, breakdown, heatmap)
 * reads from `current()` + `days()` and recomputes reactively.
 */
@Injectable({ providedIn: 'root' })
export class TimeframeService {
  readonly current = signal<Timeframe>('30D');
  readonly customRange = signal<CustomRange | null>(null);

  readonly days = computed<number>(() => {
    const tf = this.current();
    if (tf === '1D') return 1;
    if (tf === '7D') return 7;
    if (tf === '30D') return 30;
    if (tf === '90D') return 90;
    if (tf === 'ALL') return 3650;
    if (tf === 'YTD') {
      const now = new Date();
      const start = new Date(Date.UTC(now.getUTCFullYear(), 0, 1));
      const diffMs = now.getTime() - start.getTime();
      return Math.max(1, Math.ceil(diffMs / 86_400_000));
    }
    const range = this.customRange();
    if (tf === 'CUSTOM' && range) {
      const diffMs = range.to.getTime() - range.from.getTime();
      return Math.max(1, Math.ceil(diffMs / 86_400_000));
    }
    return 30;
  });

  readonly label = computed<string>(() => {
    const tf = this.current();
    if (tf !== 'CUSTOM') return tf;
    const range = this.customRange();
    if (!range) return 'CUSTOM';
    const fmt = (d: Date) => d.toISOString().slice(0, 10);
    return `${fmt(range.from)} → ${fmt(range.to)}`;
  });

  set(tf: Timeframe): void {
    this.current.set(tf);
    if (tf !== 'CUSTOM') {
      this.customRange.set(null);
    }
  }

  setCustomRange(from: Date, to: Date): void {
    if (from.getTime() > to.getTime()) {
      [from, to] = [to, from];
    }
    this.customRange.set({ from, to });
    this.current.set('CUSTOM');
  }
}
