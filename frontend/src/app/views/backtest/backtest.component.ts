import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective,
  ButtonDirective, FormControlDirective, FormLabelDirective,
  FormSelectDirective, InputGroupComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { BacktestRun } from '../../core/models';

@Component({
  selector: 'app-backtest',
  standalone: true,
  imports: [
    CommonModule, FormsModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective, ButtonDirective,
    FormControlDirective, FormLabelDirective, FormSelectDirective, InputGroupComponent
  ],
  template: `
    <c-row>
      <c-col md="4">
        <c-card class="mb-4">
          <c-card-header><strong>Run Backtest</strong></c-card-header>
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
              <label cFormLabel>Initial Equity</label>
              <input cFormControl type="number" [(ngModel)]="config.initial_equity" />
            </div>
            <div class="mb-3">
              <label cFormLabel>Risk per Trade</label>
              <input cFormControl type="number" step="0.01" [(ngModel)]="config.risk_per_trade" />
            </div>
            <button cButton color="primary" (click)="runBacktest()" [disabled]="running">
              {{ running ? 'Running...' : 'Run Backtest' }}
            </button>
          </c-card-body>
        </c-card>
      </c-col>
      <c-col md="8">
        <c-card class="mb-4">
          <c-card-header><strong>Results</strong></c-card-header>
          <c-card-body>
            @if (runs.length === 0) {
              <p class="text-body-secondary">No backtest runs yet</p>
            } @else {
              <table cTable striped hover>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Epic</th>
                    <th>Status</th>
                    <th>Return %</th>
                    <th>Sharpe</th>
                    <th>Max DD %</th>
                    <th>Trades</th>
                    <th>Win Rate</th>
                  </tr>
                </thead>
                <tbody>
                  @for (run of runs; track run.id) {
                    <tr>
                      <td>{{ run.id }}</td>
                      <td>{{ run.epic }}</td>
                      <td>{{ run.status }}</td>
                      <td>{{ run.total_return_pct ?? 0 | number:'1.2-2' }}%</td>
                      <td>{{ run.sharpe_ratio ?? 0 | number:'1.2-2' }}</td>
                      <td>{{ run.max_drawdown_pct ?? 0 | number:'1.2-2' }}%</td>
                      <td>{{ run.total_trades ?? 0 }}</td>
                      <td>{{ run.win_rate ?? 0 | number:'1.0-0' }}%</td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>
  `
})
export class BacktestComponent {
  private readonly trading = inject(TradingService);
  runs: BacktestRun[] = [];
  running = false;
  config = { epic: 'XAUUSD', initial_equity: 10000, risk_per_trade: 0.02 };

  constructor() {
    this.loadRuns();
  }

  runBacktest(): void {
    this.running = true;
    this.trading.runBacktest(this.config).subscribe({
      next: () => {
        this.running = false;
        this.loadRuns();
      },
      error: () => this.running = false
    });
  }

  loadRuns(): void {
    this.trading.listBacktestRuns().subscribe(data => this.runs = data);
  }
}
