import { Component, ChangeDetectionStrategy, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent,
  TableDirective,
  BadgeComponent, ButtonDirective, ProgressComponent, ProgressBarComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { ToastService } from '../../shared/services/toast.service';

@Component({
  selector: 'app-signals',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, CardComponent, CardBodyComponent,
    TableDirective, BadgeComponent,
    ButtonDirective, ProgressComponent, ProgressBarComponent
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3">
      <div class="d-flex align-items-center gap-2">
        <h5 class="mb-0 fw-bold">Segnali</h5>
        <c-badge color="info" class="mantis-badge-animated">{{ signals().length }}</c-badge>
      </div>
      <button cButton color="primary" size="sm" (click)="generateTestSignal()">
        Test Signal
      </button>
    </div>

    <c-card class="mb-4">
      <c-card-body class="p-0">
        @if (signals().length === 0) {
          <div class="empty-state">
            <div class="empty-state__icon">🔔</div>
            <div class="empty-state__text">Nessun segnale generato</div>
            <div class="empty-state__hint">I segnali di trading appariranno qui</div>
          </div>
        } @else {
          <div style="max-height: 600px; overflow-y: auto;">
            <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
              <thead class="position-sticky top-0" style="z-index: 1;">
                <tr>
                  <th>Asset</th>
                  <th>Dir</th>
                  <th>Confidenza</th>
                  <th>Entry</th>
                  <th>SL</th>
                  <th>TP</th>
                  <th>Regime</th>
                  <th>Status</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                @for (sig of signals(); track sig.timestamp + sig.epic) {
                  <tr>
                    <td class="fw-semibold">{{ sig.epic }}</td>
                    <td>
                      <span class="dir-indicator" [class.dir-indicator--buy]="sig.direction === 'BUY'" [class.dir-indicator--sell]="sig.direction === 'SELL'">
                        {{ sig.direction }}
                      </span>
                    </td>
                    <td>
                      <div class="d-flex align-items-center gap-1">
                        <c-progress class="flex-grow-1" style="height: 4px; min-width: 40px;">
                          <c-progress-bar
                            [value]="sig.confidence * 100"
                            [color]="sig.confidence >= 0.5 ? 'success' : 'warning'">
                          </c-progress-bar>
                        </c-progress>
                        <small class="font-monospace">{{ (sig.confidence * 100) | number:'1.0-0' }}%</small>
                      </div>
                    </td>
                    <td class="font-monospace">{{ sig.entry_price | number:'1.2-2' }}</td>
                    <td class="font-monospace">{{ sig.suggested_stop ? (sig.suggested_stop | number:'1.2-2') : '—' }}</td>
                    <td class="font-monospace">{{ sig.suggested_tp ? (sig.suggested_tp | number:'1.2-2') : '—' }}</td>
                    <td>
                      @if (sig.regime) {
                        <c-badge [color]="regimeColor(sig.regime)" class="badge-sm">{{ sig.regime }}</c-badge>
                      } @else {
                        <span class="text-body-secondary">-</span>
                      }
                    </td>
                    <td>
                      <c-badge [color]="statusColor(sig.status)" class="badge-sm">{{ sig.status }}</c-badge>
                    </td>
                    <td class="text-body-secondary small text-nowrap">{{ formatDateTime(sig.timestamp) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </c-card-body>
    </c-card>
  `
})
export class SignalsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly toast = inject(ToastService);
  readonly signals = this.trading.paperSignals;

  ngOnInit(): void {
    this.trading.loadPaperSignals();
  }

  generateTestSignal(): void {
    this.trading.generateSignal('XAUUSD').subscribe({
      next: () => {
        this.toast.success('Segnale test generato');
        this.trading.loadPaperSignals();
      },
      error: () => this.toast.error('Errore generazione segnale')
    });
  }

  directionColor(dir: string): string {
    return dir === 'BUY' ? 'success' : dir === 'SELL' ? 'danger' : 'secondary';
  }

  regimeColor(regime: string): string {
    if (regime.includes('trending')) return 'primary';
    if (regime.includes('ranging')) return 'warning';
    return 'secondary';
  }

  statusColor(status: string): string {
    switch (status) {
      case 'executed': return 'success';
      case 'rejected': case 'exec_failed': return 'danger';
      case 'hold': return 'warning';
      case 'predicted': return 'info';
      default: return 'secondary';
    }
  }

  formatDateTime(iso: string): string {
    if (!iso) return '-';
    try {
      return new Date(iso).toLocaleString('it-IT', {
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso; }
  }
}
