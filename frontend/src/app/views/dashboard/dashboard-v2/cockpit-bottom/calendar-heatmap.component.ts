import { Component, ChangeDetectionStrategy, computed, inject, LOCALE_ID, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { TimeframeService } from '../../../../core/services/timeframe.service';
import { currencySymbol, formatMoneyIt } from '../shared/currency.util';

interface HeatmapCell {
  date: string;        // YYYY-MM-DD
  pnl: number;
  tradeCount: number;
  winCount: number;
  equity: number;
  isEmpty: boolean;
}

interface WeekColumn {
  cells: (HeatmapCell | null)[]; // length 7, Mon-Sun, null = no cell yet
}

/**
 * 90-day calendar heatmap of daily P&L.
 * Reads from TradingService.equityCurve() — parent triggers a
 * `loadEquityCurve(90)` before mounting.
 */
@Component({
  selector: 'app-calendar-heatmap',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './calendar-heatmap.component.html',
  styleUrl: './calendar-heatmap.component.scss',
})
export class CalendarHeatmapComponent {
  private readonly trading = inject(TradingService);
  private readonly tf = inject(TimeframeService);
  private readonly localeId = inject(LOCALE_ID);

  readonly equityCurve = this.trading.equityCurve;

  /** Label for the card header — matches active tf (e.g. "7d", "30d", "YTD"). */
  readonly tfLabel = computed<string>(() => this.tf.label().toLowerCase());

  /**
   * Mon-Sun narrow weekday initials localized to LOCALE_ID (it-IT → L M M G V S D).
   * Derived once per instance — locale doesn't change at runtime.
   */
  readonly dayInitials: string[] = (() => {
    const fmt = new Intl.DateTimeFormat(this.localeId, {
      weekday: 'narrow',
      timeZone: 'UTC',
    });
    const out: string[] = [];
    // 2024-01-01 was Monday → 01..07 covers Mon-Sun.
    for (let i = 1; i <= 7; i++) {
      out.push(fmt.format(new Date(Date.UTC(2024, 0, i))).toUpperCase());
    }
    return out;
  })();

  readonly focusIndex = signal<number | null>(null);

  readonly cells = computed<HeatmapCell[]>(() => {
    const curve = this.equityCurve();
    if (curve.length === 0) return [];
    // Deduplicate last value per UTC day
    const byDay = new Map<string, HeatmapCell>();
    for (const p of curve) {
      const day = (p.date ?? '').slice(0, 10);
      if (!day) continue;
      const winCount = p.win_count ?? 0;
      const tradeCount = p.trade_count ?? 0;
      byDay.set(day, {
        date: day,
        pnl: p.daily_pnl ?? 0,
        tradeCount,
        winCount,
        equity: p.equity ?? 0,
        isEmpty: tradeCount === 0 && (p.daily_pnl ?? 0) === 0,
      });
    }
    return Array.from(byDay.values()).sort((a, b) => a.date.localeCompare(b.date));
  });

  readonly maxAbsPnl = computed<number>(() => {
    let max = 1;
    for (const c of this.cells()) {
      max = Math.max(max, Math.abs(c.pnl));
    }
    return max;
  });

  readonly best = computed<number>(() => {
    const arr = this.cells();
    if (arr.length === 0) return 0;
    return arr.reduce((m, c) => Math.max(m, c.pnl), -Infinity);
  });

  readonly worst = computed<number>(() => {
    const arr = this.cells();
    if (arr.length === 0) return 0;
    return arr.reduce((m, c) => Math.min(m, c.pnl), Infinity);
  });

  readonly weeks = computed<WeekColumn[]>(() => {
    const arr = this.cells();
    if (arr.length === 0) return [];
    const weeks: WeekColumn[] = [];
    let current: (HeatmapCell | null)[] = new Array(7).fill(null);
    let hasAny = false;
    for (const c of arr) {
      const d = new Date(c.date + 'T00:00:00Z');
      const dow = d.getUTCDay(); // 0=Sun..6=Sat
      // Remap so Monday=0..Sunday=6
      const idx = (dow + 6) % 7;
      current[idx] = c;
      hasAny = true;
      if (idx === 6) {
        weeks.push({ cells: current });
        current = new Array(7).fill(null);
        hasAny = false;
      }
    }
    if (hasAny) weeks.push({ cells: current });
    return weeks;
  });

  readonly focused = computed<HeatmapCell | null>(() => {
    const arr = this.cells();
    const idx = this.focusIndex();
    if (idx == null) return arr.length > 0 ? arr[arr.length - 1] : null;
    return arr[idx] ?? null;
  });

  /** Returns the global index of a cell object (for focus tracking). */
  cellIndex(cell: HeatmapCell): number {
    return this.cells().findIndex(c => c.date === cell.date);
  }

  setFocus(cell: HeatmapCell | null): void {
    if (!cell) return;
    const i = this.cellIndex(cell);
    if (i >= 0) this.focusIndex.set(i);
  }

  clearFocus(): void {
    this.focusIndex.set(null);
  }

  cellColor(cell: HeatmapCell): string {
    if (cell.isEmpty || cell.pnl === 0) return 'rgba(255,255,255,0.03)';
    const intensity = Math.min(1, Math.abs(cell.pnl) / this.maxAbsPnl());
    const alpha = 0.12 + intensity * 0.75;
    if (cell.pnl > 0) return `rgba(57,255,20,${alpha.toFixed(2)})`;
    return `rgba(255,61,87,${alpha.toFixed(2)})`;
  }

  cellIntensity(cell: HeatmapCell): number {
    if (cell.isEmpty || cell.pnl === 0) return 0;
    return Math.min(1, Math.abs(cell.pnl) / this.maxAbsPnl());
  }

  readonly currency = computed<string>(() => this.trading.overview()?.currency ?? 'USD');

  /** Compact P&L format for in-cell text: +1.4k, -612 (no currency, space-constrained). */
  formatCompact(n: number): string {
    if (n === 0) return '';
    const abs = Math.abs(n);
    const sign = n > 0 ? '+' : '−';
    if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}k`;
    return `${sign}${Math.round(abs)}`;
  }

  /** % of peak equity (simple proxy: pnl / equity * 100) */
  focusEquityPct(cell: HeatmapCell): string {
    if (!cell.equity || cell.pnl === 0) return '0.0%';
    const pct = (cell.pnl / cell.equity) * 100;
    return `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%`;
  }

  focusHitRate(cell: HeatmapCell): string {
    if (cell.tradeCount === 0) return '0%';
    return `${Math.round((cell.winCount / cell.tradeCount) * 100)}%`;
  }

  formatMoney(n: number): string {
    return formatMoneyIt(n, this.currency());
  }

  formatFocusDate(iso: string): string {
    if (!iso) return '';
    try {
      const d = new Date(iso + 'T00:00:00Z');
      return d.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
    } catch { return iso; }
  }
}
