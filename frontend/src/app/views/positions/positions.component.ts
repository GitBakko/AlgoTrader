import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective,
  BadgeComponent, ButtonDirective
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { TradingService } from '../../core/services/trading.service';

@Component({
  selector: 'app-positions',
  standalone: true,
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective, BadgeComponent, ButtonDirective,
    IconDirective
  ],
  template: `
    <c-row>
      <c-col xs="12">
        <c-card class="mb-4">
          <c-card-header><strong>Open Positions</strong></c-card-header>
          <c-card-body>
            @if (positions().length === 0) {
              <p class="text-body-secondary">No open positions</p>
            } @else {
              <table cTable striped hover>
                <thead>
                  <tr>
                    <th>Epic</th>
                    <th>Direction</th>
                    <th>Size</th>
                    <th>Entry Price</th>
                    <th>Stop Loss</th>
                    <th>Take Profit</th>
                    <th>P&L</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  @for (pos of positions(); track pos.deal_id) {
                    <tr>
                      <td><strong>{{ pos.epic }}</strong></td>
                      <td>
                        <c-badge [color]="pos.direction === 'BUY' ? 'success' : 'danger'">
                          {{ pos.direction }}
                        </c-badge>
                      </td>
                      <td>{{ pos.size }}</td>
                      <td>{{ pos.entry_price | number:'1.2-2' }}</td>
                      <td>{{ pos.stop_loss ?? '-' }}</td>
                      <td>{{ pos.take_profit ?? '-' }}</td>
                      <td [class]="pos.current_pnl >= 0 ? 'text-success' : 'text-danger'">
                        {{ pos.current_pnl | number:'1.2-2' }}
                      </td>
                      <td>
                        <button cButton color="danger" size="sm" (click)="closePosition(pos.deal_id)">
                          Close
                        </button>
                      </td>
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
export class PositionsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  readonly positions = this.trading.positions;

  ngOnInit(): void {
    this.trading.loadPositions();
  }

  closePosition(dealId: string): void {
    this.trading.closePosition(dealId).subscribe(() => {
      this.trading.loadPositions();
    });
  }
}
