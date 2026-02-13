import { Component, ChangeDetectionStrategy, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { SystemSettings, RiskStatus } from '../../core/models';
import { WebSocketService } from '../../core/services/websocket.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent
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

      <!-- Risk Params -->
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
  `
})
export class SettingsComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);

  settings: SystemSettings | null = null;
  riskStatus: RiskStatus | null = null;
  readonly wsConnected = this.ws.connected;

  ngOnInit(): void {
    this.trading.getSystemSettings().subscribe(data => this.settings = data);
    this.trading.getRiskStatus().subscribe(data => this.riskStatus = data);
  }
}
