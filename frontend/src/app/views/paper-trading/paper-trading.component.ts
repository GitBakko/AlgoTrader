import { Component, OnInit, OnDestroy, inject, signal, computed } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent, ProgressBarComponent,
  ButtonDirective, SpinnerComponent, AlertComponent,
  TableDirective,
} from '@coreui/angular';

import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { PaperPosition, PaperSignal, BrokerErrorDetail } from '../../core/models';

interface KpiCard {
  label: string;
  value: string;
  colorClass: string;
}

interface LivePosition extends PaperPosition {
  live_pnl: number;
}

@Component({
  selector: 'app-paper-trading',
  standalone: true,
  imports: [
    CommonModule, DecimalPipe,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent, ProgressBarComponent,
    ButtonDirective, SpinnerComponent, AlertComponent,
    TableDirective,
  ],
  template: `
    <!-- Alerts -->
    @if (successMsg()) {
      <c-alert color="success" [dismissible]="true" (visibleChange)="successMsg.set('')">
        {{ successMsg() }}
      </c-alert>
    }
    @if (errorMsg()) {
      <c-alert color="danger" [dismissible]="true" (visibleChange)="errorMsg.set('')">
        {{ errorMsg() }}
      </c-alert>
    }

    <!-- Section A: Control Panel -->
    <c-card class="mb-4 border-start border-start-4"
            [class.border-start-success]="status()?.running"
            [class.border-start-secondary]="!status()?.running">
      <c-card-body>
        <c-row class="align-items-center">
          <c-col md="4">
            <c-badge [color]="status()?.running ? 'success' : 'secondary'" class="fs-6 mb-1">
              {{ status()?.running ? 'RUNNING' : 'STOPPED' }}
            </c-badge>
            <c-badge [color]="modeColor()" class="fs-6 mb-1 ms-2">
              {{ status()?.execution_mode ?? 'PAPER' }}
            </c-badge>
            @if (status()?.message && !status()?.running && !status()?.epics) {
              <div class="text-warning small mt-1">{{ status()?.message }}</div>
            }
            @if (status()?.last_run) {
              <div class="text-body-secondary small mt-1">
                Ultimo check: {{ formatDateTime(status()!.last_run!) }}
              </div>
            }
          </c-col>
          <c-col md="4" class="text-center">
            <div class="text-body-secondary small">Intervallo</div>
            <div class="fs-5">{{ status()?.interval_seconds ?? '—' }}s</div>
            <div class="text-body-secondary small">
              {{ status()?.check_count ?? 0 }} check totali
            </div>
          </c-col>
          <c-col md="4" class="text-end">
            <button cButton [color]="status()?.running ? 'danger' : 'success'"
                    (click)="togglePaperTrading()" [disabled]="actionInProgress() || !statusLoaded()">
              @if (actionInProgress()) {
                <c-spinner size="sm" class="me-2"></c-spinner>
              }
              {{ status()?.running ? 'Stop Trading' : 'Start Trading' }}
            </button>
          </c-col>
        </c-row>
      </c-card-body>
    </c-card>

    <!-- Section B: KPI Cards -->
    <c-row>
      @for (kpi of kpiCards(); track kpi.label) {
        <c-col md="2" sm="4" class="mb-4">
          <c-card class="h-100">
            <c-card-body class="text-center py-3">
              <div class="text-body-secondary small text-uppercase mb-1">{{ kpi.label }}</div>
              <div class="fs-4 fw-semibold" [class]="kpi.colorClass">{{ kpi.value }}</div>
            </c-card-body>
          </c-card>
        </c-col>
      }
    </c-row>

    <!-- Section C: Models + Last Signals -->
    <c-row>
      <!-- Models Loaded -->
      <c-col md="6" class="mb-4">
        <c-card class="h-100">
          <c-card-header><strong>Modelli Caricati</strong></c-card-header>
          <c-card-body>
            @if (modelEntries().length > 0) {
              <table cTable [striped]="true" [hover]="true" [small]="true">
                <thead>
                  <tr>
                    <th>Epic</th>
                    <th>Tipo</th>
                    <th>Features</th>
                    <th>Versione</th>
                  </tr>
                </thead>
                <tbody>
                  @for (m of modelEntries(); track m.epic) {
                    <tr>
                      <td><strong>{{ m.epic }}</strong></td>
                      <td>{{ m.info.model_type }}</td>
                      <td>{{ m.info.num_features }}</td>
                      <td>{{ m.info.version }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            } @else {
              <p class="text-body-secondary mb-0">Nessun modello caricato</p>
            }
          </c-card-body>
        </c-card>
      </c-col>

      <!-- Last Signals per Epic -->
      <c-col md="6" class="mb-4">
        <c-card class="h-100">
          <c-card-header><strong>Ultimi Segnali per Asset</strong></c-card-header>
          <c-card-body>
            @if (signalEntries().length > 0) {
              <table cTable [striped]="true" [hover]="true" [small]="true">
                <thead>
                  <tr>
                    <th>Epic</th>
                    <th>Direzione</th>
                    <th>Confidenza</th>
                    <th>Prezzo</th>
                    <th>Stato</th>
                  </tr>
                </thead>
                <tbody>
                  @for (s of signalEntries(); track s.epic) {
                    <tr>
                      <td><strong>{{ s.epic }}</strong></td>
                      <td>
                        <c-badge [color]="directionColor(s.info.direction)">
                          {{ s.info.direction }}
                        </c-badge>
                      </td>
                      <td>
                        <div class="d-flex align-items-center gap-2">
                          <c-progress class="flex-grow-1" style="height: 6px;">
                            <c-progress-bar
                              [value]="s.info.confidence * 100"
                              [color]="s.info.confidence >= 0.5 ? 'success' : 'warning'">
                            </c-progress-bar>
                          </c-progress>
                          <small>{{ (s.info.confidence * 100).toFixed(0) }}%</small>
                        </div>
                      </td>
                      <td>{{ s.info.entry_price | number:'1.2-2' }}</td>
                      <td>
                        @if (s.info.status) {
                          <c-badge [color]="statusColor(s.info.status)">
                            {{ statusLabel(s.info.status) }}
                          </c-badge>
                          @if (s.info.error_detail) {
                            <div [class]="s.info.status === 'market_closed' ? 'text-body-secondary small mt-1' : 'text-danger small mt-1'" style="max-width: 200px;">
                              {{ s.info.error_detail.summary }}
                            </div>
                          } @else if (s.info.rejection_reason) {
                            <div class="text-danger small mt-1" style="max-width: 200px;">
                              {{ s.info.rejection_reason }}
                            </div>
                          }
                        } @else {
                          <small class="text-body-secondary">{{ formatDateTime(s.info.timestamp) }}</small>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            } @else {
              <p class="text-body-secondary mb-0">Nessun segnale generato</p>
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>

    <!-- Section D: Open Positions -->
    <c-card class="mb-4">
      <c-card-header class="d-flex align-items-center">
        <strong>Posizioni Aperte</strong>
        <c-badge color="info" class="ms-2">{{ livePositions().length }}</c-badge>
        @if (livePositions().length > 0) {
          <c-badge [color]="totalPnl() >= 0 ? 'success' : 'danger'" class="ms-auto">
            P&amp;L: {{ totalPnl() >= 0 ? '+' : '' }}{{ totalPnl() | number:'1.2-2' }}
          </c-badge>
        }
      </c-card-header>
      <c-card-body>
        @if (livePositions().length > 0) {
          <table cTable [striped]="true" [hover]="true" [small]="true" [responsive]="true">
            <thead>
              <tr>
                <th>Epic</th>
                <th>Direzione</th>
                <th>Size</th>
                <th>Entry</th>
                <th>SL</th>
                <th>TP</th>
                <th>P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              @for (pos of livePositions(); track pos.deal_id) {
                <tr>
                  <td><strong>{{ pos.epic }}</strong></td>
                  <td>
                    <c-badge [color]="directionColor(pos.direction)">
                      {{ pos.direction }}
                    </c-badge>
                  </td>
                  <td>{{ pos.size | number:'1.4-4' }}</td>
                  <td>{{ pos.level | number:'1.2-2' }}</td>
                  <td>{{ pos.stop_level !== null ? (pos.stop_level | number:'1.2-2') : '—' }}</td>
                  <td>{{ pos.profit_level !== null ? (pos.profit_level | number:'1.2-2') : '—' }}</td>
                  <td [class]="pos.live_pnl >= 0 ? 'text-success fw-semibold' : 'text-danger fw-semibold'">
                    {{ pos.live_pnl >= 0 ? '+' : '' }}{{ pos.live_pnl | number:'1.2-2' }}
                  </td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <p class="text-body-secondary mb-0">Nessuna posizione aperta</p>
        }
      </c-card-body>
    </c-card>

    <!-- Section E: Recent Signals -->
    <c-card class="mb-4">
      <c-card-header class="d-flex align-items-center">
        <strong>Attivita Recente</strong>
        @if (rejectedCount() > 0) {
          <c-badge color="danger" class="ms-2">{{ rejectedCount() }} rejected</c-badge>
        }
      </c-card-header>
      <c-card-body>
        @if (recentSignals().length > 0) {
          <table cTable [striped]="true" [hover]="true" [small]="true" [responsive]="true">
            <thead>
              <tr>
                <th>Ora</th>
                <th>Epic</th>
                <th>Direzione</th>
                <th>Confidenza</th>
                <th>Prezzo</th>
                <th>Stato</th>
                <th>Dettaglio</th>
              </tr>
            </thead>
            <tbody>
              @for (sig of recentSignals(); track sig.timestamp + sig.epic) {
                <tr [class.table-danger]="sig.status === 'rejected' || sig.status === 'exec_failed'"
                    [class.table-secondary]="sig.status === 'market_closed'">
                  <td class="small">{{ formatDateTime(sig.timestamp) }}</td>
                  <td><strong>{{ sig.epic }}</strong></td>
                  <td>
                    <c-badge [color]="directionColor(sig.direction)">
                      {{ sig.direction }}
                    </c-badge>
                  </td>
                  <td>{{ (sig.confidence * 100).toFixed(0) }}%</td>
                  <td>{{ sig.entry_price | number:'1.2-2' }}</td>
                  <td>
                    <c-badge [color]="statusColor(sig.status)">
                      {{ statusLabel(sig.status) }}
                    </c-badge>
                  </td>
                  <td class="small" style="max-width: 300px;">
                    @if (sig.error_detail) {
                      <div class="d-flex align-items-start gap-1">
                        <span>{{ errorIcon(sig.error_detail.error_type) }}</span>
                        <div>
                          <span [class]="sig.status === 'market_closed' ? 'text-body-secondary' : 'text-danger'">
                            {{ sig.error_detail.summary }}
                          </span>
                          @if (sig.error_detail.details) {
                            <div class="text-body-secondary mt-1" style="font-size: 0.75rem;">
                              {{ sig.error_detail.details }}
                            </div>
                          }
                          <button class="btn btn-link btn-sm p-0 mt-1" style="font-size: 0.7rem;"
                                  (click)="toggleRaw(sig)">
                            {{ sig._showRaw ? 'Nascondi RAW' : 'Visualizza RAW' }}
                          </button>
                          @if (sig._showRaw) {
                            <pre class="bg-body-tertiary p-2 mt-1 rounded small mb-0"
                                 style="font-size: 0.7rem; max-height: 100px; overflow: auto;">{{ sig.error_detail.raw }}</pre>
                          }
                        </div>
                      </div>
                    } @else if (sig.rejection_reason) {
                      <span class="text-danger">{{ sig.rejection_reason }}</span>
                    } @else if (sig.status === 'executed') {
                      <span class="text-success">Trade eseguito</span>
                    } @else if (sig.status === 'hold') {
                      <span class="text-body-secondary">Segnale HOLD, nessuna azione</span>
                    } @else if (sig.status === 'market_closed') {
                      <span class="text-body-secondary">Mercato chiuso</span>
                    } @else {
                      <span class="text-body-secondary">—</span>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <p class="text-body-secondary mb-0">Nessun segnale recente</p>
        }
      </c-card-body>
    </c-card>
  `
})
export class PaperTradingComponent implements OnInit, OnDestroy {
  readonly trading = inject(TradingService);
  readonly ws = inject(WebSocketService);

