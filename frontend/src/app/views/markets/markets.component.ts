import { Component, ChangeDetectionStrategy, inject, OnInit, OnDestroy, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, TableDirective, BadgeComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { WebSocketService } from '../../core/services/websocket.service';

@Component({
  selector: 'app-markets',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, TableDirective, BadgeComponent
  ],
  template: `
    <!-- Header -->
    <div class="d-flex align-items-center justify-content-between mb-3 px-1">
      <div class="d-flex align-items-center gap-2">
        <h5 class="mb-0 fw-semibold">Mercati</h5>
        @if (wsConnected()) {
          <c-badge color="success" class="badge-sm">WS Live</c-badge>
        } @else {
          <c-badge color="danger" class="badge-sm">WS Offline</c-badge>
        }
      </div>
      <span class="text-body-secondary small">{{ markets().length }} asset</span>
    </div>

    <!-- Live Prices from WebSocket -->
    @if (livePrices().length > 0) {
      <c-row class="mb-4">
        @for (p of livePrices(); track p.epic) {
          <c-col sm="6" md="4" lg="3" class="mb-3">
            <c-card class="h-100">
              <c-card-body class="py-2 d-flex justify-content-between align-items-center">
                <div>
                  <div class="fw-semibold">{{ p.epic }}</div>
                  <div class="text-body-secondary small">Spread: {{ p.spread | number:'1.2-5' }}</div>
                </div>
                <div class="text-end">
                  <div class="font-monospace fw-semibold">{{ p.mid | number:'1.2-2' }}</div>
                  <div class="text-body-secondary small font-monospace">
                    {{ p.bid | number:'1.2-2' }} / {{ p.offer | number:'1.2-2' }}
                  </div>
                </div>
              </c-card-body>
            </c-card>
          </c-col>
        }
      </c-row>
    }

    <!-- Markets Table -->
    <c-card class="mb-4">
      <c-card-header class="py-2"><strong>Elenco Mercati</strong></c-card-header>
      <c-card-body class="p-0">
        @if (markets().length > 0) {
          <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0">
            <thead>
              <tr>
                <th>Epic</th>
                <th>Nome</th>
                <th class="text-end">Bid</th>
                <th class="text-end">Offer</th>
                <th class="text-end">High</th>
                <th class="text-end">Low</th>
                <th class="text-end">Change %</th>
              </tr>
            </thead>
            <tbody>
              @for (m of markets(); track m.epic) {
                <tr>
                  <td class="fw-semibold">{{ m.epic }}</td>
                  <td>{{ m.name }}</td>
                  <td class="text-end font-monospace">{{ m.bid != null ? (m.bid | number:'1.2-2') : '—' }}</td>
                  <td class="text-end font-monospace">{{ m.offer != null ? (m.offer | number:'1.2-2') : '—' }}</td>
                  <td class="text-end font-monospace">{{ m.high != null ? (m.high | number:'1.2-2') : '—' }}</td>
                  <td class="text-end font-monospace">{{ m.low != null ? (m.low | number:'1.2-2') : '—' }}</td>
                  <td class="text-end font-monospace"
                      [class.text-success]="m.change_pct != null && m.change_pct >= 0"
                      [class.text-danger]="m.change_pct != null && m.change_pct < 0">
                    {{ m.change_pct != null ? ((m.change_pct >= 0 ? '+' : '') + (m.change_pct | number:'1.2-2') + '%') : '—' }}
                  </td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <div class="text-center py-5 text-body-secondary small">
            Nessun mercato disponibile. Connetti il backend per caricare i dati.
          </div>
        }
      </c-card-body>
    </c-card>
  `
})
export class MarketsComponent implements OnInit, OnDestroy {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  readonly markets = this.trading.markets;
  readonly wsConnected = this.ws.connected;

  readonly livePrices = computed(() => {
    const prices = this.ws.prices();
    const epics = ['XAUUSD', 'BTCUSD', 'US500', 'WTIUSD', 'NVDA', 'TSLA', 'XAGUSD', 'DE40'];
    return epics
      .filter(e => prices[e])
      .map(e => {
        const t = prices[e];
        return { epic: e, bid: t.bid, offer: t.offer, mid: (t.bid + t.offer) / 2, spread: t.offer - t.bid };
      });
  });

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.trading.loadMarkets();
    this.ws.connectPrices();
    this.pollTimer = setInterval(() => this.trading.loadMarkets(), 60_000);
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
}
