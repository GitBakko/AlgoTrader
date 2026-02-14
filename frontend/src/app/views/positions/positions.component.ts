import { Component, ChangeDetectionStrategy, inject, OnInit, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent,
  TableDirective,
  BadgeComponent, ButtonDirective
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { ToastService } from '../../shared/services/toast.service';

@Component({
  selector: 'app-positions',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, CardComponent, CardBodyComponent,
    TableDirective, BadgeComponent, ButtonDirective,
    PriceFormatPipe,
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <div class="d-flex align-items-center gap-2">
        <h5 class="mb-0 fw-semibold">Posizioni</h5>
        <c-badge color="info">{{ positions().length }}</c-badge>
      </div>
      @if (totalPnl() !== 0) {
        <c-badge [color]="totalPnl() >= 0 ? 'success' : 'danger'" class="fs-6">
          P&amp;L: $ {{ totalPnl() >= 0 ? '+' : '' }}{{ totalPnl() | number:'1.2-2' }}
        </c-badge>
      }
    </div>

    <c-card class="mb-4">
      <c-card-body class="p-0">
        @if (positions().length === 0) {
          <div class="text-center py-5 text-body-secondary small">
            Nessuna posizione aperta
          </div>
        } @else {
          <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
            <thead>
              <tr>
                <th>Asset</th>
                <th>Dir</th>
                <th>Size</th>
                <th>Entry</th>
                <th>SL</th>
                <th>TP</th>
                <th>Aperta</th>
                <th class="text-end">P&amp;L (USD)</th>
                <th class="text-end">Azioni</th>
              </tr>
            </thead>
            <tbody>
              @for (pos of positions(); track pos.deal_id) {
                <tr>
                  <td class="fw-semibold">{{ pos.epic }}</td>
                  <td>
                    <c-badge [color]="pos.direction === 'BUY' ? 'success' : 'danger'" class="badge-sm">
                      {{ pos.direction }}
                    </c-badge>
                  </td>
                  <td class="font-monospace">{{ pos.size | number:'1.4-4' }}</td>
                  <td class="font-monospace">{{ pos.entry_price | priceFormat:pos.epic }}</td>
                  <td class="font-monospace">{{ pos.stop_loss != null ? (pos.stop_loss | priceFormat:pos.epic) : '—' }}</td>
                  <td class="font-monospace">{{ pos.take_profit != null ? (pos.take_profit | priceFormat:pos.epic) : '—' }}</td>
                  <td class="text-body-secondary small">{{ formatDate(pos.opened_at) }}</td>
                  <td class="text-end fw-semibold font-monospace"
                      [class.text-success]="pos.current_pnl >= 0"
                      [class.text-danger]="pos.current_pnl < 0">
                    $ {{ pos.current_pnl >= 0 ? '+' : '' }}{{ pos.current_pnl | number:'1.2-2' }}
                  </td>
                  <td class="text-end">
                    <button cButton color="danger" size="sm" (click)="closePosition(pos.deal_id)">
                      Chiudi
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        }
      </c-card-body>
    </c-card>
  `
})
export class PositionsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly toast = inject(ToastService);
  readonly positions = this.trading.positions;

  readonly totalPnl = computed(() =>
    this.positions().reduce((sum, p) => sum + (p.current_pnl ?? 0), 0)
  );

  ngOnInit(): void {
    this.trading.loadPositions();
  }

  closePosition(dealId: string): void {
    this.trading.closePosition(dealId).subscribe({
      next: () => {
        this.toast.success('Posizione chiusa');
        this.trading.loadPositions();
      },
      error: (err) => {
        this.toast.error(err?.error?.error || 'Errore nella chiusura');
      }
    });
  }

  formatDate(iso: string | null): string {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('it-IT', {
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso ?? '—'; }
  }
}
