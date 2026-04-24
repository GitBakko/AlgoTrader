import { Component, ChangeDetectionStrategy, computed, inject, input, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';
import { WebSocketService } from '../../../../core/services/websocket.service';
import { formatMoneyIt } from '../shared/currency.util';

/**
 * Overnight-swap card — replaces the Bybit-funding design (D1:B).
 *
 * Reads `GET /api/markets/{epic}/overnight-swap` via TradingService and
 * renders a ring-viz (|rate| normalized to 0.5%/day full-ring), plus
 * long/short rates, open position direction+size, notional € stimato,
 * weekend triple-swap multiplier, and next 22:00 UTC charge countdown.
 */
@Component({
  selector: 'app-overnight-swap',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './overnight-swap.component.html',
  styleUrl: './overnight-swap.component.scss',
})
export class OvernightSwapComponent {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);

  readonly epic = input<string>('XAUUSD');

  /** Ring radius / circumference constants. */
  readonly RING_RADIUS = 38;
  readonly RING_CIRC = 2 * Math.PI * 38; // ≈ 238.76
  /** Rate magnitude that fills the ring to 100%. */
  private readonly RING_SCALE_PCT = 0.5;

  readonly swap = computed(() => {
    const all = this.trading.overnightSwap();
    return all[this.epic()] ?? null;
  });

  /**
   * Display rate = rate applying to the open direction if a position is
   * open for this epic, otherwise long rate. Sign preserved.
   */
  readonly displayRate = computed<number>(() => {
    const s = this.swap();
    if (!s) return 0;
    const pos = this.openPosition();
    if (pos) {
      return pos.direction === 'SHORT' ? s.short_rate_pct : s.long_rate_pct;
    }
    return s.long_rate_pct;
  });

  readonly ringFillLen = computed<number>(() => {
    const rate = Math.abs(this.displayRate());
    const ratio = Math.min(1, rate / this.RING_SCALE_PCT);
    return ratio * this.RING_CIRC;
  });

  readonly ringGapLen = computed<number>(() => this.RING_CIRC - this.ringFillLen());

  readonly ringColor = computed<string>(() => {
    const r = this.displayRate();
    if (r > 0) return 'var(--mantis-neon)';
    if (r < 0) return 'var(--mantis-loss)';
    return 'var(--mantis-warning)';
  });

  /** First open paper position matching the display epic, if any. */
  readonly openPosition = computed(() => {
    const target = this.epic();
    const positions = this.trading.paperPositions();
    return positions.find(p => p.epic === target) ?? null;
  });

  /** Notional € estimate = size × entry price. */
  readonly notional = computed<number | null>(() => {
    const pos = this.openPosition();
    if (!pos) return null;
    const size = pos.size ?? 0;
    const level = pos.level ?? 0;
    if (!size || !level) return null;
    return size * level;
  });

  /** Swap € per day = rate% × notional. */
  readonly swapPerDay = computed<number | null>(() => {
    const notional = this.notional();
    const rate = this.displayRate();
    if (notional == null) return null;
    return (rate / 100) * notional;
  });

  /**
   * 7d accumulated swap — server-computed via /api/markets/{epic}/swap-accum.
   * Falls back to client-side estimate (swapPerDay × 7) if the endpoint
   * hasn't returned yet or has no data for this epic.
   */
  readonly swap7dAccum = computed<number | null>(() => {
    const byEpic = this.trading.swapAccum();
    const server = byEpic[this.epic()];
    if (server && typeof server.total_accum === 'number') {
      return server.total_accum;
    }
    const daily = this.swapPerDay();
    if (daily == null) return null;
    return daily * 7;
  });

  /** True when the 7d accum comes from the server (vs client estimate). */
  readonly swap7dFromServer = computed<boolean>(() => {
    const byEpic = this.trading.swapAccum();
    return !!byEpic[this.epic()];
  });

  readonly nextChargeCountdown = computed(() => {
    const s = this.swap();
    if (!s?.next_charge_utc) return '—';
    try {
      const diff = new Date(s.next_charge_utc).getTime() - Date.now();
      if (diff <= 0) return 'now';
      const hours = Math.floor(diff / 3600_000);
      const mins  = Math.floor((diff % 3600_000) / 60_000);
      return `${hours}h ${mins}m`;
    } catch {
      return '—';
    }
  });

  constructor() {
    // Reload swap + 7d accum when epic input changes.
    effect(() => {
      const e = this.epic();
      if (e) {
        this.trading.loadOvernightSwap(e);
        this.trading.loadSwapAccum(e, 7);
      }
    });

    // Reload on /ws/markets swap_update for this epic — replaces polling.
    effect(() => {
      const upd = this.ws.lastSwapUpdate();
      const e = this.epic();
      if (upd && e && upd.epic === e) {
        this.trading.loadOvernightSwap(e);
        this.trading.loadSwapAccum(e, 7);
      }
    });
  }

  /** Currency from swap payload (broker-provided per-epic) → fallback overview. */
  readonly currency = computed<string>(() =>
    this.swap()?.currency ?? this.trading.overview()?.currency ?? 'USD',
  );

  formatMoney(n: number): string {
    return formatMoneyIt(n, this.currency());
  }

  formatNotional(n: number): string {
    return formatMoneyIt(n, this.currency(), { signed: false });
  }
}
