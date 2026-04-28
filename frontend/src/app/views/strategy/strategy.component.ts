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
import { StrategyConfig } from '../../core/models';

@Component({
  selector: 'app-strategy',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, FormsModule, CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, ButtonDirective,
    FormControlDirective, BadgeComponent
  ],
  template: `
    <c-row>
      @for (cfg of configs(); track cfg.epic) {
        <c-col md="4">
          <c-card class="mb-4">
            <c-card-header>
              <strong>{{ cfg.epic }}</strong>
              <c-badge color="info" class="float-end">Strategy</c-badge>
            </c-card-header>
            <c-card-body>
              <div class="mb-2">
                <label cFormLabel>Min Confidence</label>
                <input cFormControl type="number" step="0.05" [(ngModel)]="cfg.min_confidence" />
              </div>
              <div class="mb-2">
                <label cFormLabel>Stop Multiplier (ATR)</label>
                <input cFormControl type="number" step="0.1" [(ngModel)]="cfg.stop_multiplier" />
              </div>
              <div class="mb-2">
                <label cFormLabel>Risk/Reward Ratio</label>
                <input cFormControl type="number" step="0.1" [(ngModel)]="cfg.risk_reward_ratio" />
              </div>
              <div class="mb-2">
                <label cFormLabel>Counter-trend Penalty</label>
                <input cFormControl type="number" step="0.1" [(ngModel)]="cfg.counter_trend_penalty" />
              </div>
              <button cButton color="primary" size="sm" class="mt-2" (click)="saveConfig(cfg)">Save</button>
            </c-card-body>
          </c-card>
        </c-col>
      }
    </c-row>
    <c-row>
      <c-col md="6">
        <c-card class="mb-4">
          <c-card-header><strong>Risk Limits</strong></c-card-header>
          <c-card-body>
            @if (limits(); as l) {
              <div class="mb-2">
                <label cFormLabel>Max Risk per Trade</label>
                <input cFormControl type="number" step="0.01" [(ngModel)]="l.max_risk_per_trade" />
              </div>
              <div class="mb-2">
                <label cFormLabel>Max Daily Drawdown</label>
                <input cFormControl type="number" step="0.01" [(ngModel)]="l.max_daily_drawdown" />
              </div>
              <div class="mb-2">
                <label cFormLabel>Max Total Drawdown</label>
                <input cFormControl type="number" step="0.01" [(ngModel)]="l.max_total_drawdown" />
              </div>
              <button cButton color="primary" size="sm" class="mt-2" (click)="saveLimits()">Save Limits</button>
            }
          </c-card-body>
        </c-card>
      </c-col>
      <c-col md="6">
        <c-card class="mb-4">
          <c-card-header><strong>Portfolio Allocation</strong></c-card-header>
          <c-card-body>
            @if (allocation()) {
              @for (entry of allocationEntries(); track entry[0]) {
                <div class="d-flex justify-content-between mb-2">
                  <span>{{ entry[0] }}</span>
                  <strong>{{ (entry[1] * 100) | number:'1.0-0' }}%</strong>
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
    this.trading.updateStrategyConfig(cfg).pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
  }

  saveLimits(): void {
    const l = this.limits();
    if (l) {
      this.trading.updateRiskLimits(l).pipe(takeUntilDestroyed(this.destroyRef)).subscribe();
    }
  }
}
