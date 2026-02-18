import { Component, ChangeDetectionStrategy, inject, OnInit, OnDestroy, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  TableDirective,
  BadgeComponent, ButtonDirective,
  TooltipDirective
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { ToastService } from '../../shared/services/toast.service';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';

@Component({
  selector: 'app-positions',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './positions.component.scss',
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    TableDirective, BadgeComponent, ButtonDirective, TooltipDirective,
    PriceFormatPipe, EpicLogoComponent,
  ],
  template: `
    <c-card class="mb-4 border-top border-top-3 border-top-primary">
      <c-card-header>
        <div class="d-flex align-items-center justify-content-between">
          <div class="d-flex align-items-center gap-2">
            <span class="fw-semibold small text-body-secondary">Posizioni Aperte</span>
            <c-badge color="info" class="mantis-badge-animated">{{ livePositions().length }}</c-badge>
          </div>
          @if (totalPnl() !== 0) {
            <span class="pos-total-pnl"
                  [class.text-success]="totalPnl() >= 0"
                  [class.text-danger]="totalPnl() < 0">
              $ {{ totalPnl() >= 0 ? '+' : '' }}{{ totalPnl() | number:'1.2-2' }}
            </span>
          }
        </div>
      </c-card-header>
      <c-card-body class="p-0">
        @if (livePositions().length === 0) {
          <div class="empty-state">
            <div class="empty-state__icon">📊</div>
            <div class="empty-state__text">Nessuna posizione aperta</div>
            <div class="empty-state__hint">Le posizioni aperte appariranno qui</div>
          </div>
        } @else {
          <!-- Mobile: Card-based layout -->
          <div class="d-block d-md-none p-3">
            @for (pos of livePositions(); track pos.deal_id) {
              <div class="pos-mobile-card mb-2">
                <div class="d-flex justify-content-between align-items-start mb-2">
                  <div class="d-flex align-items-center gap-2">
                    <app-epic-logo [epic]="pos.epic" [size]="28" [rounded]="true" />
                    <div>
                      <div class="fw-semibold">{{ pos.epic }}</div>
                      <span class="dir-indicator dir-indicator--sm"
                            [class.dir-indicator--buy]="pos.direction === 'BUY'"
                            [class.dir-indicator--sell]="pos.direction === 'SELL'">
                        {{ pos.direction }}
                      </span>
                    </div>
                  </div>
                  <div class="text-end">
                    <div class="fw-semibold mantis-mono"
                         [class.text-success]="pos.live_pnl >= 0"
                         [class.text-danger]="pos.live_pnl < 0">
                      $ {{ pos.live_pnl >= 0 ? '+' : '' }}{{ pos.live_pnl | number:'1.2-2' }}
                    </div>
                    <div class="text-body-secondary small mantis-mono">
                      Entry: {{ pos.level | priceFormat:pos.epic }}
                    </div>
                  </div>
                </div>
                <div class="d-flex justify-content-between align-items-center">
                  <div class="d-flex gap-2 small text-body-secondary">
                    @if (pos.stop_level != null) {
                      <span>SL: <span class="mantis-mono">{{ pos.stop_level | priceFormat:pos.epic }}</span></span>
                    }
                    @if (pos.trailing_stop_phase) {
                      <span class="trailing-phase trailing-phase--sm"
                            [class.trailing-phase--initial]="pos.trailing_stop_phase === 'INITIAL'"
                            [class.trailing-phase--breakeven]="pos.trailing_stop_phase === 'BREAKEVEN'"
                            [class.trailing-phase--tp1_lock]="pos.trailing_stop_phase === 'TP1_LOCK'"
                            [class.trailing-phase--trailing]="pos.trailing_stop_phase === 'TRAILING'">
                        {{ pos.trailing_stop_phase }}
                      </span>
                    }
                  </div>
                  <button cButton color="danger" size="sm" (click)="closePosition(pos.deal_id)">
                    Chiudi
                  </button>
                </div>
              </div>
            }
          </div>

          <!-- Desktop: Table layout -->
          <div class="d-none d-md-block table-responsive-mobile">
            <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
              <thead>
                <tr class="text-body-secondary">
                  <th class="fw-semibold small">Asset</th>
                  <th class="fw-semibold small">Dir</th>
                  <th class="fw-semibold small">Size</th>
                  <th class="fw-semibold small">Entry</th>
                  <th class="fw-semibold small">SL</th>
                  <th class="fw-semibold small">TP</th>
                  <th class="fw-semibold small">Risk</th>
                  <th class="fw-semibold small">Trailing</th>
                  <th class="fw-semibold small">Aperta</th>
                  <th class="fw-semibold small text-end">P&amp;L</th>
                  <th class="fw-semibold small text-end">Azioni</th>
                </tr>
              </thead>
              <tbody>
                @for (pos of livePositions(); track pos.deal_id) {
                  <tr>
                    <td class="fw-semibold">
                      <div class="d-flex align-items-center gap-2">
                        <app-epic-logo [epic]="pos.epic" [size]="24" [rounded]="true" />
                        {{ pos.epic }}
                      </div>
                    </td>
                    <td>
                      <span class="dir-indicator" [class.dir-indicator--buy]="pos.direction === 'BUY'" [class.dir-indicator--sell]="pos.direction === 'SELL'">
                        {{ pos.direction }}
                      </span>
                    </td>
                    <td class="mantis-mono">{{ pos.size | number:'1.4-4' }}</td>
                    <td class="mantis-mono">{{ pos.level | priceFormat:pos.epic }}</td>
                    <td class="mantis-mono">{{ pos.stop_level != null ? (pos.stop_level | priceFormat:pos.epic) : '—' }}</td>
                    <td class="mantis-mono">{{ pos.profit_level != null ? (pos.profit_level | priceFormat:pos.epic) : '—' }}</td>
                    <td>
                      @if (pos.risk_managed_locally) {
                        <span class="risk-badge risk-badge--slim risk-badge--local"
                              cTooltip="SL/TP gestito localmente dal sistema MANTIS (non dal broker)">
                          LOCAL
                        </span>
                      } @else if (pos.stop_level != null) {
                        <span class="risk-badge risk-badge--slim risk-badge--broker"
                              cTooltip="SL/TP gestito dal broker Capital.com">
                          BROKER
                        </span>
                      } @else {
                        <span class="risk-badge risk-badge--slim risk-badge--none"
                              cTooltip="Nessun risk management attivo!">
                          NONE
                        </span>
                      }
                    </td>
                    <td>
                      @if (pos.trailing_stop_phase) {
                        <span class="trailing-phase"
                              [class.trailing-phase--initial]="pos.trailing_stop_phase === 'INITIAL'"
                              [class.trailing-phase--breakeven]="pos.trailing_stop_phase === 'BREAKEVEN'"
                              [class.trailing-phase--tp1_lock]="pos.trailing_stop_phase === 'TP1_LOCK'"
                              [class.trailing-phase--trailing]="pos.trailing_stop_phase === 'TRAILING'"
                              [cTooltip]="trailingPhaseTooltip(pos.trailing_stop_phase)">
                          {{ pos.trailing_stop_phase }}
                        </span>
                      } @else {
                        <span class="text-body-secondary small">—</span>
                      }
                    </td>
                    <td class="text-body-secondary small">{{ formatDate(pos.opened_at) }}</td>
                    <td class="text-end fw-semibold mantis-mono"
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
          </div>
        }
      </c-card-body>
    </c-card>
  `
})
export class PositionsComponent implements OnInit, OnDestroy {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  private readonly toast = inject(ToastService);
  private pollTimer: ReturnType<typeof setInterval> | null = null;
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

  ngOnInit(): void {
    this.trading.loadPaperPositions();
    this.ws.connectPrices();
    // Auto-refresh positions every 10 seconds
    this.pollTimer = setInterval(() => {
      this.trading.loadPaperPositions();
    }, 10_000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
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

  trailingPhaseTooltip(phase: string): string {
    switch (phase) {
      case 'INITIAL': return 'Stop loss iniziale, non ancora spostato';
      case 'BREAKEVEN': return 'Stop spostato a breakeven (entry price)';
      case 'TP1_LOCK': return 'Profitto parziale preso, stop bloccato a TP1';
      case 'TRAILING': return 'Trailing stop attivo, segue il prezzo';
      default: return phase;
    }
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
