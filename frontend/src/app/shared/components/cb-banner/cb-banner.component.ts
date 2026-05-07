import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { IconDirective } from '@coreui/icons-angular';
import { TradingService } from '../../../core/services/trading.service';
import { ConfirmDialogService } from '../../services/confirm-dialog.service';
import { ToastService } from '../../services/toast.service';

interface CbEntry {
  readonly key: string;
  readonly label: string;
  readonly icon: string;
  readonly reason: string;
}

const CB_TYPE_MAP: Record<string, { label: string; icon: string }> = {
  daily_loss:         { label: 'Perdita Giornaliera', icon: 'cilArrowBottom' },
  consecutive_losses: { label: 'Perdite Consecutive', icon: 'cilChartLine' },
  max_positions:      { label: 'Max Posizioni',       icon: 'cilLayers' },
  slippage_anomaly:   { label: 'Anomalia Slippage',   icon: 'cilBolt' },
  heartbeat_timeout:  { label: 'Timeout Heartbeat',   icon: 'cilReload' },
  volatility_spike:   { label: 'Spike Volatilità',    icon: 'cilChartPie' },
};

/**
 * Circuit Breaker banner — visible whenever the paper-loop reports any
 * tripped breaker. Renders the list with Italian labels + a reset button
 * that hits POST /api/trading/reset-circuit-breakers via TradingService.
 *
 * Mount once per page (dashboard-v2, paper-trading). The component reads
 * the tripped state directly from TradingService so no inputs are needed.
 */
@Component({
  selector: 'app-cb-banner',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, IconDirective],
  templateUrl: './cb-banner.component.html',
  styleUrls: ['./cb-banner.component.scss'],
})
export class CbBannerComponent {
  private readonly trading = inject(TradingService);
  private readonly confirmDialog = inject(ConfirmDialogService);
  private readonly toast = inject(ToastService);
  private readonly destroyRef = inject(DestroyRef);

  readonly resetting = signal(false);

  readonly entries = computed<CbEntry[]>(() => {
    const raw = this.trading.paperStatus()?.circuit_breakers_tripped;
    if (!raw || Array.isArray(raw)) return [];
    return Object.entries(raw).map(([key, reason]) => ({
      key,
      label: CB_TYPE_MAP[key]?.label ?? key,
      icon: CB_TYPE_MAP[key]?.icon ?? 'cilShieldAlt',
      reason: String(reason),
    }));
  });

  readonly visible = computed(() => this.entries().length > 0);

  async onReset(): Promise<void> {
    const confirmed = await this.confirmDialog.confirm({
      title: 'Reset Circuit Breakers',
      message: 'Resettare tutti i circuit breakers e i contatori perdite per-asset?',
      confirmText: 'Reset',
      cancelText: 'Annulla',
      color: 'warning',
    });
    if (!confirmed) return;

    this.resetting.set(true);
    this.trading
      .resetCircuitBreakers()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.toast.success(data.message ?? 'Circuit breakers resettati');
          this.resetting.set(false);
          this.trading.loadPaperStatus();
        },
        error: (err) => {
          this.toast.error(err?.error?.error ?? 'Reset circuit breakers fallito');
          this.resetting.set(false);
        },
      });
  }
}
