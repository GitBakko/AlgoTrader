import { Component, ChangeDetectionStrategy, OnInit, OnDestroy, inject, signal, computed } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent, ProgressBarComponent,
  ButtonDirective, SpinnerComponent,
  TableDirective, AlertComponent,
} from '@coreui/angular';

import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { MarketStatusService, MarketStatusResponse } from '../../core/services/market-status.service';
import { ToastService } from '../../shared/services/toast.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { PaperPosition, PaperSignal } from '../../core/models';

interface LivePosition extends PaperPosition {
  live_pnl: number;
}

@Component({
  selector: 'app-paper-trading',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, DecimalPipe,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent, ProgressBarComponent,
    ButtonDirective, SpinnerComponent,
    TableDirective, AlertComponent,
    PriceFormatPipe,
  ],
  template: `
    <!-- ═══════ ROW 1: Status Bar ═══════ -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <div class="d-flex align-items-center gap-2">
        <h5 class="mb-0 fw-semibold">Paper Trading</h5>
        @if (status()?.running) {
          <c-badge color="success" class="ms-2">RUNNING</c-badge>
        } @else {
          <c-badge color="secondary" class="ms-2">STOPPED</c-badge>
        }
        @if (status()?.execution_mode; as mode) {
          <c-badge [color]="mode === 'LIVE' ? 'danger' : mode === 'DEMO' ? 'warning' : 'info'">
            {{ mode }}
          </c-badge>
        }
        @if (circuitBreakersTripped().length > 0) {
          <c-badge color="danger">CIRCUIT BREAKER</c-badge>
        }
        @if (currentMarketStatus(); as mktStatus) {
          @if (mktStatus.is_open) {
            <c-badge color="success" class="d-flex align-items-center gap-1">
              <span class="pulse-dot"></span>
              MARKET OPEN
            </c-badge>
          } @else {
            <c-badge color="danger">
              MARKET CLOSED
              @if (mktStatus.next_open) {
                <span class="ms-1">Opens in {{ getCountdown(mktStatus.next_open) }}</span>
              }
            </c-badge>
          }
        }
      </div>
      <div class="d-flex align-items-center gap-3">
        @if (status()?.last_run) {
          <span class="text-body-secondary small">
            Ultimo check: {{ formatTime(status()!.last_run!) }}
          </span>
        }
        <span class="text-body-secondary small">Poll: {{ (pollingInterval() / 1000) }}s</span>
        <button cButton [color]="status()?.running ? 'danger' : 'success'" size="sm"
                (click)="togglePaperTrading()" [disabled]="actionInProgress() || !statusLoaded()">
          @if (actionInProgress()) {
            <c-spinner size="sm" class="me-1"></c-spinner>
          }
          {{ status()?.running ? 'Stop' : 'Start' }}
        </button>
      </div>
    </div>

    <!-- Market Closed Alert -->
    @if (currentMarketStatus(); as mktStatus) {
      @if (!mktStatus.is_open) {
        <c-alert color="warning" class="mb-3">
          <strong>Using Last Available Data</strong>
          <br>
          <small>Market is currently closed. Showing most recent positions and signals.</small>
        </c-alert>
      }
    }

    <!-- ═══════ ROW 2: KPI Cards ═══════ -->
    <c-row>
      <c-col sm="6" xl="3">
        <c-card class="mb-4 border-top border-top-3 border-top-primary">
          <c-card-body class="pb-0">
            <div class="text-body-secondary text-uppercase small fw-semibold mb-1">Iterazioni</div>
            <div class="fs-4 fw-bold">{{ status()?.iteration_count ?? 0 }}</div>
          </c-card-body>
          <div class="px-3 pb-3">
            <div class="text-body-secondary small">
              Check: {{ status()?.check_count ?? 0 }} |
              Intervallo: {{ status()?.interval_seconds ?? '—' }}s
            </div>
          </div>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3">
        <c-card class="mb-4 border-top border-top-3 border-top-info">
          <c-card-body class="pb-0">
            <div class="text-body-secondary text-uppercase small fw-semibold mb-1">Segnali / Trade</div>
            <div class="fs-4 fw-bold">
              {{ status()?.signal_count ?? 0 }}
              <span class="fs-6 text-body-secondary fw-normal">/ {{ status()?.trade_count ?? 0 }}</span>
            </div>
          </c-card-body>
          <div class="px-3 pb-3">
            <div class="text-body-secondary small">
              Conversione: {{ conversionRate() }}%
            </div>
          </div>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3">
        <c-card class="mb-4 border-top border-top-3"
                [class.border-top-success]="totalPnl() >= 0"
                [class.border-top-danger]="totalPnl() < 0">
          <c-card-body class="pb-0">
            <div class="text-body-secondary text-uppercase small fw-semibold mb-1">P&amp;L (USD)</div>
            <div class="fs-4 fw-bold"
                 [class.text-success]="totalPnl() >= 0"
                 [class.text-danger]="totalPnl() < 0">
              $ {{ totalPnl() >= 0 ? '+' : '' }}{{ totalPnl() | number:'1.2-2' }}
            </div>
          </c-card-body>
          <div class="px-3 pb-3">
            <div class="text-body-secondary small">
              Posizioni aperte: {{ livePositions().length }}
            </div>
          </div>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3">
        <c-card class="mb-4 border-top border-top-3"
                [class.border-top-danger]="(status()?.error_count ?? 0) > 0"
                [class.border-top-success]="(status()?.error_count ?? 0) === 0">
          <c-card-body class="pb-0">
            <div class="text-body-secondary text-uppercase small fw-semibold mb-1">Errori</div>
            <div class="fs-4 fw-bold"
                 [class.text-danger]="(status()?.error_count ?? 0) > 0">
              {{ status()?.error_count ?? 0 }}
            </div>
          </c-card-body>
          <div class="px-3 pb-3">
            @if (rejectedCount() > 0) {
              <div class="text-danger small">{{ rejectedCount() }} segnali rifiutati</div>
            } @else {
              <div class="text-success small">Nessun rifiuto</div>
            }
          </div>
        </c-card>
      </c-col>
    </c-row>

    <!-- ═══════ ROW 3: Risk Status (compact) ═══════ -->
    @if (status()?.running) {
      <c-row class="mb-4">
        <c-col sm="6" lg="3">
          <c-card class="h-100">
            <c-card-body class="py-2 d-flex justify-content-between align-items-center">
              <span class="text-body-secondary small">Circuit Breakers</span>
              @if (circuitBreakersTripped().length === 0) {
                <c-badge color="success" class="badge-sm">OK</c-badge>
              } @else {
                <div class="d-flex flex-wrap gap-1 justify-content-end" style="max-width: 160px;">
                  @for (b of circuitBreakersTripped(); track b) {
                    <c-badge color="danger" class="badge-sm">{{ b }}</c-badge>
                  }
                </div>
              }
            </c-card-body>
          </c-card>
        </c-col>
        <c-col sm="6" lg="3">
          <c-card class="h-100">
            <c-card-body class="py-2 d-flex justify-content-between align-items-center">
              <span class="text-body-secondary small">Equity Filter</span>
              @if (status()?.equity_curve_below_sma) {
                <c-badge color="warning" class="badge-sm">-50% Size</c-badge>
              } @else {
                <c-badge color="success" class="badge-sm">Normale</c-badge>
              }
            </c-card-body>
          </c-card>
        </c-col>
        <c-col sm="6" lg="3">
          <c-card class="h-100">
            <c-card-body class="py-2 d-flex justify-content-between align-items-center">
              <span class="text-body-secondary small">Kelly History</span>
              <strong class="text-info">{{ status()?.kelly_trade_history_size ?? 0 }}</strong>
            </c-card-body>
          </c-card>
        </c-col>
        <c-col sm="6" lg="3">
          <c-card class="h-100">
            <c-card-body class="py-2 d-flex justify-content-between align-items-center">
              <span class="text-body-secondary small">Trailing Stops</span>
              <strong class="text-primary">{{ status()?.trailing_stops_tracked ?? 0 }}</strong>
            </c-card-body>
          </c-card>
        </c-col>
      </c-row>
    }

    <!-- ═══════ ROW 4: Positions + Last Signals per Asset ═══════ -->
    <c-row>
      <!-- Open Positions -->
      <c-col xl="7">
        <c-card class="mb-4">
          <c-card-header class="d-flex align-items-center justify-content-between py-2">
            <div class="d-flex align-items-center">
              <strong>Posizioni Aperte</strong>
              <c-badge color="info" class="ms-2">{{ livePositions().length }}</c-badge>
            </div>
            @if (livePositions().length > 0) {
              <c-badge [color]="totalPnl() >= 0 ? 'success' : 'danger'">
                $ {{ totalPnl() >= 0 ? '+' : '' }}{{ totalPnl() | number:'1.2-2' }}
              </c-badge>
            }
          </c-card-header>
          <c-card-body class="p-0">
            @if (livePositions().length > 0) {
              <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Dir</th>
                    <th>Size</th>
                    <th>Entry</th>
                    <th>SL</th>
                    <th>TP</th>
                    <th>Trailing</th>
                    <th class="text-end">P&amp;L (USD)</th>
                  </tr>
                </thead>
                <tbody>
                  @for (pos of livePositions(); track pos.deal_id) {
                    <tr>
                      <td class="fw-semibold">{{ pos.epic }}</td>
                      <td>
                        <c-badge [color]="directionColor(pos.direction)" class="badge-sm">
                          {{ pos.direction }}
                        </c-badge>
                      </td>
                      <td class="font-monospace">{{ pos.size | number:'1.4-4' }}</td>
                      <td class="font-monospace">{{ pos.level | priceFormat:pos.epic }}</td>
                      <td class="font-monospace">{{ pos.stop_level !== null ? (pos.stop_level | priceFormat:pos.epic) : '—' }}</td>
                      <td class="font-monospace">{{ pos.profit_level !== null ? (pos.profit_level | priceFormat:pos.epic) : '—' }}</td>
                      <td>
                        @if (pos.trailing_stop_phase) {
                          <c-badge [color]="trailingPhaseColor(pos.trailing_stop_phase)" class="badge-sm">
                            {{ pos.trailing_stop_phase }}
                          </c-badge>
                        } @else {
                          <span class="text-body-secondary">-</span>
                        }
                      </td>
                      <td class="text-end fw-semibold font-monospace"
                          [class.text-success]="pos.live_pnl >= 0"
                          [class.text-danger]="pos.live_pnl < 0">
                        $ {{ pos.live_pnl >= 0 ? '+' : '' }}{{ pos.live_pnl | number:'1.2-2' }}
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            } @else {
              <div class="text-center py-4 text-body-secondary small">
                Nessuna posizione aperta
              </div>
            }
          </c-card-body>
        </c-card>
      </c-col>

      <!-- Last Signal per Asset -->
      <c-col xl="5">
        <c-card class="mb-4">
          <c-card-header class="py-2"><strong>Ultimo Segnale per Asset</strong></c-card-header>
          <c-card-body class="p-0">
            @if (signalEntries().length > 0) {
              <table cTable [small]="true" [hover]="true" class="mb-0">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Dir</th>
                    <th>Conf</th>
                    <th>Stato</th>
                  </tr>
                </thead>
                <tbody>
                  @for (s of signalEntries(); track s.epic) {
                    <tr>
                      <td class="fw-semibold">{{ s.epic }}</td>
                      <td>
                        <c-badge [color]="directionColor(s.info.direction)" class="badge-sm">
                          {{ s.info.direction }}
                        </c-badge>
                      </td>
                      <td>
                        <div class="d-flex align-items-center gap-1">
                          <c-progress class="flex-grow-1" style="height: 4px; min-width: 40px;">
                            <c-progress-bar
                              [value]="s.info.confidence * 100"
                              [color]="s.info.confidence >= 0.5 ? 'success' : 'warning'">
                            </c-progress-bar>
                          </c-progress>
                          <small class="font-monospace">{{ (s.info.confidence * 100).toFixed(0) }}%</small>
                        </div>
                      </td>
                      <td>
                        @if (s.info.status) {
                          <c-badge [color]="statusColor(s.info.status)" class="badge-sm">
                            {{ statusLabel(s.info.status) }}
                          </c-badge>
                          @if (s.info.error_detail) {
                            <div class="text-body-secondary small mt-1" style="max-width: 150px; font-size: 0.7rem;">
                              {{ s.info.error_detail.summary }}
                            </div>
                          }
                        } @else {
                          <small class="text-body-secondary">{{ formatTime(s.info.timestamp) }}</small>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            } @else {
              <div class="text-center py-4 text-body-secondary small">
                Nessun segnale generato
              </div>
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>

    <!-- ═══════ ROW 5: Models Loaded ═══════ -->
    <c-card class="mb-4">
      <c-card-header class="d-flex align-items-center py-2">
        <strong>Modelli Caricati</strong>
        <c-badge color="primary" class="ms-2">{{ modelEntries().length }}</c-badge>
      </c-card-header>
      <c-card-body class="p-0">
        @if (modelEntries().length > 0) {
          <table cTable [small]="true" [hover]="true" class="mb-0">
            <thead>
              <tr>
                <th>Epic</th>
                <th>Tipo</th>
                <th>Features</th>
                <th>Versione</th>
                <th>Creato</th>
              </tr>
            </thead>
            <tbody>
              @for (m of modelEntries(); track m.epic) {
                <tr>
                  <td class="fw-semibold">{{ m.epic }}</td>
                  <td><c-badge color="primary" class="badge-sm">{{ m.info.model_type }}</c-badge></td>
                  <td class="font-monospace">{{ m.info.num_features }}</td>
                  <td>{{ m.info.version }}</td>
                  <td class="text-body-secondary small">{{ formatDate(m.info.created_at) }}</td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <div class="text-center py-4 text-body-secondary small">
            Nessun modello caricato. Avvia il trading per caricare i modelli.
          </div>
        }
      </c-card-body>
    </c-card>

    <!-- ═══════ ROW 6: Recent Activity Feed ═══════ -->
    <c-card class="mb-4">
      <c-card-header class="d-flex align-items-center justify-content-between py-2">
        <div class="d-flex align-items-center">
          <strong>Attivita Recente</strong>
          <c-badge color="secondary" class="ms-2">{{ recentSignals().length }}</c-badge>
          @if (rejectedCount() > 0) {
            <c-badge color="danger" class="ms-2">{{ rejectedCount() }} rifiutati</c-badge>
          }
        </div>
        <span class="text-body-secondary small">Aggiornamento: {{ (pollingInterval() / 1000) }}s</span>
      </c-card-header>
      <c-card-body class="p-0">
        @if (recentSignals().length > 0) {
          <div style="max-height: 400px; overflow-y: auto;">
            <table cTable [small]="true" [hover]="true" class="mb-0">
              <thead class="position-sticky top-0" style="z-index: 1;">
                <tr>
                  <th>Ora</th>
                  <th>Asset</th>
                  <th>Strategia</th>
                  <th>Dir</th>
                  <th>Conf</th>
                  <th>Prezzo</th>
                  <th>Stato</th>
                  <th>Dettaglio</th>
                </tr>
              </thead>
              <tbody>
                @for (sig of recentSignals(); track sig.timestamp + sig.epic) {
                  <tr [class.table-danger]="sig.status === 'rejected' || sig.status === 'exec_failed'"
                      [class.table-secondary]="sig.status === 'market_closed'">
                    <td class="small text-body-secondary text-nowrap">{{ formatTime(sig.timestamp) }}</td>
                    <td class="fw-semibold">{{ sig.epic }}</td>
                    <td>
                      @if (sig.strategy_name) {
                        <c-badge [color]="strategyColor(sig.strategy_name)" class="badge-sm">
                          {{ strategyLabel(sig.strategy_name) }}
                        </c-badge>
                      } @else {
                        <span class="text-body-secondary">-</span>
                      }
                    </td>
                    <td>
                      <c-badge [color]="directionColor(sig.direction)" class="badge-sm">
                        {{ sig.direction }}
                      </c-badge>
                    </td>
                    <td class="font-monospace small">{{ (sig.confidence * 100).toFixed(0) }}%</td>
                    <td class="font-monospace small">{{ sig.entry_price | priceFormat:sig.epic }}</td>
                    <td>
                      <c-badge [color]="statusColor(sig.status)" class="badge-sm">
                        {{ statusLabel(sig.status) }}
                      </c-badge>
                    </td>
                    <td class="small" style="max-width: 250px;">
                      @if (sig.error_detail) {
                        <div>
                          <span [class]="sig.status === 'market_closed' ? 'text-body-secondary' : 'text-danger'">
                            {{ sig.error_detail.summary }}
                          </span>
                          @if (sig.error_detail.details) {
                            <div class="text-body-secondary" style="font-size: 0.7rem;">
                              {{ sig.error_detail.details }}
                            </div>
                          }
                          <button class="btn btn-link btn-sm p-0" style="font-size: 0.65rem;"
                                  (click)="toggleRaw(sig)">
                            {{ sig._showRaw ? 'Nascondi' : 'RAW' }}
                          </button>
                          @if (sig._showRaw) {
                            <pre class="bg-body-tertiary p-1 mt-1 rounded mb-0"
                                 style="font-size: 0.65rem; max-height: 80px; overflow: auto;">{{ sig.error_detail.raw }}</pre>
                          }
                        </div>
                      } @else if (sig.rejection_reason) {
                        <span class="text-danger">{{ sig.rejection_reason }}</span>
                      } @else if (sig.status === 'executed') {
                        <span class="text-success">Trade eseguito</span>
                      } @else if (sig.status === 'hold') {
                        <span class="text-body-secondary">HOLD</span>
                      } @else if (sig.status === 'market_closed') {
                        <span class="text-body-secondary">Chiuso</span>
                      } @else {
                        <span class="text-body-secondary">—</span>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <div class="text-center py-4 text-body-secondary small">
            Nessun segnale recente. Avvia il paper trading per generare segnali.
          </div>
        }
      </c-card-body>
    </c-card>
  `
})
export class PaperTradingComponent implements OnInit, OnDestroy {
  readonly trading = inject(TradingService);
  readonly ws = inject(WebSocketService);
  readonly marketStatus = inject(MarketStatusService);
  readonly toast = inject(ToastService);

