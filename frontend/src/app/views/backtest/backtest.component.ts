import { Component, OnInit, inject, signal, ChangeDetectorRef } from '@angular/core';
import { CommonModule, DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective,
  ButtonDirective, FormControlDirective, FormLabelDirective,
  FormSelectDirective, BadgeComponent, SpinnerComponent,
  AlertComponent, ProgressComponent
} from '@coreui/angular';
import { ChartjsComponent } from '@coreui/angular-chartjs';
import { TradingService } from '../../core/services/trading.service';
import { BacktestRun, BacktestDetail } from '../../core/models';

@Component({
  selector: 'app-backtest',
  standalone: true,
  imports: [
    CommonModule, FormsModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective, ButtonDirective,
    FormControlDirective, FormLabelDirective, FormSelectDirective,
    BadgeComponent, SpinnerComponent, ChartjsComponent, AlertComponent,
    ProgressComponent
  ],
  template: `
    <!-- Success / Error alerts -->
    @if (successMsg()) {
      <c-alert color="success" class="mb-3" (visibleChange)="successMsg.set('')" [dismissible]="true">
        {{ successMsg() }}
      </c-alert>
    }
    @if (errorMsg()) {
      <c-alert color="danger" class="mb-3" (visibleChange)="errorMsg.set('')" [dismissible]="true">
        {{ errorMsg() }}
      </c-alert>
    }

    <c-row>
      <!-- Config Panel -->
      <c-col md="4">
        <c-card class="mb-4">
          <c-card-header><strong>Configura Backtest</strong></c-card-header>
          <c-card-body>
            <div class="mb-3">
              <label cFormLabel>Asset</label>
              <select cFormSelect [(ngModel)]="config.epic">
                <option value="XAUUSD">Gold (XAUUSD)</option>
                <option value="BTCUSD">Bitcoin (BTCUSD)</option>
                <option value="US500">S&P 500 (US500)</option>
              </select>
            </div>
            <div class="mb-3">
              <label cFormLabel>Timeframe</label>
              <select cFormSelect [(ngModel)]="config.timeframe">
                <option value="1h">1 Hour</option>
                <option value="4h">4 Hours</option>
                <option value="1d">1 Day</option>
              </select>
            </div>
            <div class="mb-3">
              <label cFormLabel>Capitale Iniziale ($)</label>
              <input cFormControl type="number" [(ngModel)]="config.initial_equity" />
            </div>
            <div class="mb-3">
              <label cFormLabel>Rischio per Trade (%)</label>
              <input cFormControl type="number" step="0.01" [(ngModel)]="config.risk_per_trade" />
            </div>
            <button cButton color="primary" (click)="runBacktest()" [disabled]="running()" class="w-100">
              @if (running()) {
                <c-spinner size="sm" class="me-2"></c-spinner> Backtest in corso...
              } @else {
                Avvia Backtest
              }
            </button>
            <div class="text-body-secondary small mt-2 text-center">
              Analizza tutti i dati storici disponibili per l'asset selezionato
            </div>
          </c-card-body>
        </c-card>
      </c-col>

      <!-- Results List -->
      <c-col md="8">
        <c-card class="mb-4">
          <c-card-header>
            <strong>Backtest Eseguiti</strong>
            @if (runs().length > 0) {
              <span class="float-end text-body-secondary small">{{ runs().length }} run</span>
            }
          </c-card-header>
          <c-card-body>
            @if (runs().length === 0 && !running()) {
              <p class="text-body-secondary mb-0">Nessun backtest eseguito. Configura i parametri e avvia un backtest.</p>
            } @else if (runs().length === 0 && running()) {
              <div class="text-center py-3">
                <c-spinner color="primary"></c-spinner>
                <p class="text-body-secondary mt-2 mb-0">Generazione segnali ML e simulazione in corso...</p>
              </div>
            } @else {
              <table cTable striped hover>
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>TF</th>
                    <th>Periodo</th>
                    <th>Return</th>
                    <th>Sharpe</th>
                    <th>Trades</th>
                    <th>Win Rate</th>
                  </tr>
                </thead>
                <tbody>
                  @for (run of runs(); track run.id) {
                    <tr (click)="selectRun(run)" [class.table-active]="selectedRun()?.id === run.id" style="cursor: pointer;">
                      <td><strong>{{ run.epic }}</strong></td>
                      <td>{{ getRunTimeframe(run) }}</td>
                      <td class="text-body-secondary small">{{ getRunPeriod(run) }}</td>
                      <td [class]="(run.total_return_pct ?? 0) >= 0 ? 'text-success fw-semibold' : 'text-danger fw-semibold'">
                        {{ run.total_return_pct ?? 0 >= 0 ? '+' : '' }}{{ run.total_return_pct ?? 0 | number:'1.2-2' }}%
                      </td>
                      <td>{{ run.sharpe_ratio ?? 0 | number:'1.2-2' }}</td>
                      <td>{{ run.total_trades ?? 0 }}</td>
                      <td>{{ run.win_rate ?? 0 | number:'1.1-1' }}%</td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>

    <!-- Detail View -->
    @if (detail()) {
      <!-- Summary Banner -->
      <c-card class="mb-4 border-start border-start-4 border-start-primary">
        <c-card-body class="py-3">
          <c-row class="align-items-center">
            <c-col md="4">
              <div class="fs-5 fw-semibold">{{ detail()!.summary.epic }} / {{ detail()!.config['timeframe'] ?? '1h' }}</div>
              <div class="text-body-secondary small">
                {{ formatDate(getStartDate()) }} &rarr; {{ formatDate(getEndDate()) }}
                ({{ detail()!.equity_curve.length | number:'1.0-0' }} barre)
              </div>
            </c-col>
            <c-col md="4" class="text-center">
              <div class="text-body-secondary small">Capitale</div>
              <div class="fs-5">
                <span>$</span>{{ getInitialEquity() | number:'1.0-0' }}
                &rarr;
                <span [class]="getFinalEquity() >= getInitialEquity() ? 'text-success fw-semibold' : 'text-danger fw-semibold'">
                  <span>$</span>{{ getFinalEquity() | number:'1.0-0' }}
                </span>
              </div>
            </c-col>
            <c-col md="4" class="text-end">
              <div [class]="(detail()!.summary.total_return_pct ?? 0) >= 0 ? 'text-success' : 'text-danger'"
                   style="font-size: 1.8rem; font-weight: 700; line-height: 1;">
                {{ (detail()!.summary.total_return_pct ?? 0) >= 0 ? '+' : '' }}{{ detail()!.summary.total_return_pct ?? 0 | number:'1.2-2' }}%
              </div>
              <div class="text-body-secondary small">
                Annualizzato: {{ (detail()!.metrics['annualized_return'] ?? 0) * 100 | number:'1.1-1' }}%
              </div>
            </c-col>
          </c-row>
        </c-card-body>
      </c-card>

      <!-- Risk Metrics Row -->
      <c-row>
        @for (card of riskCards(); track card.label) {
          <c-col md="3" sm="6">
            <c-card class="mb-4">
              <c-card-body class="text-center py-3">
                <div class="text-body-secondary small text-uppercase mb-1">{{ card.label }}</div>
                <div class="fs-4 fw-semibold" [class]="card.colorClass">{{ card.value }}</div>
              </c-card-body>
            </c-card>
          </c-col>
        }
      </c-row>

      <!-- Trade Metrics Row -->
      <c-row>
        @for (card of tradeCards(); track card.label) {
          <c-col md="3" sm="6">
            <c-card class="mb-4">
              <c-card-body class="text-center py-3">
                <div class="text-body-secondary small text-uppercase mb-1">{{ card.label }}</div>
                <div class="fs-4 fw-semibold" [class]="card.colorClass">{{ card.value }}</div>
              </c-card-body>
            </c-card>
          </c-col>
        }
      </c-row>

      <!-- Equity Curve -->
      <c-row>
        <c-col xs="12">
          <c-card class="mb-4">
            <c-card-header>
              <strong>Equity Curve</strong>
              <span class="float-end text-body-secondary small">
                {{ formatDate(getStartDate()) }} &mdash; {{ formatDate(getEndDate()) }}
              </span>
            </c-card-header>
            <c-card-body>
              @if (equityChartData()) {
                <c-chart type="line" [data]="equityChartData()!" [options]="equityChartOptions" style="height: 320px;"></c-chart>
              }
            </c-card-body>
          </c-card>
        </c-col>
      </c-row>

      <!-- Trades Table -->
      <c-row>
        <c-col xs="12">
          <c-card class="mb-4">
            <c-card-header>
              <strong>Lista Trade</strong>
              <span class="float-end">
                <c-badge color="success" class="me-1">{{ detail()!.trade_metrics['winning_trades'] ?? 0 }} win</c-badge>
                <c-badge color="danger" class="me-1">{{ detail()!.trade_metrics['losing_trades'] ?? 0 }} loss</c-badge>
                <span class="text-body-secondary small ms-1">| Fees totali: <span>$</span>{{ getTotalFees() | number:'1.2-2' }}</span>
              </span>
            </c-card-header>
            <c-card-body>
              @if (detail()!.trades.length > 0) {
                <div style="max-height: 400px; overflow-y: auto;">
                  <table cTable striped hover class="small">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Dir</th>
                        <th>Entry Time</th>
                        <th>Entry Price</th>
                        <th>Exit Time</th>
                        <th>Exit Price</th>
                        <th>Size</th>
                        <th>Status</th>
                        <th>Net P&L</th>
                        <th>Bars</th>
                      </tr>
                    </thead>
                    <tbody>
                      @for (trade of detail()!.trades; track trade.trade_id) {
                        <tr>
                          <td class="text-body-secondary">{{ trade.trade_id }}</td>
                          <td>
                            <c-badge [color]="trade.direction === 'LONG' ? 'success' : 'danger'" class="badge-sm">
                              {{ trade.direction === 'LONG' ? 'BUY' : 'SELL' }}
                            </c-badge>
                          </td>
                          <td>{{ formatDateTime(trade.entry_time) }}</td>
                          <td>{{ trade.entry_price | number:'1.2-2' }}</td>
                          <td>{{ trade.exit_time ? formatDateTime(trade.exit_time) : '-' }}</td>
                          <td>{{ trade.exit_price ? (trade.exit_price | number:'1.2-2') : '-' }}</td>
                          <td>{{ trade.size | number:'1.4-4' }}</td>
                          <td>
                            <c-badge [color]="getStatusColor(trade.status)" class="badge-sm">
                              {{ getStatusLabel(trade.status) }}
                            </c-badge>
                          </td>
                          <td [class]="trade.net_pnl >= 0 ? 'text-success fw-semibold' : 'text-danger fw-semibold'">
                            {{ trade.net_pnl >= 0 ? '+' : '' }}{{ trade.net_pnl | number:'1.2-2' }}
                          </td>
                          <td class="text-body-secondary">{{ trade.bars_held }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              } @else {
                <p class="text-body-secondary mb-0">Nessun trade generato in questo backtest</p>
              }
            </c-card-body>
          </c-card>
        </c-col>
      </c-row>
    }
  `
})
export class BacktestComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly cdr = inject(ChangeDetectorRef);

  readonly runs = signal<BacktestRun[]>([]);
  readonly running = signal(false);
  readonly selectedRun = signal<BacktestRun | null>(null);
  readonly detail = signal<BacktestDetail | null>(null);
  readonly equityChartData = signal<any>(null);
  readonly errorMsg = signal('');
  readonly successMsg = signal('');
  readonly riskCards = signal<MetricCard[]>([]);
  readonly tradeCards = signal<MetricCard[]>([]);

  // Maps run.id → config info for display in the table
  private runConfigs = new Map<string, { timeframe: string; startDate: string; endDate: string }>();

  config = { epic: 'XAUUSD', timeframe: '1h', initial_equity: 10000, risk_per_trade: 0.02 };

  equityChartOptions: any = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx: any) => `$${ctx.parsed.y.toFixed(2)}`
        }
      }
    },
    scales: {
      x: {
        display: true,
        ticks: { maxTicksLimit: 12, color: '#9da5b4' },
        grid: { color: 'rgba(255,255,255,0.05)' },
      },
      y: {
        display: true,
        ticks: {
          color: '#9da5b4',
          callback: (v: number) => `$${v.toLocaleString()}`
        },
        grid: { color: 'rgba(255,255,255,0.05)' },
      },
    },
  };

  ngOnInit(): void {
    this.loadRuns();
  }

  runBacktest(): void {
    this.running.set(true);
    this.detail.set(null);
    this.selectedRun.set(null);
    this.errorMsg.set('');
    this.successMsg.set('');
    this.riskCards.set([]);
    this.tradeCards.set([]);
    this.equityChartData.set(null);

    this.trading.runBacktest(this.config).subscribe({
      next: (run) => {
        this.running.set(false);
        // Store config for this run
        this.runConfigs.set(run.id, {
          timeframe: this.config.timeframe,
          startDate: '',
          endDate: ''
        });
        this.runs.update(prev => [run, ...prev]);
        this.selectedRun.set(run);
        this.selectRunById(run.id);
      },
      error: (err) => {
        this.running.set(false);
        const msg = err?.error?.error || err?.message || 'Errore durante il backtest';
        this.errorMsg.set(msg);
        this.cdr.detectChanges();
      }
    });
  }

  loadRuns(): void {
    this.trading.listBacktestRuns().subscribe({
      next: (data) => {
        this.runs.set(data);
        this.cdr.detectChanges();
      },
      error: () => {}
    });
  }

  selectRun(run: BacktestRun): void {
    this.selectedRun.set(run);
    this.selectRunById(run.id);
  }

  selectRunById(runId: string): void {
    this.trading.getBacktestDetail(runId).subscribe({
      next: (data) => {
        this.detail.set(data);
        this.selectedRun.set(data.summary);

        // Cache config/period info for table display
        const ec = data.equity_curve;
        if (ec.length > 0) {
          this.runConfigs.set(runId, {
            timeframe: (data.config['timeframe'] as string) ?? '1h',
            startDate: ec[0].timestamp,
            endDate: ec[ec.length - 1].timestamp
          });
        }

        this.buildMetricCards(data);
        this.buildEquityChart(data.equity_curve);

        const ret = data.summary.total_return_pct ?? 0;
        const trades = data.summary.total_trades ?? 0;
        this.successMsg.set(
          `Backtest completato: ${data.summary.epic} ${(data.config['timeframe'] ?? '1h')} | ` +
          `${this.formatDate(this.getStartDate())} \u2192 ${this.formatDate(this.getEndDate())} | ` +
          `${trades} trade, return ${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`
        );

        this.cdr.detectChanges();
      },
      error: () => {
        this.errorMsg.set('Errore nel caricamento dei dettagli del backtest');
        this.cdr.detectChanges();
      }
    });
  }

  // --- Helpers for table display ---

  getRunTimeframe(run: BacktestRun): string {
    return this.runConfigs.get(run.id)?.timeframe ?? '-';
  }

  getRunPeriod(run: BacktestRun): string {
    const info = this.runConfigs.get(run.id);
    if (!info || !info.startDate) {
      // Fallback: show created_at date
      return this.formatDate(run.created_at);
    }
    return `${this.formatDateShort(info.startDate)} \u2192 ${this.formatDateShort(info.endDate)}`;
  }

  // --- Helpers for detail view ---

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
    const d = new Date(iso);
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  formatDateShort(iso: string): string {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('it-IT', { month: 'short', year: '2-digit' });
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

    this.riskCards.set([
      { label: 'Sharpe Ratio', value: (m['sharpe_ratio'] ?? 0).toFixed(2), colorClass: '' },
      { label: 'Sortino Ratio', value: (m['sortino_ratio'] ?? 0).toFixed(2), colorClass: '' },
      { label: 'Calmar Ratio', value: (m['calmar_ratio'] ?? 0).toFixed(2), colorClass: '' },
      { label: 'Max Drawdown', value: ((m['max_drawdown'] ?? 0) * 100).toFixed(2) + '%', colorClass: 'text-danger' },
    ]);

    this.tradeCards.set([
      { label: 'Win Rate', value: ((tm['win_rate'] ?? 0) * 100).toFixed(1) + '%', colorClass: '' },
      { label: 'Profit Factor', value: (tm['profit_factor'] ?? 0).toFixed(2), colorClass: '' },
      { label: 'Avg Win', value: '$' + (tm['avg_win'] ?? 0).toFixed(2), colorClass: 'text-success' },
      { label: 'Avg Loss', value: '$' + (tm['avg_loss'] ?? 0).toFixed(2), colorClass: 'text-danger' },
    ]);
  }

  buildEquityChart(equityCurve: { timestamp: string; equity: number }[]): void {
    if (!equityCurve || equityCurve.length === 0) {
      this.equityChartData.set(null);
      return;
    }

    let data = equityCurve;
    if (data.length > 500) {
      const step = Math.ceil(data.length / 500);
      data = data.filter((_, i) => i % step === 0);
    }

    this.equityChartData.set({
      labels: data.map(p => {
        const d = new Date(p.timestamp);
        return d.toLocaleDateString('it-IT', { month: 'short', year: '2-digit' });
      }),
      datasets: [{
        label: 'Equity',
        data: data.map(p => p.equity),
        borderColor: '#3399ff',
        backgroundColor: 'rgba(51, 153, 255, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      }],
    });
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
}

interface MetricCard {
  label: string;
  value: string;
  colorClass: string;
}
