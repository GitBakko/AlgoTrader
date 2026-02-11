import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective,
  BadgeComponent, ButtonDirective, ProgressComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';

@Component({
  selector: 'app-signals',
  standalone: true,
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective, BadgeComponent,
    ButtonDirective, ProgressComponent
  ],
  template: `
    <c-row>
      <c-col xs="12">
        <c-card class="mb-4">
          <c-card-header>
            <strong>Trading Signals</strong>
            <button cButton color="primary" size="sm" class="float-end" (click)="generateTestSignal()">
              Generate Test Signal
            </button>
          </c-card-header>
          <c-card-body>
            @if (signals().length === 0) {
              <p class="text-body-secondary">No signals generated yet</p>
            } @else {
              <table cTable striped hover>
                <thead>
                  <tr>
                    <th>Epic</th>
                    <th>Direction</th>
                    <th>Confidence</th>
                    <th>Entry Price</th>
                    <th>Stop</th>
                    <th>Take Profit</th>
                    <th>Regime</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  @for (sig of signals(); track sig.timestamp) {
                    <tr>
                      <td><strong>{{ sig.epic }}</strong></td>
                      <td>
                        <c-badge [color]="getDirectionColor(sig.direction)">
                          {{ sig.direction }}
                        </c-badge>
                      </td>
                      <td>
                        <c-progress [value]="sig.confidence * 100" [color]="getConfidenceColor(sig.confidence)" style="height: 8px;"></c-progress>
                        <small>{{ (sig.confidence * 100) | number:'1.0-0' }}%</small>
                      </td>
                      <td>{{ sig.entry_price | number:'1.2-2' }}</td>
                      <td>{{ sig.suggested_stop ? (sig.suggested_stop | number:'1.2-2') : '-' }}</td>
                      <td>{{ sig.suggested_tp ? (sig.suggested_tp | number:'1.2-2') : '-' }}</td>
                      <td>{{ sig.regime ?? 'N/A' }}</td>
                      <td>{{ sig.timestamp | date:'short' }}</td>
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
export class SignalsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  readonly signals = this.trading.signals;

  ngOnInit(): void {
    this.trading.loadSignals();
  }

  generateTestSignal(): void {
    this.trading.generateSignal('XAUUSD').subscribe(() => {
      this.trading.loadSignals();
    });
  }

  getDirectionColor(dir: string): string {
    if (dir === 'BUY') return 'success';
    if (dir === 'SELL') return 'danger';
    return 'secondary';
  }

  getConfidenceColor(conf: number): string {
    if (conf >= 0.8) return 'success';
    if (conf >= 0.6) return 'warning';
    return 'danger';
  }
}
