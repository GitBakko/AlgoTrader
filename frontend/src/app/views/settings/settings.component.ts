import { Component, inject, OnInit } from '@angular/core';
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
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent
  ],
  template: `
    <c-row>
      <c-col md="6">
        <c-card class="mb-4">
          <c-card-header><strong>System Settings</strong></c-card-header>
          <c-card-body>
            @if (settings) {
              <table class="table">
                <tbody>
                  <tr><td>App Name</td><td><strong>{{ settings.app_name }}</strong></td></tr>
                  <tr><td>Version</td><td>{{ settings.app_version }}</td></tr>
                  <tr><td>Environment</td><td><c-badge color="info">{{ settings.environment }}</c-badge></td></tr>
                  <tr>
                    <td>Trading</td>
                    <td>
                      <c-badge [color]="settings.trading_enabled ? 'success' : 'danger'">
                        {{ settings.trading_enabled ? 'Enabled' : 'Disabled' }}
                      </c-badge>
                    </td>
                  </tr>
                  <tr>
                    <td>Mode</td>
                    <td>
                      <c-badge [color]="settings.paper_trading ? 'warning' : 'success'">
                        {{ settings.paper_trading ? 'Paper' : 'Live' }}
                      </c-badge>
                    </td>
                  </tr>
                  <tr>
                    <td>Broker</td>
                    <td>{{ settings.use_demo ? 'Demo' : 'Live' }}</td>
                  </tr>
                  <tr>
                    <td>WebSocket</td>
                    <td>
                      <c-badge [color]="wsConnected() ? 'success' : 'danger'">
                        {{ wsConnected() ? 'Connected' : 'Disconnected' }}
                      </c-badge>
                    </td>
                  </tr>
                </tbody>
              </table>
            }
          </c-card-body>
        </c-card>
      </c-col>
      <c-col md="6">
        <c-card class="mb-4">
          <c-card-header><strong>Risk Status</strong></c-card-header>
          <c-card-body>
            @if (riskStatus) {
              <div class="mb-3">
                <div class="d-flex justify-content-between">
                  <span>Equity</span>
                  <strong>{{ riskStatus.current_equity | number:'1.2-2' }}</strong>
                </div>
              </div>
              <div class="mb-3">
                <div class="d-flex justify-content-between">
                  <span>Peak Equity</span>
                  <strong>{{ riskStatus.peak_equity | number:'1.2-2' }}</strong>
                </div>
              </div>
              <div class="mb-3">
                <div class="d-flex justify-content-between mb-1">
                  <span>Drawdown</span>
                  <strong>{{ (riskStatus.current_drawdown_pct * 100) | number:'1.2-2' }}%</strong>
                </div>
                <c-progress [value]="riskStatus.current_drawdown_pct * 100" color="danger" style="height: 8px;"></c-progress>
              </div>
              <div class="mb-3">
                <div class="d-flex justify-content-between">
                  <span>Daily P&L</span>
                  <strong [class]="riskStatus.daily_pnl >= 0 ? 'text-success' : 'text-danger'">
                    {{ riskStatus.daily_pnl | number:'1.2-2' }}
                  </strong>
                </div>
              </div>
              <div class="mb-3">
                <div class="d-flex justify-content-between">
                  <span>Circuit Breaker</span>
                  <c-badge [color]="riskStatus.circuit_breaker_active ? 'danger' : 'success'">
                    {{ riskStatus.circuit_breaker_active ? 'ACTIVE' : 'OK' }}
                  </c-badge>
                </div>
              </div>
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