  readonly actionInProgress = signal(false);
  readonly currentEpic = signal<string>('XAUUSD');
  readonly currentMarketStatus = signal<MarketStatusResponse | null>(null);

  readonly status = this.trading.paperStatus;
  readonly statusLoaded = computed(() => this.status() !== null);

  // Polling interval based on market status
  readonly pollingInterval = computed(() => {
    const mktStatus = this.currentMarketStatus();
    if (!mktStatus) return 12000; // 12s default
    if (!mktStatus.is_open) return 300000; // 5min if closed
    if (mktStatus.status === 'TRADEABLE') return 12000; // 12s if open
    return 60000; // 1min if suspended
  });

  // Signal/Trade conversion rate
  readonly conversionRate = computed(() => {
    const s = this.status();
    if (!s || !s.signal_count) return '0';
    return ((s.trade_count / s.signal_count) * 100).toFixed(1);
  });

  // Models loaded entries
  readonly modelEntries = computed(() => {
    const s = this.status();
    if (!s?.models_loaded) return [];
    return Object.entries(s.models_loaded).map(([epic, info]) => ({ epic, info }));
  });

  // Last signals entries
  readonly signalEntries = computed(() => {
    const s = this.status();
    if (!s?.last_signals) return [];
    return Object.entries(s.last_signals).map(([epic, info]) => ({ epic, info }));
  });

