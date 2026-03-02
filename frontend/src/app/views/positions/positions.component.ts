import {
  Component, ChangeDetectionStrategy, inject, OnInit, OnDestroy,
  computed, signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  TableDirective, ButtonDirective, TooltipDirective,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { ToastService } from '../../shared/services/toast.service';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';
import { LoadingButtonComponent } from '../../shared/components/loading-button/loading-button.component';
import { TRADABLE_ASSETS } from '../../shared/constants/assets';

type Tab = 'open' | 'history';

@Component({
  selector: 'app-positions',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './positions.component.scss',
  imports: [
    CommonModule, FormsModule,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    TableDirective, ButtonDirective, TooltipDirective,
    PriceFormatPipe, EpicLogoComponent, LoadingButtonComponent,
    IconDirective,
  ],
  template: `
    <!-- Tab bar -->
    <div class="pos-tabs mb-3">
      <button class="pos-tab" [class.pos-tab--active]="activeTab() === 'open'"
              (click)="switchTab('open')">
        Aperte
        <span class="pos-tab__count">{{ livePositions().length }}</span>
      </button>
      <button class="pos-tab" [class.pos-tab--active]="activeTab() === 'history'"
              (click)="switchTab('history')">
        Storico
        @if (trading.closedTotal() > 0) {
          <span class="pos-tab__count">{{ trading.closedTotal() }}</span>
        }
      </button>
    </div>

    <!-- ═══════════ TAB: OPEN POSITIONS ═══════════ -->
    @if (activeTab() === 'open') {
      <c-card class="mb-4 border-top border-top-3 border-top-primary animate-in">
        <c-card-header>
          <div class="d-flex align-items-center justify-content-between">
            <span class="fw-semibold small text-body-secondary">Posizioni Aperte</span>
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
            <!-- Mobile cards -->
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
                        Live: {{ pos.current_price ? (pos.current_price | priceFormat:pos.epic) : '—' }}
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
                    <app-loading-button color="danger" size="sm"
                                        [loading]="closingDealId() === pos.deal_id"
                                        (clicked)="closePosition(pos.deal_id)">
                      Chiudi
                    </app-loading-button>
                  </div>
                </div>
              }
            </div>

            <!-- Desktop table -->
            <div class="d-none d-md-block table-responsive-mobile">
              <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
                <thead>
                  <tr class="text-body-secondary">
                    <th class="fw-semibold small">Asset</th>
                    <th class="fw-semibold small">Dir</th>
                    <th class="fw-semibold small">Size</th>
                    <th class="fw-semibold small">Entry</th>
                    <th class="fw-semibold small">Live</th>
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
                      <td class="mantis-mono"
                          [class.text-success]="pos.live_pnl > 0"
                          [class.text-danger]="pos.live_pnl < 0">
                        {{ pos.current_price ? (pos.current_price | priceFormat:pos.epic) : '—' }}
                      </td>
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
                        <app-loading-button color="danger" size="sm"
                                            [loading]="closingDealId() === pos.deal_id"
                                            (clicked)="closePosition(pos.deal_id)">
                          Chiudi
                        </app-loading-button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </c-card-body>
      </c-card>
    }

    <!-- ═══════════ TAB: HISTORY ═══════════ -->
    @if (activeTab() === 'history') {
      <!-- Filters -->
      <c-card class="mb-3 border-top border-top-3 border-top-primary">
        <c-card-body class="py-2 px-3">
          <div class="d-flex flex-wrap align-items-center gap-2">
            <select class="form-select form-select-sm pos-filter-select"
                    [ngModel]="filterEpic()" (ngModelChange)="filterEpic.set($event); loadHistory()">
              <option value="">Tutti gli asset</option>
              @for (a of assets; track a) {
                <option [value]="a">{{ a }}</option>
              }
            </select>
            <select class="form-select form-select-sm pos-filter-select"
                    [ngModel]="filterReason()" (ngModelChange)="filterReason.set($event); loadHistory()">
              <option value="">Tutte le chiusure</option>
              <option value="SL">Stop Loss</option>
              <option value="TP">Take Profit</option>
              <option value="MANUAL">Manuale</option>
              <option value="EXTERNAL">Esterna</option>
            </select>
            <input type="date" class="form-control form-control-sm pos-filter-date"
                   [ngModel]="filterFrom()" (ngModelChange)="filterFrom.set($event); loadHistory()" />
            <input type="date" class="form-control form-control-sm pos-filter-date"
                   [ngModel]="filterTo()" (ngModelChange)="filterTo.set($event); loadHistory()" />
          </div>
        </c-card-body>
      </c-card>

      <!-- Aggregates KPI row -->
      @if (trading.closedAggregates(); as agg) {
        <div class="row g-3 mb-3">
          <div class="col-6 col-xl-3 animate-in stagger-1">
            <c-card class="h-100 border-top border-top-3 border-top-primary">
              <c-card-body class="p-3">
                <div class="text-body-secondary small mb-1">P&amp;L Totale</div>
                <div class="mantis-kpi fs-5"
                     [class.text-success]="agg.total_pnl >= 0"
                     [class.text-danger]="agg.total_pnl < 0">
                  $ {{ agg.total_pnl >= 0 ? '+' : '' }}{{ agg.total_pnl | number:'1.2-2' }}
                </div>
              </c-card-body>
            </c-card>
          </div>
          <div class="col-6 col-xl-3 animate-in stagger-2">
            <c-card class="h-100 border-top border-top-3 border-top-primary">
              <c-card-body class="p-3">
                <div class="text-body-secondary small mb-1">Win Rate</div>
                <div class="mantis-kpi fs-5">
                  {{ agg.win_rate | percent:'1.1-1' }}
                  <span class="text-body-secondary small ms-1">
                    ({{ agg.win_count }}W / {{ agg.loss_count }}L)
                  </span>
                </div>
              </c-card-body>
            </c-card>
          </div>
          <div class="col-6 col-xl-3 animate-in stagger-3">
            <c-card class="h-100 border-top border-top-3 border-top-primary">
              <c-card-body class="p-3">
                <div class="text-body-secondary small mb-1">Avg Win</div>
                <div class="mantis-kpi fs-5 text-success">
                  $ +{{ agg.avg_win | number:'1.2-2' }}
                </div>
              </c-card-body>
            </c-card>
          </div>
          <div class="col-6 col-xl-3 animate-in stagger-4">
            <c-card class="h-100 border-top border-top-3 border-top-primary">
              <c-card-body class="p-3">
                <div class="text-body-secondary small mb-1">Avg Loss</div>
                <div class="mantis-kpi fs-5 text-danger">
                  $ {{ agg.avg_loss | number:'1.2-2' }}
                </div>
              </c-card-body>
            </c-card>
          </div>
        </div>
      }

      <!-- Closed positions table -->
      <c-card class="mb-4 border-top border-top-3 border-top-primary animate-in">
        <c-card-header class="d-flex align-items-center justify-content-between">
          <span class="fw-semibold small text-body-secondary">
            Storico Posizioni Chiuse
            @if (trading.closedTotal() > 0) {
              <span class="text-body-secondary ms-1">({{ trading.closedTotal() }})</span>
            }
          </span>
          @if (trading.closedPositions().length > 0) {
            <button cButton color="primary" variant="outline" size="sm"
                    [disabled]="exporting()"
                    (click)="exportHistoryCsv()">
              <svg cIcon name="cilCloudDownload" size="sm" class="me-1"></svg>
              {{ exporting() ? 'Esportando...' : 'Esporta CSV' }}
            </button>
          }
        </c-card-header>
        <c-card-body class="p-0">
          @if (trading.closedPositions().length === 0) {
            <div class="empty-state">
              <div class="empty-state__icon">📜</div>
              <div class="empty-state__text">Nessuna posizione chiusa</div>
              <div class="empty-state__hint">Lo storico delle posizioni chiuse apparirà qui</div>
            </div>
          } @else {
            <!-- Mobile cards -->
            <div class="d-block d-md-none p-3">
              @for (pos of trading.closedPositions(); track pos.deal_id) {
                <div class="pos-mobile-card mb-2">
                  <div class="d-flex justify-content-between align-items-start mb-1">
                    <div class="d-flex align-items-center gap-2">
                      <app-epic-logo [epic]="pos.epic" [size]="24" [rounded]="true" />
                      <div>
                        <span class="fw-semibold">{{ pos.epic }}</span>
                        <span class="dir-indicator dir-indicator--sm ms-1"
                              [class.dir-indicator--buy]="pos.direction === 'BUY'"
                              [class.dir-indicator--sell]="pos.direction === 'SELL'">
                          {{ pos.direction }}
                        </span>
                      </div>
                    </div>
                    <div class="mantis-mono fw-semibold"
                         [class.text-success]="(pos.profit_loss ?? 0) >= 0"
                         [class.text-danger]="(pos.profit_loss ?? 0) < 0">
                      $ {{ (pos.profit_loss ?? 0) >= 0 ? '+' : '' }}{{ pos.profit_loss | number:'1.2-2' }}
                    </div>
                  </div>
                  <div class="d-flex justify-content-between small text-body-secondary">
                    <span>
                      <span class="close-reason-badge"
                            [class.close-reason-badge--sl]="pos.close_reason === 'SL'"
                            [class.close-reason-badge--tp]="pos.close_reason === 'TP'"
                            [class.close-reason-badge--manual]="pos.close_reason === 'MANUAL'"
                            [class.close-reason-badge--external]="pos.close_reason === 'EXTERNAL'">
                        {{ pos.close_reason ?? '—' }}
                      </span>
                    </span>
                    <span>{{ formatDate(pos.closed_at) }}</span>
                  </div>
                </div>
              }
            </div>

            <!-- Desktop table -->
            <div class="d-none d-md-block table-responsive-mobile">
              <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
                <thead>
                  <tr class="text-body-secondary">
                    <th class="fw-semibold small">Asset</th>
                    <th class="fw-semibold small">Dir</th>
                    <th class="fw-semibold small">Size</th>
                    <th class="fw-semibold small">Entry</th>
                    <th class="fw-semibold small">Exit</th>
                    <th class="fw-semibold small text-end">P&amp;L</th>
                    <th class="fw-semibold small">Tipo</th>
                    <th class="fw-semibold small">Aperta</th>
                    <th class="fw-semibold small">Chiusa</th>
                    <th class="fw-semibold small">Durata</th>
                  </tr>
                </thead>
                <tbody>
                  @for (pos of trading.closedPositions(); track pos.deal_id) {
                    <tr [class.pnl-row-positive]="(pos.profit_loss ?? 0) > 0"
                        [class.pnl-row-negative]="(pos.profit_loss ?? 0) < 0">
                      <td class="fw-semibold">
                        <div class="d-flex align-items-center gap-2">
                          <app-epic-logo [epic]="pos.epic" [size]="24" [rounded]="true" />
                          {{ pos.epic }}
                        </div>
                      </td>
                      <td>
                        <span class="dir-indicator"
                              [class.dir-indicator--buy]="pos.direction === 'BUY'"
                              [class.dir-indicator--sell]="pos.direction === 'SELL'">
                          {{ pos.direction }}
                        </span>
                      </td>
                      <td class="mantis-mono">{{ pos.size | number:'1.4-4' }}</td>
                      <td class="mantis-mono">{{ pos.entry_price | priceFormat:pos.epic }}</td>
                      <td class="mantis-mono">{{ pos.exit_price != null ? (pos.exit_price | priceFormat:pos.epic) : '—' }}</td>
                      <td class="text-end fw-semibold mantis-mono"
                          [class.text-success]="(pos.profit_loss ?? 0) >= 0"
                          [class.text-danger]="(pos.profit_loss ?? 0) < 0">
                        $ {{ (pos.profit_loss ?? 0) >= 0 ? '+' : '' }}{{ pos.profit_loss | number:'1.2-2' }}
                      </td>
                      <td>
                        <span class="close-reason-badge"
                              [class.close-reason-badge--sl]="pos.close_reason === 'SL'"
                              [class.close-reason-badge--tp]="pos.close_reason === 'TP'"
                              [class.close-reason-badge--manual]="pos.close_reason === 'MANUAL'"
                              [class.close-reason-badge--external]="pos.close_reason === 'EXTERNAL'">
                          {{ pos.close_reason ?? '—' }}
                        </span>
                      </td>
                      <td class="text-body-secondary small">{{ formatDate(pos.opened_at) }}</td>
                      <td class="text-body-secondary small">{{ formatDate(pos.closed_at) }}</td>
                      <td class="text-body-secondary small">{{ formatDuration(pos.duration_minutes) }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>

            <!-- Pagination -->
            @if (totalPages() > 1) {
              <div class="d-flex justify-content-center align-items-center gap-2 py-2">
                <button cButton color="primary" variant="outline" size="sm"
                        [disabled]="currentPage() <= 1"
                        (click)="goToPage(currentPage() - 1)">
                  &laquo;
                </button>
                <span class="small text-body-secondary">
                  Pagina {{ currentPage() }} di {{ totalPages() }}
                </span>
                <button cButton color="primary" variant="outline" size="sm"
                        [disabled]="currentPage() >= totalPages()"
                        (click)="goToPage(currentPage() + 1)">
                  &raquo;
                </button>
              </div>
            }
          }
        </c-card-body>
      </c-card>
    }
  `
})
export class PositionsComponent implements OnInit, OnDestroy {
  readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  private readonly toast = inject(ToastService);
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  readonly assets = TRADABLE_ASSETS;
  readonly activeTab = signal<Tab>('open');
  readonly closingDealId = signal<string | null>(null);

  // History filters
  readonly filterEpic = signal('');
  readonly filterReason = signal('');
  readonly filterFrom = signal('');
  readonly filterTo = signal('');
  readonly currentPage = signal(1);
  readonly pageSize = 50;

  readonly exporting = signal(false);

  readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.trading.closedTotal() / this.pageSize))
  );

  // Calculate live P&L + current price using WebSocket prices
  readonly livePositions = computed(() => {
    const positions = this.trading.paperPositions();
    const prices = this.ws.prices();
    return positions.map(pos => {
      const tick = prices[pos.epic];
      if (!tick) return { ...pos, live_pnl: 0, current_price: null as number | null };
      const currentPrice = pos.direction === 'BUY' ? tick.bid : tick.offer;
      const diff = pos.direction === 'BUY' ? currentPrice - pos.level : pos.level - currentPrice;
      return {
        ...pos,
        live_pnl: Math.round(diff * pos.size * 100) / 100,
        current_price: currentPrice,
      };
    });
  });

  readonly totalPnl = computed(() =>
    this.livePositions().reduce((sum, p) => sum + (p.live_pnl ?? 0), 0)
  );

  ngOnInit(): void {
    this.trading.loadPaperPositions();
    this.ws.connectPrices();
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

  switchTab(tab: Tab): void {
    this.activeTab.set(tab);
    if (tab === 'history' && this.trading.closedPositions().length === 0) {
      this.loadHistory();
    }
  }

  loadHistory(): void {
    this.trading.loadClosedPositions({
      page: this.currentPage(),
      page_size: this.pageSize,
      epic: this.filterEpic() || undefined,
      close_reason: this.filterReason() || undefined,
      date_from: this.filterFrom() || undefined,
      date_to: this.filterTo() || undefined,
    });
  }

  goToPage(page: number): void {
    this.currentPage.set(page);
    this.loadHistory();
  }

  closePosition(dealId: string): void {
    this.closingDealId.set(dealId);
    this.trading.closePosition(dealId).subscribe({
      next: () => {
        this.closingDealId.set(null);
        // Toast notification handled by NotificationService via WebSocket event
        this.trading.loadPaperPositions();
      },
      error: (err) => {
        this.closingDealId.set(null);
        this.toast.error(err?.error?.error || 'Errore nella chiusura');
      }
    });
  }

  exportHistoryCsv(): void {
    this.exporting.set(true);
    this.trading.exportClosedPositionsCsv({
      epic: this.filterEpic() || undefined,
      close_reason: this.filterReason() || undefined,
      date_from: this.filterFrom() || undefined,
      date_to: this.filterTo() || undefined,
    }).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `mantis-positions-${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        this.exporting.set(false);
      },
      error: () => {
        this.toast.error('Errore nell\'esportazione CSV');
        this.exporting.set(false);
      },
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

  formatDate(iso: string | null | undefined): string {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('it-IT', {
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso ?? '—'; }
  }

  formatDuration(minutes: number | null | undefined): string {
    if (minutes == null) return '—';
    if (minutes < 60) return `${minutes}m`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    if (h < 24) return `${h}h ${m}m`;
    const d = Math.floor(h / 24);
    return `${d}g ${h % 24}h`;
  }
}
