import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, ButtonDirective,
  FormControlDirective, BadgeComponent
} from '@coreui/angular';
import { TradingService } from '../../core/services/trading.service';
import { ToastService } from '../../shared/services/toast.service';
import { StrategyConfig } from '../../core/models';

@Component({
  selector: 'app-strategy',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './strategy.component.scss',
  imports: [
    CommonModule, FormsModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent,
    FormControlDirective, BadgeComponent
  ],
  template: `
    <!-- HDR-03 (Bible §1.2) -->
    <header class="stg-hdr">
      <span class="stg-hdr__eyebrow mantis-mono">Trading · Configurazione</span>
      <h1 class="stg-hdr__title">Strategia</h1>
      <span class="stg-hdr__meta mantis-mono">{{ configs().length }} asset configurati</span>
    </header>

    <h2 class="stg-section-title">Per-asset config</h2>
    <c-row>
      @for (cfg of configs(); track cfg.epic) {
        <c-col md="4">
          <c-card class="mb-4 border-top border-top-3 border-top-primary">
            <c-card-header class="py-2">
              <strong>{{ cfg.epic }}</strong>
              <c-badge color="info" class="float-end">Strategy</c-badge>
            </c-card-header>
            <c-card-body>
              <div class="mb-2">
                <label class="stg-label">Min Confidence</label>
                <input cFormControl type="number" step="0.05" [(ngModel)]="cfg.min_confidence" />
              </div>
              <div class="mb-2">
                <label class="stg-label">Stop Multiplier (ATR)</label>
                <input cFormControl type="number" step="0.1" [(ngModel)]="cfg.stop_multiplier" />
              </div>
              <div class="mb-2">
                <label class="stg-label">Risk / Reward Ratio</label>
                <input cFormControl type="number" step="0.1" [(ngModel)]="cfg.risk_reward_ratio" />
              </div>
              <div class="mb-2">
                <label class="stg-label">Counter-trend Penalty</label>
                <input cFormControl type="number" step="0.1" [(ngModel)]="cfg.counter_trend_penalty" />
              </div>
              <button type="button" class="stg-btn stg-btn--primary" (click)="saveConfig(cfg)">
                Salva
              </button>
            </c-card-body>
          </c-card>
        </c-col>
      }
    </c-row>

    <h2 class="stg-section-title">Risk &amp; Allocation</h2>
    <c-row>
      <c-col md="6">
        <c-card class="mb-4 border-top border-top-3 border-top-warning">
          <c-card-header class="py-2"><strong>Risk Limits</strong></c-card-header>
          <c-card-body>
            @if (limits(); as l) {
              <div class="mb-2">
                <label class="stg-label">Max Risk per Trade</label>
                <input cFormControl type="number" step="0.01" [(ngModel)]="l.max_risk_per_trade" />
              </div>
              <div class="mb-2">
                <label class="stg-label">Max Daily Drawdown</label>
                <input cFormControl type="number" step="0.01" [(ngModel)]="l.max_daily_drawdown" />
              </div>
              <div class="mb-2">
                <label class="stg-label">Max Total Drawdown</label>
                <input cFormControl type="number" step="0.01" [(ngModel)]="l.max_total_drawdown" />
              </div>
              <button type="button" class="stg-btn stg-btn--primary" (click)="saveLimits()">
                Salva Limits
              </button>
            }
          </c-card-body>
        </c-card>
      </c-col>
      <c-col md="6">
        <c-card class="mb-4 border-top border-top-3 border-top-info">
          <c-card-header class="py-2"><strong>Portfolio Allocation</strong></c-card-header>
          <c-card-body>
            @if (allocation()) {
              @for (entry of allocationEntries(); track entry[0]) {
                <div class="stg-alloc-row mantis-mono">
                  <span class="stg-alloc-key">{{ entry[0] }}</span>
                  <strong class="stg-alloc-val">{{ (entry[1] * 100) | number:'1.0-0' }}%</strong>
                </div>
              }
            }
          </c-card-body>
        </c-card>
      </c-col>
    </c-row>
  `
})
export class StrategyComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly toast = inject(ToastService);
  readonly configs = this.trading.strategyConfigs;
  readonly limits = this.trading.riskLimitsData;
  readonly allocation = this.trading.allocationData;
  readonly allocationEntries = computed(() => {
    const alloc = this.allocation();
    return alloc ? Object.entries(alloc.weights) : [];
  });

  ngOnInit(): void {
    this.trading.loadStrategyConfig();
    this.trading.loadRiskLimits();
    this.trading.loadAllocation();
  }

  saveConfig(cfg: StrategyConfig): void {
    // H7-FE-AUDIT: was a silent .subscribe(); failures left the form
    // showing the new values without persisting them. ToastService
    // surfaces success / error.
    this.trading.updateStrategyConfig(cfg).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => this.toast.success(`${cfg.epic} config salvata`),
      error: () => this.toast.error('Errore nel salvataggio config'),
    });
  }

  saveLimits(): void {
    const l = this.limits();
    if (l) {
      this.trading.updateRiskLimits(l).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: () => this.toast.success('Risk limits salvati'),
        error: () => this.toast.error('Errore nel salvataggio risk limits'),
      });
    }
  }
}