  // Live positions with WebSocket P&L
  readonly livePositions = computed<LivePosition[]>(() => {
    const positions = this.trading.paperPositions();
    const prices = this.ws.prices();
    return positions.map(pos => {
      const tick = prices[pos.epic];
      if (!tick) return { ...pos, live_pnl: 0 };
      const currentPrice = pos.direction === 'BUY' ? tick.bid : tick.offer;
      const diff = pos.direction === 'BUY'
        ? currentPrice - pos.level
        : pos.level - currentPrice;
      return { ...pos, live_pnl: Math.round(diff * pos.size * 100) / 100 };
    });
  });

  // Total P&L across all positions
  readonly totalPnl = computed(() => {
    return this.livePositions().reduce((sum, pos) => sum + pos.live_pnl, 0);
  });

  // Recent signals (latest 50)
  readonly recentSignals = computed(() => {
    return this.trading.paperSignals().slice(0, 50);
  });

  // Count of rejected signals in recent history
  readonly rejectedCount = computed(() => {
    return this.recentSignals().filter(s => s.status === 'rejected' || s.status === 'exec_failed').length;
  });

  // Phase 8: circuit breakers list
  readonly circuitBreakersTripped = computed<string[]>(() => {
    const raw = this.status()?.circuit_breakers_tripped;
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    return Object.entries(raw).map(([k, v]) => `${k}: ${v}`);
  });

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.startSmartPolling();
    this.ws.connectPrices();
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private async startSmartPolling(): Promise<void> {
    const epic = this.currentEpic();

    // Initial fetch
    try {
      const mktStatus = await this.marketStatus.getMarketStatus(epic);
      this.currentMarketStatus.set(mktStatus);
      this.loadAll();
    } catch (error) {
      console.error('Failed to fetch market status:', error);
      this.loadAll();
    }

    // Recursive polling with dynamic interval
    const poll = async () => {
      try {
        const mktStatus = await this.marketStatus.getMarketStatus(epic);
        this.currentMarketStatus.set(mktStatus);

        // Only load data if market is open
        if (mktStatus.is_open) {
          this.loadAll();
        }
      } catch (error) {
        console.error('Polling error:', error);
      }

      this.pollTimer = setTimeout(() => poll(), this.pollingInterval());
    };

    this.pollTimer = setTimeout(() => poll(), this.pollingInterval());
  }

