import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DecimalPipe } from '@angular/common';
import { EpicLogoComponent } from '../../../../shared/components/epic-logo/epic-logo.component';
import type { FeedEvent } from '../../../../core/models';

/**
 * Live Feed Timeline — sticky right rail of the cockpit (HANDOFF §3.8 +
 * mocks/SignalsAndFeed.jsx §FeedSegnali).
 *
 * Vertical event stream sourced from `/api/trading/events` (signals,
 * positions, notifications) merged by the backend. Each row mirrors the
 * mock layout: `[time] [bullet on rail] [glyph+ticker] [strategy chip]
 * [direction badge] [conf%] [price] [detail]`. The header surfaces
 * EXEC / REJ / HOLD chip counters plus a LIVE label.
 *
 * Strict invariant: the data is real backend rows only. Empty input
 * yields the empty state — never a synthetic stream.
 */
@Component({
  selector: 'app-live-feed-timeline',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DecimalPipe, EpicLogoComponent],
  templateUrl: './live-feed-timeline.component.html',
  styleUrls: ['./live-feed-timeline.component.scss'],
})
export class LiveFeedTimelineComponent {
  readonly events = input<FeedEvent[]>([]);
  readonly loading = input<boolean>(false);
  /** Default trims to the most recent N rows; backend usually returns 50. */
  readonly maxRows = input<number>(50);

  readonly eventClicked = output<FeedEvent>();

  readonly visibleEvents = computed<FeedEvent[]>(() => {
    const list = this.events();
    if (!list.length) return [];
    return list.slice(0, this.maxRows());
  });

  /** Counter chips in the header (mock spec: EXEC · REJ · HOLD). */
  readonly counts = computed<{ exec: number; rej: number; hold: number }>(() => {
    const c = { exec: 0, rej: 0, hold: 0 };
    for (const e of this.visibleEvents()) {
      if (e.kind === 'signal-emit' || e.kind === 'position-open') c.exec += 1;
      else if (e.kind === 'signal-reject') c.rej += 1;
      else if (e.kind === 'signal-pending') c.hold += 1;
    }
    return c;
  });

  readonly skeletonRows = [0, 1, 2, 3, 4, 5];

  onEventClick(event: FeedEvent): void {
    this.eventClicked.emit(event);
  }

  /** State token used to color bullets, badges and row tint, derived from
   *  the event kind so the SCSS doesn't have to special-case every kind. */
  stateOf(event: FeedEvent): 'executed' | 'rejected' | 'hold' | 'closed' | 'error' | 'info' {
    switch (event.kind) {
      case 'signal-emit':
      case 'position-open':
        return 'executed';
      case 'signal-reject':
        return 'rejected';
      case 'signal-pending':
      case 'iteration':
        return 'hold';
      case 'position-close':
        return 'closed';
      case 'error':
        return 'error';
      default:
        return 'info';
    }
  }

  /** Treat `executed` and `rejected` as "important" — get bullet glow + bg tint. */
  isImportant(event: FeedEvent): boolean {
    const s = this.stateOf(event);
    return s === 'executed' || s === 'rejected' || s === 'error';
  }

  formatTime(ts: string | null): string {
    if (!ts) return '--:--:--';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return '--:--:--';
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  /** Confidence color tone (mock thresholds: ≥50 neon, ≥30 amber). */
  confidenceTone(conf: number | null | undefined): 'high' | 'mid' | 'low' | 'none' {
    if (conf === null || conf === undefined) return 'none';
    if (conf >= 50) return 'high';
    if (conf >= 30) return 'mid';
    return 'low';
  }

  /** Best-effort decimals for the price column based on magnitude. */
  pricePrecision(price: number | null | undefined): string {
    if (price === null || price === undefined || !Number.isFinite(price)) return '1.0-0';
    const abs = Math.abs(price);
    if (abs >= 1000) return '1.1-2';
    if (abs >= 10) return '1.2-3';
    if (abs >= 1) return '1.4-5';
    return '1.5-6';
  }
}
