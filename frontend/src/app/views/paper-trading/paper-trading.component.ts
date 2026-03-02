import { Component, ChangeDetectionStrategy, OnInit, OnDestroy, inject, signal, computed } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent, ProgressBarComponent,
  TableDirective, AlertComponent, TooltipDirective,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';

import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { MarketStatusService, MarketStatusResponse } from '../../core/services/market-status.service';
import { NewsService } from '../../core/services/news.service';
import { ToastService } from '../../shared/services/toast.service';
import { PriceFormatPipe } from '../../shared/pipes/price-format.pipe';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';
import { LoadingButtonComponent } from '../../shared/components/loading-button/loading-button.component';
import { NewsWidgetComponent } from '../../shared/components/news-widget/news-widget.component';
import { PaperPosition, PaperSignal } from '../../core/models';

interface LivePosition extends PaperPosition {
  live_pnl: number;
}

interface GroupedPosition {
  epic: string;
  positions: LivePosition[];
  totalSize: number;
  totalPnl: number;
  avgEntry: number;
  netDirection: 'LONG' | 'SHORT' | 'NEUTRAL';
  expanded: boolean;
}

@Component({
  selector: 'app-paper-trading',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrls: ['./paper-trading.component.scss'],
  imports: [
    CommonModule, DecimalPipe,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent, ProgressBarComponent,
    LoadingButtonComponent, IconDirective,
    TableDirective, AlertComponent, TooltipDirective,
    PriceFormatPipe,
    EpicLogoComponent,
    NewsWidgetComponent,
  ],
  template: `
    <!-- ═══════ STATUS STRIP (glassmorphism) ═══════ -->
    <div class="pt-status-strip">
      <div class="pt-status-strip__left">
        <h5 class="mb-0 fw-semibold">Paper Trading</h5>
        @if (status()?.running) {
          <span class="pt-chip pt-chip--running">
            <span class="pulse-dot"></span>
            RUNNING
          </span>
        } @else {
          <span class="pt-chip pt-chip--stopped">STOPPED</span>
        }
        @if (status()?.execution_mode; as mode) {
          <span class="pt-chip"
                [class.pt-chip--paper]="mode === 'PAPER'"
                [class.pt-chip--demo]="mode === 'DEMO'"
                [class.pt-chip--live]="mode === 'LIVE'">
            {{ mode }}
          </span>
        }
        @if (circuitBreakersTripped().length > 0) {
          <span class="pt-chip pt-chip--danger">CIRCUIT BREAKER</span>
        }
        @if (currentMarketStatus(); as mktStatus) {
          @if (mktStatus.is_open) {
            <span class="pt-chip pt-chip--open">
              <span class="pulse-dot"></span>
              MARKET OPEN
            </span>
          } @else {
            <span class="pt-chip pt-chip--closed">
              CLOSED
              @if (mktStatus.next_open) {
                &middot; {{ getCountdown(mktStatus.next_open) }}
              }
            </span>
          }
        }
      </div>
      <div class="pt-status-strip__right">
        @if (status()?.last_run) {
          <span class="pt-chip pt-chip--muted">
            {{ formatTime(status()!.last_run!) }}
          </span>
        }
        <span class="pt-chip pt-chip--muted">Poll: {{ (pollingInterval() / 1000) }}s</span>
        <app-loading-button [color]="status()?.running ? 'danger' : 'success'" size="sm"
                            [loading]="actionInProgress()"
                            [disabled]="!statusLoaded()"
                            (clicked)="togglePaperTrading()">
          {{ status()?.running ? 'Stop' : 'Start' }}
        </app-loading-button>
        @if (status()?.running || livePositions().length > 0) {
          <app-loading-button color="danger" size="sm" class="ms-2 emergency-stop-btn"
                              [loading]="emergencyStopInProgress()"
                              (clicked)="emergencyStop()">
            EMERGENCY STOP
          </app-loading-button>
        }
      </div>
    </div>

    <!-- Market Closed Alert -->
    @if (currentMarketStatus(); as mktStatus) {
      @if (!mktStatus.is_open) {
        <c-alert color="warning" class="mb-3 py-2" style="font-size: 0.8125rem;">
          <strong>Dati precedenti</strong> — Mercato chiuso, mostro le ultime posizioni e segnali disponibili.
        </c-alert>
      }
    }

    <!-- ═══════ SECTION: Stato ═══════ -->
    <div class="section-divider">
      <span class="section-divider__label">Stato</span>
      <span class="section-divider__line"></span>
    </div>

    <!-- KPI Cards (left accent bar pattern) -->
    <c-row class="mb-4">
      <c-col sm="6" xl="3" class="animate-in stagger-1">
        <c-card class="mb-3 pt-kpi-card">
          <div class="pt-kpi-card__accent pt-kpi-card__accent--primary"></div>
          <c-card-body class="ps-4">
            <div class="pt-kpi-card__label">Iterazioni</div>
            <div class="pt-kpi-card__value">{{ status()?.iteration_count ?? 0 }}</div>
            <div class="pt-kpi-card__detail">
              Check: {{ status()?.check_count ?? 0 }} &middot;
              Intervallo: {{ status()?.interval_seconds ?? '—' }}s
            </div>
          </c-card-body>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3" class="animate-in stagger-2">
        <c-card class="mb-3 pt-kpi-card">
          <div class="pt-kpi-card__accent pt-kpi-card__accent--info"></div>
          <c-card-body class="ps-4">
            <div class="pt-kpi-card__label">Segnali / Trade</div>
            <div class="pt-kpi-card__value">
              {{ status()?.signal_count ?? 0 }}
              <span style="font-size: 1rem; font-weight: 400; opacity: 0.5;">/ {{ status()?.trade_count ?? 0 }}</span>
            </div>
            <div class="pt-kpi-card__detail">
              Conversione: {{ conversionRate() }}%
            </div>
          </c-card-body>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3" class="animate-in stagger-3">
        <c-card class="mb-3 pt-kpi-card">
          <div class="pt-kpi-card__accent"
               [class.pt-kpi-card__accent--profit]="totalPnl() >= 0"
               [class.pt-kpi-card__accent--loss]="totalPnl() < 0"></div>
          <c-card-body class="ps-4">
            <div class="pt-kpi-card__label">P&amp;L (USD)</div>
            <div class="pt-kpi-card__value"
                 [class.text-success]="totalPnl() >= 0"
                 [class.text-danger]="totalPnl() < 0">
              $ {{ totalPnl() >= 0 ? '+' : '' }}{{ totalPnl() | number:'1.2-2' }}
            </div>
            <div class="pt-kpi-card__detail">
              Posizioni aperte: {{ livePositions().length }}
            </div>
          </c-card-body>
        </c-card>
      </c-col>
      <c-col sm="6" xl="3" class="animate-in stagger-4">
        <c-card class="mb-3 pt-kpi-card">
          <div class="pt-kpi-card__accent"
               [class.pt-kpi-card__accent--success]="(status()?.error_count ?? 0) === 0"
               [class.pt-kpi-card__accent--danger]="(status()?.error_count ?? 0) > 0"></div>
          <c-card-body class="ps-4">
            <div class="pt-kpi-card__label">Errori</div>
            <div class="pt-kpi-card__value"
                 [class.text-danger]="(status()?.error_count ?? 0) > 0">
              {{ status()?.error_count ?? 0 }}
            </div>
            <div class="pt-kpi-card__detail">
              @if (rejectedCount() > 0) {
                <span class="text-danger">{{ rejectedCount() }} segnali rifiutati</span>
              } @else {
                <span class="text-success">Nessun rifiuto</span>
              }
            </div>
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>

    <!-- ═══════ SECTION: Risk Management ═══════ -->
    @if (status()?.running) {
      <div class="section-divider">
        <span class="section-divider__label">Risk Management</span>
        <span class="section-divider__line"></span>
      </div>

      <c-row class="mb-4">
        <c-col sm="6" lg="3" class="animate-in stagger-1">
          <c-card class="h-100 border-top border-top-3 border-top-primary">
            <c-card-body class="py-2 d-flex justify-content-between align-items-center">
              <span class="text-body-secondary small">Circuit Breakers</span>
              @if (circuitBreakersTripped().length === 0) {
                <c-badge color="success" class="badge-sm">OK</c-badge>
              } @else {
                <div class="d-flex flex-wrap gap-1 justify-content-end align-items-center cb-badges">
                  @for (cb of circuitBreakersTripped(); track cb.key) {
                    <c-badge class="badge-sm cb-badge-warning" [cTooltip]="cb.reason">
                      <svg cIcon [name]="cb.icon" size="xs"></svg>
                      {{ cb.label }}
                    </c-badge>
                  }
                  <app-loading-button
                    color="warning"
                    size="sm"
                    [loading]="resetCbInProgress()"
                    (clicked)="resetCircuitBreakers()">
                    Reset
                  </app-loading-button>
                </div>
              }
            </c-card-body>
          </c-card>
        </c-col>
        <c-col sm="6" lg="3" class="animate-in stagger-2">
          <c-card class="h-100 border-top border-top-3 border-top-primary">
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
        <c-col sm="6" lg="3" class="animate-in stagger-3">
          <c-card class="h-100 border-top border-top-3 border-top-primary">
            <c-card-body class="py-2">
              <div class="d-flex justify-content-between align-items-center">
                <span class="text-body-secondary small">Kelly Sizing</span>
                @if (status()?.kelly_stats; as ks) {
                  <c-badge [color]="ks.active ? 'success' : 'warning'" class="badge-sm">
                    {{ ks.active ? 'Attivo' : ks.total_trades + '/' + ks.min_required }}
                  </c-badge>
                } @else {
                  <c-badge color="secondary" class="badge-sm">0 trade</c-badge>
                }
              </div>
              @if (status()?.kelly_stats; as ks) {
                <div class="mt-1 small text-body-secondary kelly-detail">
                  <span class="text-success">{{ ks.wins }}W</span> /
                  <span class="text-danger">{{ ks.losses }}L</span>
                  &middot; WR {{ (ks.win_rate * 100).toFixed(0) }}%
                  &middot; P&L <span [class]="ks.total_pnl >= 0 ? 'text-success' : 'text-danger'">
                    {{ (ks.total_pnl >= 0 ? '+' : '') + '$' + ks.total_pnl.toFixed(2) }}
                  </span>
                </div>
              }
            </c-card-body>
          </c-card>
        </c-col>
        <c-col sm="6" lg="3" class="animate-in stagger-4">
          <c-card class="h-100 border-top border-top-3 border-top-primary">
            <c-card-body class="py-2 d-flex justify-content-between align-items-center">
              <span class="text-body-secondary small">Trailing Stops</span>
              <strong class="text-primary">{{ status()?.trailing_stops_tracked ?? 0 }}</strong>
            </c-card-body>
          </c-card>
        </c-col>
      </c-row>
    }

    <!-- ═══════ SECTION: Posizioni & Segnali ═══════ -->
    <div class="section-divider">
      <span class="section-divider__label">Posizioni &amp; Segnali</span>
      <span class="section-divider__line"></span>
    </div>

    <c-row>
      <!-- Open Positions -->
      <c-col xl="7">
        <c-card class="mb-4 border-top border-top-3 border-top-primary">
          <c-card-header class="d-flex align-items-center justify-content-between py-2">
            <div class="d-flex align-items-center gap-2">
              <span class="fw-semibold small text-body-secondary">Posizioni Aperte</span>
              <c-badge color="info" class="mantis-badge-animated">{{ livePositions().length }}</c-badge>
            </div>
            @if (livePositions().length > 0) {
              <span class="mantis-mono fw-bold small"
                    [class.text-success]="totalPnl() >= 0"
                    [class.text-danger]="totalPnl() < 0">
                $ {{ totalPnl() >= 0 ? '+' : '' }}{{ totalPnl() | number:'1.2-2' }}
              </span>
            }
          </c-card-header>
          <c-card-body class="p-0">
            @if (groupedPositions().length > 0) {
              <div class="table-responsive-mobile">
                <table cTable [small]="true" class="mb-0 grouped-positions-table">
                  <thead>
                    <tr class="text-body-secondary">
                      <th class="fw-semibold small" style="width: 30px;"></th>
                      <th class="fw-semibold small">Asset</th>
                      <th class="fw-semibold small">Esposizione</th>
                      <th class="fw-semibold small d-mobile-none">Entry Medio</th>
                      <th class="fw-semibold small text-end">P&amp;L Totale</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (group of groupedPositions(); track group.epic) {
                      <!-- GROUP HEADER ROW -->
                      <tr class="group-header" [class.group-expanded]="group.expanded"
                          [class.pnl-row-positive]="group.totalPnl > 0"
                          [class.pnl-row-negative]="group.totalPnl < 0"
                          (click)="toggleGroup(group.epic)">
                        <td class="text-center">
                          <svg width="16" height="16" fill="currentColor" class="chevron-icon"
                               [class.rotated]="group.expanded">
                            <path d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/>
                          </svg>
                        </td>
                        <td class="fw-bold">
                          <div class="d-flex align-items-center gap-2">
                            <app-epic-logo [epic]="group.epic" [size]="28"></app-epic-logo>
                            <span>{{ group.epic }}</span>
                            @if (group.positions.length > 1) {
                              <c-badge color="primary" class="badge-sm ms-1">{{ group.positions.length }}x</c-badge>
                            }
                          </div>
                        </td>
                        <td>
                          <div class="d-flex align-items-center gap-2">
                            <c-badge [color]="directionColor(group.netDirection)" class="badge-sm">
                              {{ group.netDirection }}
                            </c-badge>
                            @if (getGroupRiskType(group) === 'local') {
                              <span class="risk-badge risk-badge--local risk-badge--slim"
                                    cTooltip="Risk gestito da MANTIS">L</span>
                            } @else if (getGroupRiskType(group) === 'broker') {
                              <span class="risk-badge risk-badge--broker risk-badge--slim"
                                    cTooltip="Risk gestito dal broker">B</span>
                            } @else {
                              <span class="risk-badge risk-badge--none risk-badge--slim"
                                    cTooltip="Nessun risk management!">!</span>
                            }
                            <span class="mantis-mono">{{ group.totalSize | number:'1.4-4' }}</span>
                          </div>
                        </td>
                        <td class="mantis-mono d-mobile-none">{{ group.avgEntry | priceFormat:group.epic }}</td>
                        <td class="text-end fw-bold mantis-mono"
                            [class.text-success]="group.totalPnl >= 0"
                            [class.text-danger]="group.totalPnl < 0">
                          $ {{ group.totalPnl >= 0 ? '+' : '' }}{{ group.totalPnl | number:'1.2-2' }}
                        </td>
                      </tr>

                      <!-- DETAIL ROWS (shown when expanded) -->
                      @if (group.expanded) {
                        @for (pos of group.positions; track pos.deal_id) {
                          <tr class="detail-row"
                              [class.pnl-row-positive]="pos.live_pnl > 0"
                              [class.pnl-row-negative]="pos.live_pnl < 0">
                            <td></td>
                            <td class="ps-4">
                              <div class="d-flex align-items-center gap-1">
                                <c-badge [color]="directionColor(pos.direction)" class="badge-sm">
                                  {{ pos.direction }}
                                </c-badge>
                                @if (pos.risk_managed_locally) {
                                  <span class="risk-badge risk-badge--local risk-badge--slim"
                                        cTooltip="Risk gestito da MANTIS">L</span>
                                } @else if (pos.stop_level !== null) {
                                  <span class="risk-badge risk-badge--broker risk-badge--slim"
                                        cTooltip="Risk gestito dal broker">B</span>
                                } @else {
                                  <span class="risk-badge risk-badge--none risk-badge--slim"
                                        cTooltip="Nessun risk management!">!</span>
                                }
                              </div>
                            </td>
                            <td class="mantis-mono small">{{ pos.size | number:'1.4-4' }}</td>
                            <td class="mantis-mono small d-mobile-none">{{ pos.level | priceFormat:pos.epic }}</td>
                            <td>
                              <div class="d-flex justify-content-end gap-2 small">
                                @if (getCurrentPrice(pos); as currentPrice) {
                                  <span class="mantis-mono fw-semibold"
                                        [class.text-success]="pos.live_pnl >= 0"
                                        [class.text-danger]="pos.live_pnl < 0">
                                    {{ currentPrice | priceFormat:pos.epic }}
                                  </span>
                                }
                                <span class="text-body-secondary">|</span>
                                <span class="mantis-mono">SL: {{ pos.stop_level !== null ? (pos.stop_level | priceFormat:pos.epic) : '—' }}</span>
                                <span class="text-body-secondary">|</span>
                                <span class="mantis-mono">TP: {{ pos.profit_level !== null ? (pos.profit_level | priceFormat:pos.epic) : '—' }}</span>
                                @if (pos.trailing_stop_phase) {
                                  <span class="text-body-secondary">|</span>
                                  <c-badge [color]="trailingPhaseColor(pos.trailing_stop_phase)" class="badge-sm">
                                    {{ pos.trailing_stop_phase }}
                                  </c-badge>
                                }
                                <span class="text-body-secondary">|</span>
                                <span class="mantis-mono fw-semibold"
                                      [class.text-success]="pos.live_pnl >= 0"
                                      [class.text-danger]="pos.live_pnl < 0">
                                  $ {{ pos.live_pnl >= 0 ? '+' : '' }}{{ pos.live_pnl | number:'1.2-2' }}
                                </span>
                              </div>
                            </td>
                          </tr>
                        }
                      }
                    }
                  </tbody>
                </table>
              </div>
            } @else {
              <div class="empty-state">
                <div class="empty-state__icon">📊</div>
                <div class="empty-state__text">Nessuna posizione aperta</div>
                <div class="empty-state__hint">Avvia il paper trading per aprire posizioni</div>
              </div>
            }
          </c-card-body>
        </c-card>
      </c-col>

      <!-- Last Signal per Asset -->
      <c-col xl="5">
        <c-card class="mb-4 border-top border-top-3 border-top-primary">
          <c-card-header class="py-2">
            <span class="fw-semibold small text-body-secondary">Ultimo Segnale per Asset</span>
          </c-card-header>
          <c-card-body class="p-0">
            @if (signalEntries().length > 0) {
              <div class="table-responsive-mobile">
                <table cTable [small]="true" [hover]="true" class="mb-0">
                  <thead>
                    <tr class="text-body-secondary">
                      <th class="fw-semibold small">Asset</th>
                      <th class="fw-semibold small">Dir</th>
                      <th class="fw-semibold small">Conf</th>
                      <th class="fw-semibold small">Ora</th>
                      <th class="fw-semibold small">Stato</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (s of signalEntries(); track s.epic) {
                      <tr>
                        <td class="fw-semibold">
                          <div class="d-flex align-items-center gap-2 epic-link" (click)="onEpicClick(s.epic)">
                            <app-epic-logo [epic]="s.epic" [size]="24"></app-epic-logo>
                            <span>{{ s.epic }}</span>
                          </div>
                        </td>
                        <td>
                          <c-badge [color]="directionColor(s.info.direction)" class="badge-sm">
                            {{ s.info.direction }}
                          </c-badge>
                        </td>
                        <td>
                          <div class="d-flex align-items-center gap-1">
                            <c-progress class="flex-grow-1 conf-bar-wrapper">
                              <c-progress-bar
                                [value]="s.info.confidence * 100"
                                [color]="s.info.confidence >= 0.5 ? 'success' : 'warning'">
                              </c-progress-bar>
                            </c-progress>
                            <small class="mantis-mono">{{ (s.info.confidence * 100).toFixed(0) }}%</small>
                          </div>
                        </td>
                        <td class="mantis-mono small">{{ formatTime(s.info.timestamp) }}</td>
                        <td>
                          @if (s.info.status) {
                            <span class="signal-status signal-status--{{ s.info.status }}">
                              <span class="signal-status__dot"></span>
                              {{ statusLabel(s.info.status) }}
                            </span>
                            @if (s.info.error_detail) {
                              <div class="text-body-secondary small mt-1 error-sub">
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
              </div>
            } @else {
              <div class="empty-state">
                <div class="empty-state__icon">🔔</div>
                <div class="empty-state__text">Nessun segnale generato</div>
                <div class="empty-state__hint">Avvia il paper trading per generare segnali</div>
              </div>
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>

    <!-- ═══════ SECTION: Modelli ═══════ -->
    <div class="section-divider">
      <span class="section-divider__label">Modelli</span>
      <span class="section-divider__line"></span>
    </div>

    <c-card class="mb-4 border-top border-top-3 border-top-primary">
      <c-card-header class="d-flex align-items-center gap-2 py-2">
        <span class="fw-semibold small text-body-secondary">Modelli Caricati</span>
        <c-badge color="primary" class="mantis-badge-animated">{{ modelEntries().length }}</c-badge>
      </c-card-header>
      <c-card-body class="p-0">
        @if (modelEntries().length > 0) {
          <div class="table-responsive-mobile">
            <table cTable [small]="true" [hover]="true" class="mb-0">
              <thead>
                <tr class="text-body-secondary">
                  <th class="fw-semibold small">Epic</th>
                  <th class="fw-semibold small">Tipo</th>
                  <th class="fw-semibold small">Features</th>
                  <th class="fw-semibold small d-mobile-none">Versione</th>
                  <th class="fw-semibold small d-mobile-none">Creato</th>
                </tr>
              </thead>
              <tbody>
                @for (m of modelEntries(); track m.epic) {
                  <tr>
                    <td class="fw-semibold">{{ m.epic }}</td>
                    <td><c-badge color="primary" class="badge-sm">{{ m.info.model_type }}</c-badge></td>
                    <td class="mantis-mono">{{ m.info.num_features }}</td>
                    <td class="d-mobile-none">{{ m.info.version }}</td>
                    <td class="text-body-secondary small d-mobile-none">{{ formatDate(m.info.created_at) }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <div class="empty-state">
            <div class="empty-state__icon">🤖</div>
            <div class="empty-state__text">Nessun modello caricato</div>
            <div class="empty-state__hint">Avvia il trading per caricare i modelli</div>
          </div>
        }
      </c-card-body>
    </c-card>

    <!-- ═══════ SECTION: Attivita Recente ═══════ -->
    <div class="section-divider">
      <span class="section-divider__label">Attivita Recente</span>
      <span class="section-divider__line"></span>
    </div>

    <c-card class="mb-4 border-top border-top-3 border-top-primary">
      <c-card-header class="d-flex align-items-center justify-content-between py-2">
        <div class="d-flex align-items-center gap-2">
          <span class="fw-semibold small text-body-secondary">Feed Segnali</span>
          <c-badge color="secondary" class="mantis-badge-animated">{{ recentSignals().length }}</c-badge>
          @if (rejectedCount() > 0) {
            <c-badge color="danger">{{ rejectedCount() }} rifiutati</c-badge>
          }
        </div>
        <span class="pt-chip pt-chip--muted">{{ (pollingInterval() / 1000) }}s</span>
      </c-card-header>
      <c-card-body class="p-0">
        @if (recentSignals().length > 0) {
          <div class="activity-scroll">
            <div class="table-responsive-mobile">
              <table cTable [small]="true" [hover]="true" class="mb-0">
                <thead class="sticky-thead">
                  <tr class="text-body-secondary">
                    <th class="fw-semibold small">Ora</th>
                    <th class="fw-semibold small">Asset</th>
                    <th class="fw-semibold small d-mobile-none">Strategia</th>
                    <th class="fw-semibold small">Dir</th>
                    <th class="fw-semibold small d-mobile-none">Conf</th>
                    <th class="fw-semibold small d-mobile-none">Prezzo</th>
                    <th class="fw-semibold small">Stato</th>
                    <th class="fw-semibold small d-mobile-none">Dettaglio</th>
                  </tr>
                </thead>
                <tbody>
                  @for (sig of recentSignals(); track sig.timestamp + sig.epic) {
                    <tr [class.table-danger]="sig.status === 'rejected' || sig.status === 'exec_failed'"
                        [class.table-secondary]="sig.status === 'market_closed'">
                      <td class="small text-body-secondary text-nowrap">{{ formatTime(sig.timestamp) }}</td>
                      <td class="fw-semibold">
                        <div class="d-flex align-items-center gap-2 epic-link" (click)="onEpicClick(sig.epic)">
                          <app-epic-logo [epic]="sig.epic" [size]="20"></app-epic-logo>
                          <span>{{ sig.epic }}</span>
                        </div>
                      </td>
                      <td class="d-mobile-none">
                        @if (sig.strategy_name) {
                          <c-badge [color]="strategyColor(sig.strategy_name)" class="badge-sm">
                            {{ strategyLabel(sig.strategy_name) }}
                          </c-badge>
                        } @else {
                          <span class="text-body-secondary">-</span>
                        }
                      </td>
                      <td>
                        <span class="dir-indicator dir-indicator--sm"
                              [class.dir-indicator--buy]="sig.direction === 'BUY'"
                              [class.dir-indicator--sell]="sig.direction === 'SELL'">
                          {{ sig.direction }}
                        </span>
                      </td>
                      <td class="mantis-mono small d-mobile-none">{{ (sig.confidence * 100).toFixed(0) }}%</td>
                      <td class="mantis-mono small d-mobile-none">{{ sig.entry_price | priceFormat:sig.epic }}</td>
                      <td>
                        <span class="signal-status signal-status--{{ sig.status }}">
                          <span class="signal-status__dot"></span>
                          {{ statusLabel(sig.status) }}
                        </span>
                      </td>
                      <td class="small detail-cell d-mobile-none">
                        @if (sig.error_detail) {
                          <div>
                            <span [class]="sig.status === 'market_closed' ? 'text-body-secondary' : 'text-danger'">
                              {{ sig.error_detail.summary }}
                            </span>
                            @if (sig.error_detail.details) {
                              <div class="text-body-secondary error-sub">
                                {{ sig.error_detail.details }}
                              </div>
                            }
                            <button class="raw-toggle-btn" (click)="toggleRaw(sig)">
                              {{ sig._showRaw ? 'Nascondi' : 'RAW' }}
                            </button>
                            @if (sig._showRaw) {
                              <pre class="bg-body-tertiary p-1 mt-1 rounded mb-0 raw-error-pre">{{ sig.error_detail.raw }}</pre>
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
          </div>
        } @else {
          <div class="empty-state">
            <div class="empty-state__icon">📋</div>
            <div class="empty-state__text">Nessun segnale recente</div>
            <div class="empty-state__hint">Avvia il paper trading per generare segnali</div>
          </div>
        }
      </c-card-body>
    </c-card>

    <!-- ═══════ NEWS MODAL (scoped) ═══════ -->
    @if (showNewsModal() && selectedEpic()) {
      <div class="pt-modal-backdrop" (click)="closeNewsModal()">
        <div class="pt-modal" (click)="$event.stopPropagation()">
          <div class="pt-modal__header">
            <div class="pt-modal__title">
              <app-epic-logo [epic]="selectedEpic()!" [size]="32"></app-epic-logo>
              <span>{{ selectedEpic() }} — Top News</span>
            </div>
            <button class="pt-modal__close" (click)="closeNewsModal()">&times;</button>
          </div>
          <div class="pt-modal__body">
            <app-news-widget [news]="newsService.news()" [maxItems]="10" />
          </div>
        </div>
      </div>
    }
  `
})
export class PaperTradingComponent implements OnInit, OnDestroy {
  readonly trading = inject(TradingService);
  readonly ws = inject(WebSocketService);
  readonly marketStatus = inject(MarketStatusService);
  readonly toast = inject(ToastService);
  readonly newsService = inject(NewsService);