  loadAll(): void {
    this.trading.loadPaperStatus();
    this.trading.loadPaperPositions();
    this.trading.loadPaperSignals();
  }

  togglePaperTrading(): void {
    this.actionInProgress.set(true);
    const action = this.status()?.running
      ? this.trading.stopPaperTrading()
      : this.trading.startPaperTrading();
    action.subscribe({
      next: (data) => {
        this.toast.success(data.message);
        this.actionInProgress.set(false);
        this.loadAll();
      },
      error: (err) => {
        this.toast.error(err?.error?.error || 'Operazione fallita');
        this.actionInProgress.set(false);
      }
    });
  }

  directionColor(direction: string): string {
    return direction === 'BUY' ? 'success' : direction === 'SELL' ? 'danger' : 'secondary';
  }

  statusColor(status: string): string {
    switch (status) {
      case 'executed': return 'success';
      case 'rejected': case 'exec_failed': return 'danger';
      case 'predicted': return 'info';
      case 'hold': return 'warning';
      case 'market_closed': return 'dark';
      default: return 'secondary';
    }
  }

  statusLabel(status: string): string {
    switch (status) {
      case 'executed': return 'Eseguito';
      case 'rejected': return 'Rifiutato';
      case 'exec_failed': return 'Fallito';
      case 'predicted': return 'Predetto';
      case 'hold': return 'Hold';
      case 'market_closed': return 'Chiuso';
      default: return status;
    }
  }

