import { Component, ChangeDetectionStrategy, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  TableDirective,
  BadgeComponent, ButtonDirective, ProgressComponent, ProgressBarComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { ToastService } from '../../shared/services/toast.service';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';

@Component({
  selector: 'app-signals',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './signals.component.scss',
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    TableDirective, BadgeComponent,
    ButtonDirective, ProgressComponent, ProgressBarComponent,
    PriceFormatPipe, EpicLogoComponent,
  ],
  template: `
    <c-card class="mb-4 border-top border-top-3 border-top-primary">
      <c-card-header>
        <div class="d-flex align-items-center justify-content-between">
          <div class="d-flex align-items-center gap-2">
            <span class="fw-semibold small text-body-secondary">Segnali di Trading</span>
            <c-badge color="info" class="mantis-badge-animated">{{ signals().length }}</c-badge>
          </div>
          <button cButton color="primary" size="sm" (click)="generateTestSignal()">
            Test Signal
          </button>
        </div>
      </c-card-header>
      <c-card-body class="p-0">
        @if (signals().length === 0) {
          <div class="empty-state">
            <div class="empty-state__icon">🔔</div>
            <div class="empty-state__text">Nessun segnale generato</div>
            <div class="empty-state__hint">I segnali di trading appariranno qui</div>
          </div>
        } @else {
          <div class="signals-scroll-container">
            <div class="table-responsive-mobile">
              <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
                <thead class="signals-sticky-thead">
                  <tr class="text-body-secondary">
                    <th class="fw-semibold small">Asset</th>
                    <th class="fw-semibold small">Dir</th>
                    <th class="fw-semibold small">Confidenza</th>
                    <th class="fw-semibold small d-mobile-none">Entry</th>
                    <th class="fw-semibold small d-mobile-none">SL</th>
                    <th class="fw-semibold small d-mobile-none">TP</th>
                    <th class="fw-semibold small">Regime</th>
                    <th class="fw-semibold small">Status</th>
                    <th class="fw-semibold small d-mobile-none">Data</th>
                  </tr>
                </thead>
                <tbody>
                  @for (sig of signals(); track sig.timestamp + sig.epic) {
                    <tr>
                      <td class="fw-semibold">
                        <div class="d-flex align-items-center gap-2">
                          <app-epic-logo [epic]="sig.epic" [size]="20" />
                          {{ sig.epic }}
                        </div>
                      </td>
                      <td>
                        <span class="dir-indicator" [class.dir-indicator--buy]="sig.direction === 'BUY'" [class.dir-indicator--sell]="sig.direction === 'SELL'">
                          {{ sig.direction }}
                        </span>
                      </td>
                      <td>
                        <div class="d-flex align-items-center gap-1">
                          <c-progress class="flex-grow-1 conf-progress">
                            <c-progress-bar
                              [value]="sig.confidence * 100"
                              [color]="sig.confidence >= 0.5 ? 'success' : 'warning'">
                            </c-progress-bar>
                          </c-progress>
                          <small class="mantis-mono">{{ (sig.confidence * 100) | number:'1.0-0' }}%</small>
                        </div>
                      </td>
                      <td class="mantis-mono d-mobile-none">{{ sig.entry_price | priceFormat:sig.epic }}</td>
                      <td class="mantis-mono d-mobile-none">{{ sig.suggested_stop ? (sig.suggested_stop | priceFormat:sig.epic) : '—' }}</td>
                      <td class="mantis-mono d-mobile-none">{{ sig.suggested_tp ? (sig.suggested_tp | priceFormat:sig.epic) : '—' }}</td>
                      <td>
                        @if (sig.regime) {
                          <c-badge [color]="regimeColor(sig.regime)" class="badge-sm">{{ sig.regime }}</c-badge>
                        } @else {
                          <span class="text-body-secondary">-</span>
                        }
                      </td>
                      <td>
                        <span class="signal-status signal-status--{{ sig.status }}">
                          <span class="signal-status__dot"></span>
                          {{ sig.status }}
                        </span>
                      </td>
                      <td class="text-body-secondary small text-nowrap d-mobile-none">{{ formatDateTime(sig.timestamp) }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
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

  regimeColor(regime: string): string {
    if (regime.includes('trending')) return 'primary';
    if (regime.includes('ranging')) return 'warning';
    return 'secondary';
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