  /** Circuit breaker type → Italian label + icon */
  readonly cbTypeMap: Record<string, { label: string; icon: string }> = {
    'daily_loss':         { label: 'Perdita Giornaliera',  icon: 'cilArrowBottom' },
    'consecutive_losses': { label: 'Perdite Consecutive',  icon: 'cilChartLine' },
    'max_positions':      { label: 'Max Posizioni',        icon: 'cilLayers' },
    'slippage_anomaly':   { label: 'Anomalia Slippage',    icon: 'cilBolt' },
    'heartbeat_timeout':  { label: 'Timeout Heartbeat',    icon: 'cilReload' },
    'volatility_spike':   { label: 'Spike Volatilita',     icon: 'cilChartPie' },
  };

  readonly actionInProgress = signal(false);
  readonly emergencyStopInProgress = signal(false);
  readonly resetCbInProgress = signal(false);
  readonly currentEpic = signal<string>('XAUUSD');
  readonly currentMarketStatus = signal<MarketStatusResponse | null>(null);
  readonly selectedEpic = signal<string | null>(null);
  readonly showNewsModal = signal(false);
  readonly expandedGroups = signal<Set<string>>(new Set());

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

  // Grouped positions by epic
  readonly groupedPositions = computed<GroupedPosition[]>(() => {
    const positions = this.livePositions();
    const groups = new Map<string, LivePosition[]>();

    // Group by epic
    positions.forEach(pos => {
      if (!groups.has(pos.epic)) {
        groups.set(pos.epic, []);
      }
      groups.get(pos.epic)!.push(pos);
    });

    // Convert to GroupedPosition array
    return Array.from(groups.entries()).map(([epic, epicPositions]) => {
      const totalSize = epicPositions.reduce((sum, p) => {
        return sum + (p.direction === 'BUY' ? p.size : -p.size);
      }, 0);

      const totalPnl = epicPositions.reduce((sum, p) => sum + p.live_pnl, 0);

      const buySize = epicPositions.filter(p => p.direction === 'BUY').reduce((sum, p) => sum + p.size, 0);
      const sellSize = epicPositions.filter(p => p.direction === 'SELL').reduce((sum, p) => sum + p.size, 0);

      const netDirection: 'LONG' | 'SHORT' | 'NEUTRAL' =
        Math.abs(buySize - sellSize) < 0.0001 ? 'NEUTRAL' :
        buySize > sellSize ? 'LONG' : 'SHORT';

      // Weighted average entry price
      const totalValue = epicPositions.reduce((sum, p) => sum + (p.level * p.size), 0);
      const totalVolume = epicPositions.reduce((sum, p) => sum + p.size, 0);
      const avgEntry = totalVolume > 0 ? totalValue / totalVolume : 0;

      const expanded = this.expandedGroups().has(epic);

      return {
        epic,
        positions: epicPositions,
        totalSize: Math.abs(totalSize),
        totalPnl,
        avgEntry,
        netDirection,
        expanded
      };
    }).sort((a, b) => b.totalPnl - a.totalPnl); // Sort by P&L descending
  });

