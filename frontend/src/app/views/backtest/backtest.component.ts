import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective,
  ButtonDirective, FormControlDirective,
  BadgeComponent, SpinnerComponent,
} from '@coreui/angular';
import { TvChartComponent, LineDataPoint } from '../../shared/components/tv-chart/tv-chart.component';
import { TradingService } from '../../core/services/trading.service';
import { ToastService } from '../../shared/services/toast.service';
import { BacktestRun, BacktestDetail } from '../../core/models';

@Component({
  selector: 'app-backtest',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './backtest.component.scss',
  imports: [
    CommonModule, FormsModule, DecimalPipe,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective, ButtonDirective,
    FormControlDirective,
    BadgeComponent, SpinnerComponent,
    TvChartComponent
  ],
  template: `
    <!-- ═══════ ROW 1: Header ═══════ -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <h5 class="mb-0 fw-semibold">Backtest Engine</h5>
      @if (runs().length > 0) {
        <span class="text-body-secondary small">{{ runs().length }} run salvati</span>
      }
    </div>

    <c-row>
      <!-- ═══════ Config Panel ═══════ -->
      <c-col lg="3">
        <c-card class="mb-4 border-top border-top-3 border-top-primary">
          <c-card-header class="py-2"><span class="fw-semibold small text-body-secondary">Configurazione</span></c-card-header>
          <c-card-body>
            <div class="mb-3">
              <label cFormLabel class="small">Asset</label>
              <select cFormSelect [(ngModel)]="config.epic" class="form-select-sm">
                <!-- Existing 8 assets (EURUSD excluded) -->
                <option value="XAUUSD">Gold (XAUUSD)</option>
                <option value="BTCUSD">Bitcoin (BTCUSD)</option>
                <option value="US500">S&P 500 (US500)</option>
                <option value="WTIUSD">Oil (WTIUSD)</option>
                <option value="NVDA">NVIDIA (NVDA)</option>
                <option value="TSLA">Tesla (TSLA)</option>
                <option value="XAGUSD">Silver (XAGUSD)</option>
                <option value="DE40">DAX (DE40)</option>
                <!-- New 12 assets - Phase 12: Portfolio Expansion -->
                <option value="SOLUSD">Solana (SOLUSD)</option>
                <option value="ETHUSD">Ethereum (ETHUSD)</option>
                <option value="BNBUSD">Binance Coin (BNBUSD)</option>
                <option value="DOGUSD">Dogecoin (DOGUSD)</option>
                <option value="DASHUSD">Dash (DASHUSD)</option>
                <option value="ICPUSD">Internet Computer (ICPUSD)</option>
                <option value="NATGAS">Natural Gas (NATGAS)</option>
                <option value="COPPER">Copper (COPPER)</option>
                <option value="PLATINUM">Platinum (PLATINUM)</option>
                <option value="GBPUSD">GBP/USD (GBPUSD)</option>
                <option value="USDJPY">USD/JPY (USDJPY)</option>
                <option value="NAS100">Nasdaq 100 (NAS100)</option>
              </select>
            </div>
            <div class="mb-3">
              <label cFormLabel class="small">Timeframe</label>
              <select cFormSelect [(ngModel)]="config.timeframe" class="form-select-sm">
                <option value="1h">1 Hour</option>
                <option value="4h">4 Hours</option>
                <option value="1d">1 Day</option>
              </select>
            </div>
            <div class="mb-3">
              <label cFormLabel class="small">Capitale ($)</label>
              <input cFormControl type="number" [(ngModel)]="config.initial_equity" class="form-control-sm" />
            </div>
            <div class="mb-3">
              <label cFormLabel class="small">Rischio/Trade (%)</label>
              <input cFormControl type="number" step="0.01" [(ngModel)]="config.risk_per_trade" class="form-control-sm" />
            </div>
            <div class="mb-3">
              <label cFormLabel class="small">Strategia</label>
              <select cFormSelect [(ngModel)]="config.strategy" class="form-select-sm">
                <option value="ml_ensemble">ML Ensemble</option>
                <option value="squeeze_breakout">Squeeze Breakout</option>
                <option value="vwap_reversion">VWAP Reversion</option>
                <option value="auto">Auto (Router)</option>
              </select>
            </div>
            <button cButton color="primary" size="sm" (click)="runBacktest()" [disabled]="running()" class="w-100">
              @if (running()) {
                <c-spinner size="sm" class="me-1"></c-spinner> In corso...
              } @else {
                Avvia Backtest
              }
            </button>
          </c-card-body>
        </c-card>
      </c-col>

      <!-- ═══════ Results List ═══════ -->
      <c-col lg="9">
        <c-card class="mb-4 border-top border-top-3 border-top-primary">
          <c-card-header class="py-2"><span class="fw-semibold small text-body-secondary">Risultati</span></c-card-header>
          <c-card-body class="p-0">
            @if (runs().length === 0 && !running()) {
              <div class="empty-state">
                <div class="empty-state__text">Nessun backtest eseguito</div>
                <div class="empty-state__hint">Configura i parametri e avvia un backtest.</div>
              </div>
            } @else if (runs().length === 0 && running()) {
              <div class="text-center py-4">
                <c-spinner color="primary" size="sm"></c-spinner>
                <p class="text-body-secondary mt-2 mb-0 small">Generazione segnali ML e simulazione...</p>
              </div>
            } @else {
              <div class="table-responsive-mobile">
                <table cTable [small]="true" [hover]="true" class="mb-0">
                  <thead>
                    <tr>
                      <th class="text-center" style="width: 36px">
                        <span class="small text-body-secondary" title="Confronta">VS</span>
                      </th>
                      <th>Asset</th>
                      <th class="d-mobile-none">TF</th>
                      <th class="d-mobile-none">Periodo</th>
                      <th class="text-end">Return</th>
                      <th class="text-end d-mobile-none">Sharpe</th>
                      <th class="text-end">Trades</th>
                      <th class="text-end">Win Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (run of runs(); track run.id) {
                      <tr class="bt-result-row" (click)="selectRun(run)" [class.table-active]="selectedRun()?.id === run.id">
                        <td class="text-center" (click)="toggleComparison(run.id, $event)">
                          <input type="checkbox" class="form-check-input" [checked]="isSelectedForComparison(run.id)" />
                        </td>
                        <td class="fw-semibold">{{ run.epic }}</td>
                        <td class="d-mobile-none">{{ getRunTimeframe(run) }}</td>
                        <td class="text-body-secondary small d-mobile-none">{{ getRunPeriod(run) }}</td>
                        <td class="text-end fw-semibold mantis-mono"
                            [class.text-success]="(run.total_return_pct ?? 0) >= 0"
                            [class.text-danger]="(run.total_return_pct ?? 0) < 0">
                          {{ (run.total_return_pct ?? 0) >= 0 ? '+' : '' }}{{ run.total_return_pct ?? 0 | number:'1.2-2' }}%
                        </td>
                        <td class="text-end mantis-mono d-mobile-none">{{ run.sharpe_ratio ?? 0 | number:'1.2-2' }}</td>
                        <td class="text-end">{{ run.total_trades ?? 0 }}</td>
                        <td class="text-end mantis-mono">{{ run.win_rate ?? 0 | number:'1.1-1' }}%</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>

    <!-- ═══════ Detail View ═══════ -->
    @if (detail()) {
      <!-- Summary Banner -->
      <c-card class="mb-4 border-top border-top-3 border-top-primary">
        <c-card-body class="py-3">
          <c-row class="align-items-center">
            <c-col md="3">
              <div class="fs-5 fw-semibold">{{ detail()!.summary.epic }}</div>
              <div class="text-body-secondary small">
                {{ detail()!.config['timeframe'] ?? '1h' }} |
                {{ formatDate(getStartDate()) }} &rarr; {{ formatDate(getEndDate()) }}
              </div>
            </c-col>
            <c-col md="3" class="text-center">
              <div class="text-body-secondary small">Capitale</div>
              <div class="fs-6">
                $ {{ getInitialEquity() | number:'1.0-0' }}
                &rarr;
                <strong [class.text-success]="getFinalEquity() >= getInitialEquity()"
                        [class.text-danger]="getFinalEquity() < getInitialEquity()">
                  $ {{ getFinalEquity() | number:'1.0-0' }}
                </strong>
              </div>
            </c-col>
            <c-col md="3" class="text-center">
              <div class="text-body-secondary small">Trade</div>
              <div class="fs-6">
                {{ detail()!.summary.total_trades ?? 0 }}
                <span class="text-body-secondary small">
                  ({{ detail()!.equity_curve.length | number:'1.0-0' }} barre)
                </span>
              </div>
            </c-col>
            <c-col md="3" class="text-end">
              <div class="bt-hero-value"
                   [class.text-success]="(detail()!.summary.total_return_pct ?? 0) >= 0"
                   [class.text-danger]="(detail()!.summary.total_return_pct ?? 0) < 0">
                {{ (detail()!.summary.total_return_pct ?? 0) >= 0 ? '+' : '' }}{{ detail()!.summary.total_return_pct ?? 0 | number:'1.2-2' }}%
              </div>
              <div class="text-body-secondary small">
                Ann: {{ detail()!.metrics['annualized_return'] * 100 | number:'1.1-1' }}%
              </div>
            </c-col>
          </c-row>
        </c-card-body>
      </c-card>

      <!-- Risk + Trade Metric Cards -->
      <c-row>
        @for (card of metricCards(); track card.label) {
          <c-col lg="2" md="3" sm="4" class="col-6">
            <c-card class="mb-3">
              <c-card-body class="text-center py-2">
                <div class="bt-stat-label">{{ card.label }}</div>
                <div class="fs-5 fw-semibold" [class]="card.colorClass">{{ card.value }}</div>
              </c-card-body>
            </c-card>
          </c-col>
        }
      </c-row>

      <!-- Monte Carlo Validation -->
      @if (detail()!.monte_carlo) {
        <c-card class="mb-4 border-top border-top-3 border-top-info">
          <c-card-header class="d-flex align-items-center justify-content-between py-2">
            <span class="fw-semibold small text-body-secondary">Monte Carlo Validation</span>
            <span class="text-body-secondary small">
              {{ detail()!.monte_carlo!.n_simulations | number:'1.0-0' }} sim,
              {{ detail()!.monte_carlo!.n_trades | number:'1.0-0' }} trade
            </span>
          </c-card-header>
          <c-card-body class="py-3">
            <c-row>
              <c-col md="3" sm="6" class="mb-2 mb-md-0">
                <div class="bt-stat-label mb-1">Equity 95% CI</div>
                <div class="fw-semibold">
                  $ {{ detail()!.monte_carlo!.final_equity.p5 | number:'1.0-0' }}
                  &mdash; $ {{ detail()!.monte_carlo!.final_equity.p95 | number:'1.0-0' }}
                </div>
                <div class="text-body-secondary small">
                  Med: $ {{ detail()!.monte_carlo!.final_equity.p50 | number:'1.0-0' }}
                </div>
              </c-col>
              <c-col md="3" sm="6" class="mb-2 mb-md-0">
                <div class="bt-stat-label mb-1">Max DD 95% CI</div>
                <div class="fw-semibold text-danger">
                  {{ (detail()!.monte_carlo!.max_drawdown.p5 * 100) | number:'1.1-1' }}%
                  &mdash; {{ (detail()!.monte_carlo!.max_drawdown.p95 * 100) | number:'1.1-1' }}%
                </div>
              </c-col>
              <c-col md="2" sm="4" class="mb-2 mb-md-0">
                <div class="bt-stat-label mb-1">Sharpe CI</div>
                <div class="fw-semibold">
                  {{ detail()!.monte_carlo!.sharpe_ratio.p5 | number:'1.2-2' }}
                  &mdash; {{ detail()!.monte_carlo!.sharpe_ratio.p95 | number:'1.2-2' }}
                </div>
              </c-col>
              <c-col md="2" sm="4">
                <div class="bt-stat-label mb-1">P-Value</div>
                <c-badge [color]="pValueColor(detail()!.monte_carlo!.p_value_return)">
                  {{ detail()!.monte_carlo!.p_value_return | number:'1.4-4' }}
                </c-badge>
                <div class="text-body-secondary small">
                  {{ detail()!.monte_carlo!.p_value_return < 0.05 ? 'Significativo' : 'Non signif.' }}
                </div>
              </c-col>
              <c-col md="2" sm="4">
                <div class="bt-stat-label mb-1">Risk of Ruin</div>
                <div class="fs-5 fw-semibold"
                     [class.text-danger]="detail()!.monte_carlo!.risk_of_ruin > 0.1"
                     [class.text-success]="detail()!.monte_carlo!.risk_of_ruin <= 0.1">
                  {{ (detail()!.monte_carlo!.risk_of_ruin * 100) | number:'1.1-1' }}%
                </div>
              </c-col>
            </c-row>
          </c-card-body>
        </c-card>
      }

      <!-- Equity Curve (TradingView) -->
      <c-card class="mb-4 border-top border-top-3 border-top-primary">
        <c-card-header class="d-flex align-items-center justify-content-between py-2">
          <span class="fw-semibold small text-body-secondary">Equity Curve</span>
          <span class="text-body-secondary small">
            {{ formatDate(getStartDate()) }} &mdash; {{ formatDate(getEndDate()) }}
          </span>
        </c-card-header>
        <c-card-body class="p-0">
          @if (equityLineData().length > 0) {
            <app-tv-chart
              mode="area"
              [lineData]="equityLineData()"
              [height]="320"
              lineColor="#00d97e"
              areaTopColor="rgba(0, 217, 126, 0.20)"
              areaBottomColor="rgba(0, 217, 126, 0.01)"
            ></app-tv-chart>
          } @else {
            <div class="empty-state">
              <div class="empty-state__text">Nessun dato equity disponibile</div>
            </div>
          }
        </c-card-body>
      </c-card>

      <!-- Trades Table -->
      <c-card class="mb-4 border-top border-top-3 border-top-primary">
        <c-card-header class="d-flex align-items-center justify-content-between py-2">
          <div class="d-flex align-items-center">
            <span class="fw-semibold small text-body-secondary">Lista Trade</span>
            <c-badge color="success" class="ms-2">{{ detail()!.trade_metrics['winning_trades'] }} W</c-badge>
            <c-badge color="danger" class="ms-1">{{ detail()!.trade_metrics['losing_trades'] }} L</c-badge>
          </div>
          <span class="text-body-secondary small">Fees: $ {{ getTotalFees() | number:'1.2-2' }}</span>
        </c-card-header>
        <c-card-body class="p-0">
          @if (detail()!.trades.length > 0) {
            <div class="bt-trades-scroll">
              <div class="table-responsive-mobile">
                <table cTable [small]="true" [hover]="true" class="mb-0">
                  <thead class="bt-sticky-thead">
                    <tr>
                      <th>#</th>
                      <th>Dir</th>
                      <th class="d-mobile-none">Entry Time</th>
                      <th>Entry</th>
                      <th class="d-mobile-none">Exit Time</th>
                      <th>Exit</th>
                      <th class="d-mobile-none">Size</th>
                      <th>Status</th>
                      <th class="text-end">Net P&amp;L</th>
                      <th class="text-end d-mobile-none">Bars</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (trade of detail()!.trades; track trade.trade_id) {
                      <tr>
                        <td class="text-body-secondary">{{ trade.trade_id }}</td>
                        <td>
                          <span class="dir-indicator" [class.dir-indicator--buy]="trade.direction === 'LONG'" [class.dir-indicator--sell]="trade.direction !== 'LONG'">
                            {{ trade.direction === 'LONG' ? 'BUY' : 'SELL' }}
                          </span>
                        </td>
                        <td class="small text-body-secondary d-mobile-none">{{ formatDateTime(trade.entry_time) }}</td>
                        <td class="mantis-mono">{{ trade.entry_price | number:'1.2-2' }}</td>
                        <td class="small text-body-secondary d-mobile-none">{{ formatDateTime(trade.exit_time!) }}</td>
                        <td class="mantis-mono">
                          @if (trade.exit_price) {
                            {{ trade.exit_price | number:'1.2-2' }}
                          } @else {
                            <span class="text-body-secondary">-</span>
                          }
                        </td>
                        <td class="mantis-mono small d-mobile-none">{{ trade.size | number:'1.4-4' }}</td>
                        <td>
                          <c-badge [color]="getStatusColor(trade.status)" class="badge-sm">
                            {{ getStatusLabel(trade.status) }}
                          </c-badge>
                        </td>
                        <td class="text-end fw-semibold mantis-mono"
                            [class.text-success]="trade.net_pnl >= 0"
                            [class.text-danger]="trade.net_pnl < 0">
                          $ {{ trade.net_pnl >= 0 ? '+' : '' }}{{ trade.net_pnl | number:'1.2-2' }}
                        </td>
                        <td class="text-end text-body-secondary small d-mobile-none">{{ trade.bars_held }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            </div>
          } @else {
            <div class="empty-state">
              <div class="empty-state__text">Nessun trade generato in questo backtest</div>
            </div>
          }
        </c-card-body>
      </c-card>
    }

    <!-- ═══════ Comparison Panel ═══════ -->
    @if (comparisonRuns().length >= 2) {
      <div class="section-divider">
        <span class="section-divider__label">Confronto Run ({{ comparisonRuns().length }})</span>
        <div class="section-divider__line"></div>
      </div>
      <c-card class="mb-4 border-top border-top-3 border-top-info">
        <c-card-header class="d-flex align-items-center justify-content-between py-2">
          <span class="fw-semibold small text-body-secondary">Confronto Metriche</span>
          <button class="btn btn-sm btn-outline-secondary" (click)="clearComparison()">
            Chiudi confronto
          </button>
        </c-card-header>
        <c-card-body class="p-0">
          <div class="table-responsive-mobile">
            <table cTable [small]="true" class="mb-0 bt-comparison-table">
              <thead>
                <tr>
                  <th class="bt-comparison-metric-col">Metrica</th>
                  @for (run of comparisonRuns(); track run.summary.id) {
                    <th class="text-center">
                      <div class="fw-semibold">{{ run.summary.epic }}</div>
                      <div class="text-body-secondary small">{{ run.config['timeframe'] ?? '1h' }}</div>
                    </th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (metric of comparisonMetrics; track metric.key) {
                  <tr>
                    <td class="text-body-secondary small">{{ metric.label }}</td>
                    @for (run of comparisonRuns(); track run.summary.id) {
                      <td class="text-center mantis-mono fw-semibold" [class]="getComparisonValueClass(run, metric)">
                        {{ getComparisonValue(run, metric) }}
                      </td>
                    }
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </c-card-body>
      </c-card>
    } @else if (selectedForComparison().length === 1) {
      <div class="text-center text-body-secondary small py-2">
        Seleziona almeno 2 run per confrontarli ({{ selectedForComparison().length }}/4)
      </div>
    }
  `
})
export class BacktestComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);

  readonly runs = signal<BacktestRun[]>([]);
  readonly running = signal(false);
  readonly selectedRun = signal<BacktestRun | null>(null);
  readonly detail = signal<BacktestDetail | null>(null);
  readonly metricCards = signal<MetricCard[]>([]);

  // Comparison feature
  readonly selectedForComparison = signal<string[]>([]);
  readonly comparisonDetails = signal<Map<string, BacktestDetail>>(new Map());
  readonly comparisonRuns = computed<BacktestDetail[]>(() => {
    const ids = this.selectedForComparison();
    const details = this.comparisonDetails();
    return ids.map(id => details.get(id)).filter((d): d is BacktestDetail => !!d);
  });

  // Equity curve for TvChart
  readonly equityLineData = computed<LineDataPoint[]>(() => {
    const d = this.detail();
    if (!d?.equity_curve?.length) return [];
    let data = d.equity_curve;
    if (data.length > 800) {
      const step = Math.ceil(data.length / 800);
      data = data.filter((_, i) => i % step === 0);
    }
    return data.map(p => ({
      time: p.timestamp?.substring(0, 10) || '',
      value: p.equity,
    }));
  });

  private runConfigs = new Map<string, { timeframe: string; startDate: string; endDate: string }>();

  config = { epic: 'XAUUSD', timeframe: '1h', initial_equity: 10000, risk_per_trade: 0.02, strategy: 'ml_ensemble' };

  ngOnInit(): void {
    const epicParam = this.route.snapshot.queryParamMap.get('epic');
    if (epicParam) {
      this.config.epic = epicParam;
    }
    this.loadRuns();
  }

  runBacktest(): void {
    this.running.set(true);
    this.detail.set(null);
    this.selectedRun.set(null);
    this.metricCards.set([]);

    this.trading.runBacktest(this.config).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (run) => {
        this.running.set(false);
        this.runConfigs.set(run.id, { timeframe: this.config.timeframe, startDate: '', endDate: '' });
        this.runs.update(prev => [run, ...prev]);
        this.selectedRun.set(run);
        this.selectRunById(run.id);
      },
      error: (err) => {
        this.running.set(false);
        this.toast.error(err?.error?.error || err?.message || 'Errore durante il backtest');
      }
    });
  }

  loadRuns(): void {
    this.trading.listBacktestRuns().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => this.runs.set(data),
      error: () => {}
    });
  }

  selectRun(run: BacktestRun): void {
    this.selectedRun.set(run);
    this.selectRunById(run.id);
  }

  selectRunById(runId: string): void {
    this.trading.getBacktestDetail(runId).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        this.detail.set(data);
        this.selectedRun.set(data.summary);

        const ec = data.equity_curve;
        if (ec.length > 0) {
          this.runConfigs.set(runId, {
            timeframe: (data.config['timeframe'] as string) ?? '1h',
            startDate: ec[0].timestamp,
            endDate: ec[ec.length - 1].timestamp
          });
        }

        this.buildMetricCards(data);

        const ret = data.summary.total_return_pct ?? 0;
        const trades = data.summary.total_trades ?? 0;
        this.toast.success(
          `${data.summary.epic} ${data.config['timeframe'] ?? '1h'}: ${trades} trade, ${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`
        );
      },
      error: () => {
        this.toast.error('Errore nel caricamento dei dettagli');
      }
    });
  }

  getRunTimeframe(run: BacktestRun): string {
    return this.runConfigs.get(run.id)?.timeframe ?? '-';
  }

  getRunPeriod(run: BacktestRun): string {
    const info = this.runConfigs.get(run.id);
    if (!info || !info.startDate) return this.formatDate(run.created_at);
    return `${this.formatDateShort(info.startDate)} \u2192 ${this.formatDateShort(info.endDate)}`;
  }

  getStartDate(): string {
    const ec = this.detail()?.equity_curve;
    return ec && ec.length > 0 ? ec[0].timestamp : '';
  }

  getEndDate(): string {
    const ec = this.detail()?.equity_curve;
    return ec && ec.length > 0 ? ec[ec.length - 1].timestamp : '';
  }

  getInitialEquity(): number {
    return +(this.detail()?.config['initial_equity'] ?? 10000);
  }

  getFinalEquity(): number {
    const ec = this.detail()?.equity_curve;
    return ec && ec.length > 0 ? ec[ec.length - 1].equity : 0;
  }

  getTotalFees(): number {
    return +(this.detail()?.trade_metrics['total_fees'] ?? 0);
  }

  formatDate(iso: string): string {
    if (!iso) return '-';
    return new Date(iso).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  formatDateShort(iso: string): string {
    if (!iso) return '-';
    return new Date(iso).toLocaleDateString('it-IT', { month: 'short', year: '2-digit' });
  }

  formatDateTime(iso: string): string {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: '2-digit' })
      + ' ' + d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  }

  buildMetricCards(data: BacktestDetail): void {
    const m = data.metrics;
    const tm = data.trade_metrics;
    this.metricCards.set([
      { label: 'Sharpe', value: (m['sharpe_ratio'] ?? 0).toFixed(2), colorClass: '' },
      { label: 'Sortino', value: (m['sortino_ratio'] ?? 0).toFixed(2), colorClass: '' },
      { label: 'Calmar', value: (m['calmar_ratio'] ?? 0).toFixed(2), colorClass: '' },
      { label: 'Max DD', value: ((m['max_drawdown'] ?? 0) * 100).toFixed(2) + '%', colorClass: 'text-danger' },
      { label: 'Win Rate', value: ((tm['win_rate'] ?? 0) * 100).toFixed(1) + '%', colorClass: '' },
      { label: 'Profit Factor', value: (tm['profit_factor'] ?? 0).toFixed(2), colorClass: '' },
      { label: 'Avg Win', value: '$ ' + (tm['avg_win'] ?? 0).toFixed(2), colorClass: 'text-success' },
      { label: 'Avg Loss', value: '$ ' + (tm['avg_loss'] ?? 0).toFixed(2), colorClass: 'text-danger' },
    ]);
  }

  getStatusColor(status: string): string {
    if (status === 'closed_tp') return 'success';
    if (status === 'closed_sl') return 'danger';
    if (status === 'closed_signal') return 'info';
    return 'secondary';
  }

  getStatusLabel(status: string): string {
    if (status === 'closed_tp') return 'TP';
    if (status === 'closed_sl') return 'SL';
    if (status === 'closed_signal') return 'Signal';
    return status;
  }

  pValueColor(pValue: number): string {
    if (pValue < 0.05) return 'success';
    if (pValue < 0.10) return 'warning';
    return 'danger';
  }

  toggleComparison(runId: string, event: Event): void {
    event.stopPropagation();
    const current = this.selectedForComparison();
    if (current.includes(runId)) {
      this.selectedForComparison.set(current.filter(id => id !== runId));
    } else {
      if (current.length >= 4) {
        this.toast.error('Massimo 4 run confrontabili');
        return;
      }
      this.selectedForComparison.set([...current, runId]);
      this.loadComparisonDetail(runId);
    }
  }

  isSelectedForComparison(runId: string): boolean {
    return this.selectedForComparison().includes(runId);
  }

  clearComparison(): void {
    this.selectedForComparison.set([]);
    this.comparisonDetails.set(new Map());
  }

  private loadComparisonDetail(runId: string): void {
    if (this.comparisonDetails().has(runId)) return;
    this.trading.getBacktestDetail(runId).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (data) => {
        this.comparisonDetails.update(map => {
          const newMap = new Map(map);
          newMap.set(runId, data);
          return newMap;
        });
      },
      error: () => {}
    });
  }

  readonly comparisonMetrics = [
    { key: 'total_return_pct', label: 'Return %', type: 'summary', format: 'pct' },
    { key: 'sharpe_ratio', label: 'Sharpe', type: 'metrics', format: 'dec2' },
    { key: 'sortino_ratio', label: 'Sortino', type: 'metrics', format: 'dec2' },
    { key: 'calmar_ratio', label: 'Calmar', type: 'metrics', format: 'dec2' },
    { key: 'max_drawdown', label: 'Max DD', type: 'metrics', format: 'pct_neg' },
    { key: 'win_rate', label: 'Win Rate', type: 'trade_metrics', format: 'pct' },
    { key: 'profit_factor', label: 'Profit Factor', type: 'trade_metrics', format: 'dec2' },
    { key: 'total_trades', label: 'Trades', type: 'summary', format: 'int' },
  ];

  getComparisonValue(detail: BacktestDetail, metric: { key: string; type: string; format: string }): string {
    let val: number;
    if (metric.type === 'summary') {
      val = (detail.summary as unknown as Record<string, number>)[metric.key] ?? 0;
    } else if (metric.type === 'metrics') {
      val = detail.metrics[metric.key] ?? 0;
    } else {
      val = detail.trade_metrics[metric.key] ?? 0;
    }
    if (metric.format === 'pct') return (val * (metric.key === 'total_return_pct' ? 1 : 100)).toFixed(2) + '%';
    if (metric.format === 'pct_neg') return (val * 100).toFixed(2) + '%';
    if (metric.format === 'dec2') return val.toFixed(2);
    return val.toFixed(0);
  }

  getComparisonValueClass(detail: BacktestDetail, metric: { key: string; type: string }): string {
    let val: number;
    if (metric.type === 'summary') {
      val = (detail.summary as unknown as Record<string, number>)[metric.key] ?? 0;
    } else if (metric.type === 'metrics') {
      val = detail.metrics[metric.key] ?? 0;
    } else {
      val = detail.trade_metrics[metric.key] ?? 0;
    }
    if (metric.key === 'max_drawdown') return val > 0.1 ? 'text-danger' : '';
    if (metric.key === 'total_trades') return '';
    return val > 0 ? 'text-success' : val < 0 ? 'text-danger' : '';
  }
}

interface MetricCard {
  label: string;
  value: string;
  colorClass: string;
}
