import { Component, ChangeDetectionStrategy, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent,
  FormCheckComponent, FormCheckInputDirective, FormCheckLabelDirective,
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { SystemSettings, RiskStatus } from '../../core/models';
import { WebSocketService } from '../../core/services/websocket.service';
import { NotificationService } from '../../shared/services/notification.service';

const ASSET_INFO: { epic: string; name: string; type: string; exchange: string }[] = [
  // Existing 9 assets
  { epic: 'XAUUSD', name: 'Gold', type: 'Commodity', exchange: 'COMEX' },
  { epic: 'XAGUSD', name: 'Silver', type: 'Commodity', exchange: 'COMEX' },
  { epic: 'WTIUSD', name: 'Crude Oil WTI', type: 'Commodity', exchange: 'NYMEX' },
  { epic: 'BTCUSD', name: 'Bitcoin', type: 'Crypto', exchange: '24/7' },
  { epic: 'EURUSD', name: 'EUR/USD', type: 'Forex', exchange: '24/5' },
  { epic: 'US500', name: 'S&P 500', type: 'Index', exchange: 'CME' },
  { epic: 'DE40', name: 'DAX 40', type: 'Index', exchange: 'EUREX' },
  { epic: 'NVDA', name: 'NVIDIA', type: 'Stock CFD', exchange: 'NASDAQ' },
  { epic: 'TSLA', name: 'Tesla', type: 'Stock CFD', exchange: 'NASDAQ' },
  // New 12 assets - Phase 12: Portfolio Expansion
  { epic: 'SOLUSD', name: 'Solana', type: 'Crypto', exchange: '24/7' },
  { epic: 'ETHUSD', name: 'Ethereum', type: 'Crypto', exchange: '24/7' },
  { epic: 'BNBUSD', name: 'Binance Coin', type: 'Crypto', exchange: '24/7' },
  { epic: 'DOGUSD', name: 'Dogecoin', type: 'Crypto', exchange: '24/7' },
  { epic: 'DASHUSD', name: 'Dash', type: 'Crypto', exchange: '24/7' },
  { epic: 'ICPUSD', name: 'Internet Computer', type: 'Crypto', exchange: '24/7' },
  { epic: 'NATGAS', name: 'Natural Gas', type: 'Commodity', exchange: 'NYMEX' },
  { epic: 'COPPER', name: 'Copper', type: 'Commodity', exchange: 'COMEX' },
  { epic: 'PLATINUM', name: 'Platinum', type: 'Commodity', exchange: 'NYMEX' },
  { epic: 'GBPUSD', name: 'GBP/USD', type: 'Forex', exchange: '24/5' },
  { epic: 'USDJPY', name: 'USD/JPY', type: 'Forex', exchange: '24/5' },
  { epic: 'NAS100', name: 'Nasdaq 100', type: 'Index', exchange: 'CME' },
];

@Component({
  selector: 'app-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent,
    FormCheckComponent, FormCheckInputDirective, FormCheckLabelDirective,
  ],
  template: `
    <!-- Header -->
    <h5 class="mb-3 fw-semibold px-1">Sistema</h5>

    <c-row>
      <!-- System Info -->
      <c-col lg="4">
        <c-card class="mb-4">
          <c-card-header class="py-2"><strong>Configurazione</strong></c-card-header>
          <c-card-body class="p-0">
            @if (settings) {
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">App</span>
                <strong class="small">{{ settings.app_name }} v{{ settings.app_version }}</strong>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Ambiente</span>
                <c-badge color="info" class="badge-sm">{{ settings.environment }}</c-badge>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Trading</span>
                <c-badge [color]="settings.trading_enabled ? 'success' : 'danger'" class="badge-sm">
                  {{ settings.trading_enabled ? 'Attivo' : 'Disattivato' }}
                </c-badge>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Modalita</span>
                <c-badge [color]="settings.paper_trading ? 'warning' : 'success'" class="badge-sm">
                  {{ settings.paper_trading ? 'Paper' : 'Live' }}
                </c-badge>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Broker</span>
                <c-badge [color]="settings.use_demo ? 'warning' : 'danger'" class="badge-sm">
                  {{ settings.use_demo ? 'Demo' : 'Live' }}
                </c-badge>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between">
                <span class="text-body-secondary small">WebSocket</span>
                <c-badge [color]="wsConnected() ? 'success' : 'danger'" class="badge-sm">
                  {{ wsConnected() ? 'Connesso' : 'Disconnesso' }}
                </c-badge>
              </div>
            } @else {
              <div class="text-center py-4 text-body-secondary small">Caricamento...</div>
            }
          </c-card-body>
        </c-card>
      </c-col>

      <!-- Risk Params + Notifications -->
      <c-col lg="4">
        <c-card class="mb-4">
          <c-card-header class="py-2"><strong>Parametri Rischio</strong></c-card-header>
          <c-card-body class="p-0">
            @if (settings) {
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Min Confidence</span>
                <strong class="small font-monospace">{{ (settings.min_confidence_threshold * 100) | number:'1.0-0' }}%</strong>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Max Risk/Trade</span>
                <strong class="small font-monospace">{{ (settings.max_risk_per_trade * 100) | number:'1.1-1' }}%</strong>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Max Daily DD</span>
                <strong class="small font-monospace text-warning">{{ (settings.max_daily_drawdown * 100) | number:'1.1-1' }}%</strong>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between">
                <span class="text-body-secondary small">Max Total DD</span>
                <strong class="small font-monospace text-danger">{{ (settings.max_total_drawdown * 100) | number:'1.1-1' }}%</strong>
              </div>
            }
          </c-card-body>
        </c-card>

        <!-- Notifications -->
        <c-card class="mb-4">
          <c-card-header class="py-2"><strong>Notifiche</strong></c-card-header>
          <c-card-body>
            <c-form-check class="mb-2">
              <input cFormCheckInput type="checkbox" id="notifBrowser"
                     [checked]="notifications.enabled()"
                     (change)="toggleBrowserNotifications()"/>
              <label cFormCheckLabel for="notifBrowser" class="small">Notifiche browser (trade, circuit breaker)</label>
            </c-form-check>
            <c-form-check>
              <input cFormCheckInput type="checkbox" id="notifSound"
                     [checked]="notifications.soundEnabled()"
                     (change)="notifications.toggleSound()"/>
              <label cFormCheckLabel for="notifSound" class="small">Suoni alert (chime su trade)</label>
            </c-form-check>
          </c-card-body>
        </c-card>
      </c-col>

      <!-- Risk Status Live -->
      <c-col lg="4">
        <c-card class="mb-4 border-top border-top-3"
                [class.border-top-danger]="riskStatus?.circuit_breaker_active"
                [class.border-top-success]="riskStatus && !riskStatus.circuit_breaker_active">
          <c-card-header class="py-2"><strong>Risk Status Live</strong></c-card-header>
          <c-card-body>
            @if (riskStatus) {
              <div class="d-flex justify-content-between mb-3">
                <span class="text-body-secondary small">Equity (USD)</span>
                <strong>$ {{ riskStatus.current_equity | number:'1.2-2' }}</strong>
              </div>
              <div class="d-flex justify-content-between mb-3">
                <span class="text-body-secondary small">Peak (USD)</span>
                <strong>$ {{ riskStatus.peak_equity | number:'1.2-2' }}</strong>
              </div>
              <div class="mb-3">
                <div class="d-flex justify-content-between mb-1">
                  <span class="text-body-secondary small">Drawdown</span>
                  <strong class="text-danger small">{{ (riskStatus.current_drawdown_pct * 100) | number:'1.2-2' }}%</strong>
                </div>
                <c-progress [value]="riskStatus.current_drawdown_pct * 100" [max]="20" color="danger" style="height: 4px;"></c-progress>
              </div>
              <div class="d-flex justify-content-between mb-3">
                <span class="text-body-secondary small">Daily P&amp;L (USD)</span>
                <strong [class.text-success]="riskStatus.daily_pnl >= 0"
                        [class.text-danger]="riskStatus.daily_pnl < 0">
                  $ {{ riskStatus.daily_pnl >= 0 ? '+' : '' }}{{ riskStatus.daily_pnl | number:'1.2-2' }}
                </strong>
              </div>
              <div class="d-flex justify-content-between">
                <span class="text-body-secondary small">Circuit Breaker</span>
                <c-badge [color]="riskStatus.circuit_breaker_active ? 'danger' : 'success'" class="badge-sm">
                  {{ riskStatus.circuit_breaker_active ? 'ATTIVO' : 'OK' }}
                </c-badge>
              </div>
            } @else {
              <div class="text-center text-body-secondary small">Caricamento...</div>
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>

    <!-- Asset Universe -->
    <c-card class="mb-4">
      <c-card-header class="py-2">
        <strong>Asset Universe</strong>
        <c-badge color="primary" class="ms-2 badge-sm">{{ assets.length }} asset</c-badge>
      </c-card-header>
      <c-card-body class="p-0">
        <div class="table-responsive">
          <table class="table table-sm table-hover table-striped mb-0">
            <thead>
              <tr>
                <th>Epic</th>
                <th>Nome</th>
                <th>Tipo</th>
                <th>Exchange</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              @for (a of assets; track a.epic) {
                <tr>
                  <td class="fw-semibold">{{ a.epic }}</td>
                  <td>{{ a.name }}</td>
                  <td><c-badge color="primary" class="badge-sm">{{ a.type }}</c-badge></td>
                  <td class="text-body-secondary small">{{ a.exchange }}</td>
                  <td>
                    @if (a.epic === 'EURUSD') {
                      <c-badge color="secondary" class="badge-sm">Escluso</c-badge>
                    } @else {
                      <c-badge color="success" class="badge-sm">Attivo</c-badge>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </c-card-body>
    </c-card>
  `
})
export class SettingsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  readonly notifications = inject(NotificationService);

  settings: SystemSettings | null = null;
  riskStatus: RiskStatus | null = null;
  readonly wsConnected = this.ws.connected;
  readonly assets = ASSET_INFO;

  ngOnInit(): void {
    this.trading.getSystemSettings().subscribe(data => this.settings = data);
    this.trading.getRiskStatus().subscribe(data => this.riskStatus = data);
  }

  toggleBrowserNotifications(): void {
    if (this.notifications.enabled()) return;
    this.notifications.requestPermission();
  }
}
