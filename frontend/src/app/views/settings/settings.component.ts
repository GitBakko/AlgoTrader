import { Component, ChangeDetectionStrategy, inject, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent,
  FormCheckComponent, FormCheckInputDirective, FormCheckLabelDirective,
  TableDirective,
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { SystemSettings, RiskStatus } from '../../core/models';
import { WebSocketService } from '../../core/services/websocket.service';
import { NotificationService } from '../../shared/services/notification.service';
import { EpicLogoComponent } from '../../shared/components/epic-logo/epic-logo.component';

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

const TYPE_BADGE_COLORS: Record<string, string> = {
  'Commodity': 'warning',
  'Crypto': 'info',
  'Forex': 'primary',
  'Index': 'secondary',
  'Stock CFD': 'success',
};

@Component({
  selector: 'app-settings',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './settings.component.scss',
  imports: [
    CommonModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent,
    FormCheckComponent, FormCheckInputDirective, FormCheckLabelDirective,
    TableDirective,
    EpicLogoComponent,
  ],
  template: `
    <!-- Header -->
    <h5 class="mb-3 fw-semibold px-1">Sistema</h5>

    <c-row>
      <!-- System Info -->
      <c-col lg="4">
        <c-card class="mb-4 border-top border-top-3 border-top-primary">
          <c-card-header class="py-2"><span class="fw-semibold small text-body-secondary">Configurazione</span></c-card-header>
          <c-card-body class="p-0">
            @if (settings(); as s) {
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">App</span>
                <strong class="small">{{ s.app_name }} v{{ s.app_version }}</strong>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Ambiente</span>
                <c-badge color="info" class="badge-sm">{{ s.environment }}</c-badge>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Trading</span>
                <c-badge [color]="s.trading_enabled ? 'success' : 'danger'" class="badge-sm">
                  {{ s.trading_enabled ? 'Attivo' : 'Disattivato' }}
                </c-badge>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Modalita</span>
                <c-badge [color]="s.paper_trading ? 'warning' : 'success'" class="badge-sm">
                  {{ s.paper_trading ? 'Paper' : 'Live' }}
                </c-badge>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Broker</span>
                <c-badge [color]="s.use_demo ? 'warning' : 'danger'" class="badge-sm">
                  {{ s.use_demo ? 'Demo' : 'Live' }}
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
        <c-card class="mb-4 border-top border-top-3 border-top-primary">
          <c-card-header class="py-2"><span class="fw-semibold small text-body-secondary">Parametri Rischio</span></c-card-header>
          <c-card-body class="p-0">
            @if (settings(); as s) {
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Min Confidence</span>
                <strong class="small mantis-mono">{{ (s.min_confidence_threshold * 100) | number:'1.0-0' }}%</strong>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Max Risk/Trade</span>
                <strong class="small mantis-mono">{{ (s.max_risk_per_trade * 100) | number:'1.1-1' }}%</strong>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between border-bottom">
                <span class="text-body-secondary small">Max Daily DD</span>
                <strong class="small mantis-mono text-warning">{{ (s.max_daily_drawdown * 100) | number:'1.1-1' }}%</strong>
              </div>
              <div class="px-3 py-2 d-flex justify-content-between">
                <span class="text-body-secondary small">Max Total DD</span>
                <strong class="small mantis-mono text-danger">{{ (s.max_total_drawdown * 100) | number:'1.1-1' }}%</strong>
              </div>
            }
          </c-card-body>
        </c-card>

        <!-- Notifications -->
        <c-card class="mb-4 border-top border-top-3 border-top-primary">
          <c-card-header class="py-2"><span class="fw-semibold small text-body-secondary">Notifiche</span></c-card-header>
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
                [class.border-top-danger]="riskStatus()?.circuit_breaker_active"
                [class.border-top-success]="riskStatus() && !riskStatus()?.circuit_breaker_active">
          <c-card-header class="py-2"><span class="fw-semibold small text-body-secondary">Risk Status Live</span></c-card-header>
          <c-card-body>
            @if (riskStatus(); as rs) {
              <div class="d-flex justify-content-between mb-3">
                <span class="text-body-secondary small">Equity (USD)</span>
                <strong>$ {{ rs.current_equity | number:'1.2-2' }}</strong>
              </div>
              <div class="d-flex justify-content-between mb-3">
                <span class="text-body-secondary small">Peak (USD)</span>
                <strong>$ {{ rs.peak_equity | number:'1.2-2' }}</strong>
              </div>
              <div class="mb-3">
                <div class="d-flex justify-content-between mb-1">
                  <span class="text-body-secondary small">Drawdown</span>
                  <strong class="text-danger small">{{ (rs.current_drawdown_pct * 100) | number:'1.2-2' }}%</strong>
                </div>
                <c-progress [value]="rs.current_drawdown_pct * 100" [max]="20" color="danger" style="height: 4px;"></c-progress>
              </div>
              <div class="d-flex justify-content-between mb-3">
                <span class="text-body-secondary small">Daily P&amp;L (USD)</span>
                <strong [class.text-success]="rs.daily_pnl >= 0"
                        [class.text-danger]="rs.daily_pnl < 0">
                  $ {{ rs.daily_pnl >= 0 ? '+' : '' }}{{ rs.daily_pnl | number:'1.2-2' }}
                </strong>
              </div>
              <div class="d-flex justify-content-between">
                <span class="text-body-secondary small">Circuit Breaker</span>
                <c-badge [color]="rs.circuit_breaker_active ? 'danger' : 'success'" class="badge-sm">
                  {{ rs.circuit_breaker_active ? 'ATTIVO' : 'OK' }}
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
    <c-card class="mb-4 border-top border-top-3 border-top-primary">
      <c-card-header class="py-2">
        <span class="fw-semibold small text-body-secondary">Asset Universe</span>
        <c-badge color="primary" class="ms-2 badge-sm">{{ assets.length }} asset</c-badge>
      </c-card-header>
      <c-card-body class="p-0">
        <div class="table-responsive-mobile">
          <table cTable [small]="true" [hover]="true" [striped]="true" class="mb-0 align-middle">
            <thead>
              <tr>
                <th>Epic</th>
                <th>Nome</th>
                <th class="d-mobile-none">Tipo</th>
                <th class="d-mobile-none">Exchange</th>
                <th class="text-center d-mobile-none">Posizioni</th>
                <th>Status</th>
                <th class="text-center">Azioni</th>
              </tr>
            </thead>
            <tbody>
              @for (a of assets; track a.epic) {
                <tr class="settings-asset-row" [class.settings-asset-row--excluded]="excludedEpics().has(a.epic)">
                  <td>
                    <div class="d-flex align-items-center gap-2">
                      <app-epic-logo [epic]="a.epic" [size]="20"></app-epic-logo>
                      <span class="fw-semibold">{{ a.epic }}</span>
                    </div>
                  </td>
                  <td>{{ a.name }}</td>
                  <td class="d-mobile-none"><c-badge [color]="getTypeBadgeColor(a.type)" class="badge-sm">{{ a.type }}</c-badge></td>
                  <td class="text-body-secondary small d-mobile-none">{{ a.exchange }}</td>
                  <td class="text-center mantis-mono d-mobile-none">
                    @if (positionCounts()[a.epic]) {
                      <c-badge color="info" class="badge-sm">{{ positionCounts()[a.epic] }}</c-badge>
                    } @else {
                      <span class="text-body-secondary">0</span>
                    }
                  </td>
                  <td>
                    @if (excludedEpics().has(a.epic)) {
                      <c-badge color="secondary" class="badge-sm">Escluso</c-badge>
                    } @else {
                      <c-badge color="success" class="badge-sm">Attivo</c-badge>
                    }
                  </td>
                  <td class="text-center">
                    <div class="d-flex gap-1 justify-content-center">
                      @if (!positionCounts()[a.epic]) {
                        <button class="btn btn-sm py-0 px-2"
                                [class.btn-outline-success]="excludedEpics().has(a.epic)"
                                [class.btn-outline-secondary]="!excludedEpics().has(a.epic)"
                                (click)="toggleEpic(a.epic)">
                          <small>{{ excludedEpics().has(a.epic) ? 'Attiva' : 'Escludi' }}</small>
                        </button>
                      }
                      <button class="btn btn-sm btn-outline-info py-0 px-2"
                              [disabled]="trainingEpics().has(a.epic)"
                              (click)="trainModel(a.epic)">
                        @if (trainingEpics().has(a.epic)) {
                          <span class="spinner-border spinner-border-sm settings-train-spinner"></span>
                        } @else {
                          <small>Train</small>
                        }
                      </button>
                    </div>
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

  readonly settings = signal<SystemSettings | null>(null);
  readonly riskStatus = signal<RiskStatus | null>(null);
  readonly wsConnected = this.ws.connected;
  readonly assets = ASSET_INFO;

  readonly excludedEpics = signal<Set<string>>(
    new Set(JSON.parse(localStorage.getItem('mantis-excluded-epics') || '["EURUSD"]'))
  );
  readonly trainingEpics = signal<Set<string>>(new Set());

  readonly positionCounts = computed(() => {
    const counts: Record<string, number> = {};
    for (const p of this.trading.paperPositions()) {
      counts[p.epic] = (counts[p.epic] || 0) + 1;
    }
    return counts;
  });

  ngOnInit(): void {
    this.trading.getSystemSettings().subscribe(data => this.settings.set(data));
    this.trading.getRiskStatus().subscribe(data => this.riskStatus.set(data));
    this.trading.loadPaperPositions();
  }

  toggleBrowserNotifications(): void {
    if (this.notifications.enabled()) return;
    this.notifications.requestPermission();
  }

  getTypeBadgeColor(type: string): string {
    return TYPE_BADGE_COLORS[type] || 'primary';
  }

  toggleEpic(epic: string): void {
    const excluded = new Set(this.excludedEpics());
    if (excluded.has(epic)) {
      excluded.delete(epic);
    } else {
      excluded.add(epic);
    }
    this.excludedEpics.set(excluded);
    localStorage.setItem('mantis-excluded-epics', JSON.stringify([...excluded]));
  }

  trainModel(epic: string): void {
    const training = new Set(this.trainingEpics());
    training.add(epic);
    this.trainingEpics.set(training);

    this.trading.trainModel(epic).subscribe({
      next: () => {
        // Training started as background subprocess — spinner stays for 3s then clears
        setTimeout(() => {
          const t = new Set(this.trainingEpics());
          t.delete(epic);
          this.trainingEpics.set(t);
        }, 3000);
      },
      error: () => {
        const t = new Set(this.trainingEpics());
        t.delete(epic);
        this.trainingEpics.set(t);
      }
    });
  }
}
