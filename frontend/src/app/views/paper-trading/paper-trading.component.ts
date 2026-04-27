import { ChangeDetectionStrategy, Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { CockpitHeaderComponent, type CockpitMode, type CockpitState } from '../../shared/components/cockpit-header/cockpit-header.component';
import { TradingService } from '../../core/services/trading.service';
import { ToastService } from '../../shared/services/toast.service';
import { ConfirmDialogService } from '../../shared/services/confirm-dialog.service';

/**
 * Paper Trading v2 — cockpit shell (PR 1 · chrome only).
 *
 * Layout: 3-col grid (260px · 1fr · 360px) with cockpit header on top.
 * Slots are placeholders until PR 2 (left rail), PR 3 (center hero),
 * PR 4 (telemetry) and PR 5 (drawer + skeletons) land.
 *
 * Source: docs/handoff/paper-trading/HANDOFF.md §1, §10.
 */
@Component({
  selector: 'app-paper-trading',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, CockpitHeaderComponent],
  templateUrl: './paper-trading.component.html',
  styleUrls: ['./paper-trading.component.scss'],
  host: {
    'data-screen-label': '02 Paper Trading',
  },
})
export class PaperTradingComponent implements OnInit, OnDestroy {
  private readonly trading = inject(TradingService);
  private readonly toast = inject(ToastService);
  private readonly confirmDialog = inject(ConfirmDialogService);

  readonly stopBusy = signal(false);
  readonly emergencyBusy = signal(false);

  readonly status = this.trading.paperStatus;

  readonly state = computed<CockpitState>(() => {
    const s = this.status();
    if (!s) return 'IDLE';
    if ((s.error_count ?? 0) > 0) return 'ERROR';
    return s.running ? 'RUNNING' : 'IDLE';
  });

  readonly mode = computed<CockpitMode>(() => {
    const raw = this.status()?.execution_mode ?? 'DEMO';
    return (raw === 'LIVE' || raw === 'PAPER') ? raw : 'DEMO';
  });

  readonly lastTickAgo = computed<number | null>(() => {
    const iso = this.status()?.last_run;
    if (!iso) return null;
    const ts = Date.parse(iso);
    if (Number.isNaN(ts)) return null;
    return Math.max(0, (Date.now() - ts) / 1000);
  });

  /** Build/footer label — extended in PR 5. */
  readonly buildTag = signal<string>('mantis · v2 shell');

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.trading.loadPaperStatus();
    this.pollTimer = setInterval(() => this.trading.loadPaperStatus(), 10_000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  async onStop(): Promise<void> {
    if (this.stopBusy()) return;
    const running = this.status()?.running === true;
    const confirmed = await this.confirmDialog.confirm({
      title: running ? 'Stop Paper Trading' : 'Start Paper Trading',
      message: running
        ? 'Vuoi fermare il loop di paper trading? Le posizioni aperte restano sul broker.'
        : 'Avviare il loop di paper trading?',
      confirmText: running ? 'Stop' : 'Start',
      cancelText: 'Annulla',
      color: running ? 'warning' : 'primary',
    });
    if (!confirmed) return;

    this.stopBusy.set(true);
    const action$ = running ? this.trading.stopPaperTrading() : this.trading.startPaperTrading();
    action$.subscribe({
      next: (data) => {
        this.toast.success(data.message);
        this.stopBusy.set(false);
        this.trading.loadPaperStatus();
      },
      error: (err) => {
        this.toast.error(err?.error?.error ?? 'Operazione fallita');
        this.stopBusy.set(false);
      },
    });
  }

  async onEmergency(): Promise<void> {
    if (this.emergencyBusy()) return;
    const confirmed = await this.confirmDialog.confirm({
      title: 'Emergency Stop',
      message: 'ATTENZIONE: chiude TUTTE le posizioni aperte e ferma il loop. Procedere?',
      confirmText: 'Ferma tutto',
      cancelText: 'Annulla',
      color: 'danger',
    });
    if (!confirmed) return;

    this.emergencyBusy.set(true);
    this.trading.emergencyStop().subscribe({
      next: (data) => {
        this.toast.success(data.message);
        this.emergencyBusy.set(false);
        this.trading.loadPaperStatus();
      },
      error: (err) => {
        this.toast.error(err?.error?.error ?? 'Emergency stop fallito');
        this.emergencyBusy.set(false);
      },
    });
  }
}
