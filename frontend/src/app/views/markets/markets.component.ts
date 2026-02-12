import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';

@Component({
  selector: 'app-markets',
  standalone: true,
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective
  ],
  template: `
    <c-row>
      <c-col xs="12">
        <c-card class="mb-4">
          <c-card-header><strong>Markets</strong></c-card-header>
          <c-card-body>
            <table cTable striped hover>
              <thead>
                <tr>
                  <th>Epic</th>
                  <th>Name</th>
                  <th>Bid</th>
                  <th>Offer</th>
                  <th>Change %</th>
                </tr>
              </thead>
              <tbody>
                @for (market of markets(); track market.epic) {
                  <tr>
                    <td><strong>{{ market.epic }}</strong></td>
                    <td>{{ market.name }}</td>
                    <td>{{ market.bid ?? '-' }}</td>
                    <td>{{ market.offer ?? '-' }}</td>
                    <td>{{ market.change_pct != null ? (market.change_pct | number:'1.2-2') + '%' : '-' }}</td>
                  </tr>
                }
              </tbody>
            </table>
            @if (!wsConnected()) {
              <p class="text-body-secondary mt-3">
                Live prices via WebSocket will be available when connected to the backend.
              </p>
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>
  `
})
export class MarketsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  readonly markets = this.trading.markets;
  readonly wsConnected = this.ws.connected;

  ngOnInit(): void {
    this.trading.loadMarkets();
  }
}