  readonly actionInProgress = signal(false);
  readonly successMsg = signal('');
  readonly errorMsg = signal('');

  readonly status = this.trading.paperStatus;
  readonly statusLoaded = computed(() => this.status() !== null);

  // KPI cards derived from status
  readonly kpiCards = computed<KpiCard[]>(() => {
    const s = this.status();
    if (!s) return [];
    const pnl = s.total_unrealized_pnl ?? 0;
    return [
      { label: 'Iterazioni', value: String(s.iteration_count ?? 0), colorClass: 'text-info' },
      { label: 'Segnali', value: String(s.signal_count ?? 0), colorClass: 'text-primary' },
      { label: 'Trade', value: String(s.trade_count ?? 0), colorClass: 'text-success' },
      { label: 'Errori', value: String(s.error_count ?? 0), colorClass: (s.error_count ?? 0) > 0 ? 'text-danger' : 'text-success' },
      { label: 'Posizioni', value: String(s.open_positions ?? 0), colorClass: 'text-warning' },
      { label: 'P&L', value: (pnl >= 0 ? '+' : '') + pnl.toFixed(2), colorClass: pnl >= 0 ? 'text-success' : 'text-danger' },
    ];
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

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private readonly POLL_INTERVAL = 12_000;

  ngOnInit(): void {
    this.loadAll();
    this.ws.connectPrices();
    this.pollTimer = setInterval(() => this.loadAll(), this.POLL_INTERVAL);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  loadAll(): void {
    this.trading.loadPaperStatus();
    this.trading.loadPaperPositions();
    this.trading.loadPaperSignals();
  }

  togglePaperTrading(): void {
    this.actionInProgress.set(true);
    this.errorMsg.set('');
    this.successMsg.set('');
    const action = this.status()?.running
      ? this.trading.stopPaperTrading()
      : this.trading.startPaperTrading();
    action.subscribe({
      next: (data) => {
        this.showSuccess(data.message);
        this.actionInProgress.set(false);
        this.loadAll();
      },
      error: (err) => {
        this.errorMsg.set(err?.error?.error || 'Operazione fallita');
        this.actionInProgress.set(false);
      }
    });
  }

  private showSuccess(msg: string, ms = 2000): void {
    this.successMsg.set(msg);
    setTimeout(() => this.successMsg.set(''), ms);
  }

  modeColor(): string {
    switch (this.status()?.execution_mode) {
      case 'DEMO': return 'warning';
      case 'LIVE': return 'danger';
      default: return 'info';
    }
  }

  directionColor(direction: string): string {
    switch (direction) {
      case 'BUY': return 'success';
      case 'SELL': return 'danger';
      default: return 'secondary';
    }
  }

  statusColor(status: string): string {
    switch (status) {
      case 'executed': return 'success';
      case 'rejected': return 'danger';
      case 'exec_failed': return 'danger';
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

  errorIcon(errorType: string): string {
    switch (errorType) {
      case 'market_closed': return '\u{1F550}';
      case 'insufficient_funds': return '\u{1F4B0}';
      case 'rate_limit': return '\u{23F1}';
      case 'min_size': return '\u{1F4CF}';
      case 'max_positions': return '\u{1F4CA}';
      default: return '\u{26A0}';
    }
  }

  toggleRaw(sig: any): void {
    sig._showRaw = !sig._showRaw;
  }

  formatDateTime(iso: string | null): string {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('it-IT', {
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    } catch {
      return iso;
    }
  }
}