  toggleRaw(sig: any): void {
    sig._showRaw = !sig._showRaw;
  }

  strategyColor(name: string): string {
    switch (name) {
      case 'ml_ensemble': return 'primary';
      case 'squeeze_breakout': return 'warning';
      case 'vwap_reversion': return 'info';
      default: return 'secondary';
    }
  }

  strategyLabel(name: string): string {
    switch (name) {
      case 'ml_ensemble': return 'ML';
      case 'squeeze_breakout': return 'Squeeze';
      case 'vwap_reversion': return 'VWAP';
      default: return name;
    }
  }

  trailingPhaseColor(phase: string): string {
    switch (phase) {
      case 'INITIAL': return 'secondary';
      case 'BREAKEVEN': return 'info';
      case 'TP1_LOCK': return 'warning';
      case 'TRAILING': return 'success';
      default: return 'secondary';
    }
  }

  formatTime(iso: string | null): string {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('it-IT', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    } catch { return iso ?? '—'; }
  }

  formatDate(iso: string | null): string {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString('it-IT', {
        day: '2-digit', month: '2-digit', year: '2-digit',
      });
    } catch { return iso ?? '—'; }
  }

  getCountdown(timestamp: number): string {
    const diff = timestamp - Date.now();
    if (diff < 0) return 'Soon';

    const hours = Math.floor(diff / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);

    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `${days}d ${hours % 24}h`;
    }
    return `${hours}h ${minutes}m`;
  }
}
