import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { EpicLogoComponent } from '../../../../shared/components/epic-logo/epic-logo.component';
import type { TradingSignal, PaperPosition } from '../../../../core/models';

/** Filter chip values surfaced in the heatmap header (mocks/SignalsAndFeed.jsx §SignalsPerAsset). */
export type HeatmapFilter = 'all' | 'active' | 'hold';

/**
 * Heatmap cell rendered on the cockpit grid (HANDOFF §3.7 + mock).
 * One per epic in the trading universe; reflects the latest signal per
 * epic + an open-position overlay so the cell can show "live".
 */
export interface HeatmapCell {
  epic: string;
  /** BUY · SELL · HOLD · — (no signal yet for this epic) */
  direction: 'BUY' | 'SELL' | 'HOLD' | '—';
  /** Confidence percent 0..100, null when no signal exists. */
  confidence: number | null;
  /** UI state mapped from signal status + live overlay. */
  state: 'live' | 'executed' | 'rejected' | 'closed' | 'hold' | 'none';
  /** ISO timestamp of the latest signal, or null. */
  ts: string | null;
}

/**
 * Signals Heatmap — center cockpit (HANDOFF §3.7, mock SignalsPerAsset).
 *
 * 3-column grid (one row every 3 assets, 21 cells = 7 rows). Each cell:
 *   ┌──────────────────────────────────────────────────────┐
 *   │ [glyph] EPIC  [DIR badge]  [pulse if active]   conf% │
 *   │ [confidence bar — full width, 2 px]            STATE │
 *   └──────────────────────────────────────────────────────┘
 *
 * Real data only: `signals` (DB endpoint) + `positions` (broker
 * authoritative) — no fixtures, no synthetic placeholders.
 */
@Component({
  selector: 'app-signals-heatmap',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, EpicLogoComponent],
  templateUrl: './signals-heatmap.component.html',
  styleUrls: ['./signals-heatmap.component.scss'],
})
export class SignalsHeatmapComponent {
  /** Universe — fixed asset list from the backend (paperStatus.epics). */
  readonly epics = input.required<readonly string[]>();
  /** Recent signal history sorted DESC by ts (DB endpoint `/api/signals/`). */
  readonly signals = input<TradingSignal[]>([]);
  /** Live broker positions, used to mark cells as "live". */
  readonly positions = input<PaperPosition[]>([]);
  /** Loading shell during the first fetch. */
  readonly loading = input<boolean>(false);

  readonly cellClicked = output<HeatmapCell>();

  readonly filter = signal<HeatmapFilter>('all');

  /** Static filter chips — frozen so each render reuses the same array
   *  reference (avoids re-running `@for` track on every CD pass). */
  readonly filterChips: readonly { id: HeatmapFilter; label: string }[] = [
    { id: 'all',    label: 'ALL' },
    { id: 'active', label: 'ACTIVE' },
    { id: 'hold',   label: 'HOLD' },
  ];

  /** Indexed by epic for quick lookup (latest signal per epic). */
  private readonly latestByEpic = computed<Record<string, TradingSignal>>(() => {
    const map: Record<string, TradingSignal> = {};
    for (const sig of this.signals()) {
      if (!sig.epic || !sig.timestamp) continue;
      const cur = map[sig.epic];
      if (!cur || cur.timestamp < sig.timestamp) {
        map[sig.epic] = sig;
      }
    }
    return map;
  });

  /** Set of epics with an open position right now (state="live" overlay). */
  private readonly liveEpics = computed<Set<string>>(() => {
    const set = new Set<string>();
    for (const p of this.positions()) {
      if (p.epic) set.add(p.epic);
    }
    return set;
  });

  /** Full cell list driven by the universe — always one cell per epic. */
  readonly allCells = computed<HeatmapCell[]>(() => {
    const universe = this.epics();
    const latest = this.latestByEpic();
    const live = this.liveEpics();
    return universe.map((epic) => {
      const sig = latest[epic] ?? null;
      const direction = (sig?.direction as HeatmapCell['direction']) ?? '—';
      const confidence = sig ? Math.round((sig.confidence ?? 0) * 100) : null;
      let state: HeatmapCell['state'] = 'none';
      if (live.has(epic)) {
        state = 'live';
      } else if (sig) {
        const status = (sig.status ?? '').toUpperCase();
        if (status === 'EXECUTED') state = 'executed';
        else if (status === 'REJECTED') state = 'rejected';
        else if (status === 'CLOSED') state = 'closed';
        else if (direction === 'HOLD') state = 'hold';
        else state = 'executed';
      }
      return {
        epic,
        direction,
        confidence,
        state,
        ts: sig?.timestamp ?? null,
      };
    });
  });

  /** Visible cells after the active filter is applied. */
  readonly cells = computed<HeatmapCell[]>(() => {
    const f = this.filter();
    if (f === 'all') return this.allCells();
    if (f === 'active') {
      return this.allCells().filter((c) =>
        c.state === 'executed' || c.state === 'rejected' || c.state === 'live' || c.state === 'closed',
      );
    }
    return this.allCells().filter((c) => c.state === f);
  });

  setFilter(f: HeatmapFilter): void {
    this.filter.set(f);
  }

  onCellClick(cell: HeatmapCell): void {
    this.cellClicked.emit(cell);
  }

  /** Bar tone matches the mock: green ≥50 · amber ≥30 · neutral below. */
  confidenceTone(conf: number | null): 'high' | 'mid' | 'low' | 'none' {
    if (conf === null) return 'none';
    if (conf >= 50) return 'high';
    if (conf >= 30) return 'mid';
    return 'low';
  }
}
