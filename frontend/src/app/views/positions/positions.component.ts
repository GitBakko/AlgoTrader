import { Component, ChangeDetectionStrategy, inject, OnInit, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent,
  TableDirective,
  BadgeComponent, ButtonDirective
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { ToastService } from '../../shared/services/toast.service';
import { getEpicSymbol } from '../../shared/constants/epic-symbols';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';

@Component({
  selector: 'app-positions',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, CardComponent, CardBodyComponent,
    TableDirective, BadgeComponent, ButtonDirective,
    PriceFormatPipe, EpicLogoComponent,
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3">
      <div class="d-flex align-items-center gap-2">
        <h5 class="mb-0 fw-bold">Posizioni</h5>
        <c-badge color="info" class="mantis-badge-animated">{{ livePositions().length }}</c-badge>
      </div>
      @if (totalPnl() !== 0) {
        <span class="mantis-kpi" [class.text-success]="totalPnl() >= 0" [class.text-danger]="totalPnl() < 0" style="font-size: 1.125rem;">
          $ {{ totalPnl() >= 0 ? '+' : '' }}{{ totalPnl() | number:'1.2-2' }}
        </span>
      }
    </div>

    <c-card class="mb-4">
      <c-card-body class="p-0">
        @if (livePositions().length === 0) {
          <div class="empty-state">
            <div class="empty-state__icon">📊</div>
            <div class="empty-state__text">Nessuna posizione aperta</div>
            <div class="empty-state__hint">Le posizioni aperte appariranno qui</div>
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
              @for (pos of livePositions(); track pos.deal_id) {
                <tr>
                  <td class="fw-semibold">
                    <div class="d-flex align-items-center gap-2">
                      <app-epic-logo [epic]="pos.epic" [size]="24" [rounded]="true" />
                      <span class="me-1" style="font-size: 1.1em;">{{ getSymbol(pos.epic) }}</span>
                      {{ pos.epic }}
                    </div>
                  </td>
                  <td>
                    <span class="dir-indicator" [class.dir-indicator--buy]="pos.direction === 'BUY'" [class.dir-indicator--sell]="pos.direction === 'SELL'">
                      {{ pos.direction }}
                    </span>
                  </td>
                  <td class="font-monospace">{{ pos.size | number:'1.4-4' }}</td>
                  <td class="font-monospace">{{ pos.level | priceFormat:pos.epic }}</td>
                  <td class="font-monospace">{{ pos.stop_level != null ? (pos.stop_level | priceFormat:pos.epic) : '—' }}</td>
                  <td class="font-monospace">{{ pos.profit_level != null ? (pos.profit_level | priceFormat:pos.epic) : '—' }}</td>
                  <td class="text-body-secondary small">{{ formatDate(pos.opened_at) }}</td>
                  <td class="text-end fw-semibold font-monospace"
                      [class.text-success]="pos.live_pnl >= 0"
                      [class.text-danger]="pos.live_pnl < 0">
                    $ {{ pos.live_pnl >= 0 ? '+' : '' }}{{ pos.live_pnl | number:'1.2-2' }}
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
  private readonly ws = inject(WebSocketService);
  private readonly toast = inject(ToastService);
  readonly positions = this.trading.paperPositions;

  // Calculate live P&L using WebSocket prices
  readonly livePositions = computed(() => {
    const positions = this.positions();
    const prices = this.ws.prices();
    return positions.map(pos => {
      const tick = prices[pos.epic];
      if (!tick) return { ...pos, live_pnl: 0 };
      const currentPrice = pos.direction === 'BUY' ? tick.bid : tick.offer;
      const diff = pos.direction === 'BUY' ? currentPrice - pos.level : pos.level - currentPrice;
      return { ...pos, live_pnl: Math.round(diff * pos.size * 100) / 100 };
    });
  });

  readonly totalPnl = computed(() =>
    this.livePositions().reduce((sum, p) => sum + (p.live_pnl ?? 0), 0)
  );

  // Get symbol for EPIC display
  getSymbol = getEpicSymbol;

  ngOnInit(): void {
    this.trading.loadPaperPositions();
  }

  closePosition(dealId: string): void {
    this.trading.closePosition(dealId).subscribe({
      next: () => {
        this.toast.success('Posizione chiusa');
        this.trading.loadPaperPositions();
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