  // Recent signals (latest 50)
  readonly recentSignals = computed(() => {
    return this.trading.paperSignals().slice(0, 50);
  });

  // Count of rejected signals in recent history
  readonly rejectedCount = computed(() => {
    return this.recentSignals().filter(s => s.status === 'rejected' || s.status === 'exec_failed').length;
  });

  // Phase 8: circuit breakers list (structured with Italian labels + icons)
  readonly circuitBreakersTripped = computed(() => {
    const raw = this.status()?.circuit_breakers_tripped;
    if (!raw || Array.isArray(raw)) return [];
    return Object.entries(raw).map(([key, reason]) => ({
      key,
      label: this.cbTypeMap[key]?.label ?? key,
      icon: this.cbTypeMap[key]?.icon ?? 'cilShieldAlt',
      reason: String(reason),
    }));
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

  emergencyStop(): void {
    const confirmed = window.confirm(
      'ATTENZIONE: Questo fermerà il trading e chiuderà TUTTE le posizioni aperte. Procedere?'
    );
    if (!confirmed) return;

    this.emergencyStopInProgress.set(true);
    this.trading.emergencyStop().subscribe({
      next: (data) => {
        this.toast.success(data.message);
        this.emergencyStopInProgress.set(false);
        this.loadAll();
      },
      error: (err) => {
        this.toast.error(err?.error?.error || 'Emergency stop fallito');
        this.emergencyStopInProgress.set(false);
      }
    });
  }

  resetCircuitBreakers(): void {
    const confirmed = window.confirm(
      'Resettare tutti i circuit breakers e i contatori perdite per-asset?'
    );
    if (!confirmed) return;

    this.resetCbInProgress.set(true);
    this.trading.resetCircuitBreakers().subscribe({
      next: (data) => {
        this.toast.success(data.message);
        this.resetCbInProgress.set(false);
        this.loadAll();
      },
      error: (err) => {
        this.toast.error(err?.error?.error || 'Reset circuit breakers fallito');
        this.resetCbInProgress.set(false);
      }
    });
  }

  toggleGroup(epic: string): void {
    const current = this.expandedGroups();
    const newSet = new Set(current);
    if (newSet.has(epic)) {
      newSet.delete(epic);
    } else {
      newSet.add(epic);
    }
    this.expandedGroups.set(newSet);
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
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit',
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

  onEpicClick(epic: string): void {
    this.selectedEpic.set(epic);
    this.showNewsModal.set(true);
    this.newsService.getNews(epic, 10, 7);
  }

  closeNewsModal(): void {
    this.showNewsModal.set(false);
    this.selectedEpic.set(null);
  }

  getGroupRiskType(group: GroupedPosition): 'broker' | 'local' | 'none' {
    const hasLocal = group.positions.some(p => p.risk_managed_locally);
    const hasBroker = group.positions.some(p => !p.risk_managed_locally && p.stop_level !== null);
    if (hasLocal) return 'local';
    if (hasBroker) return 'broker';
    return 'none';
  }

  getCurrentPrice(pos: LivePosition): number | null {
    const tick = this.ws.prices()[pos.epic];
    if (!tick) return null;
    return pos.direction === 'BUY' ? tick.bid : tick.offer;
  }
}
