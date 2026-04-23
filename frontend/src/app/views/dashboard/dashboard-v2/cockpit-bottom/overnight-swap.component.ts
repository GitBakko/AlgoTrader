import { Component, ChangeDetectionStrategy, computed, inject, input, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TradingService } from '../../../../core/services/trading.service';

/**
 * Overnight-swap card — replaces the Bybit-funding design (D1:B).
 *
 * Reads `GET /api/markets/{epic}/overnight-swap` via TradingService and
 * renders the daily long/short rollover rates, weekend triple-swap
 * multiplier, and next 22:00 UTC charge time.
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

  readonly epic = input<string>('XAUUSD');

  readonly swap = computed(() => {
    const all = this.trading.overnightSwap();
    return all[this.epic()] ?? null;
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
    // Reload swap when epic input changes.
    effect(() => {
      const e = this.epic();
      if (e) this.trading.loadOvernightSwap(e);
    });
  }
}
