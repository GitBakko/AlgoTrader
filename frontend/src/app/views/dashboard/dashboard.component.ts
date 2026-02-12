import { Component, effect, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent, BadgeComponent, ProgressComponent,
  WidgetStatFComponent
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { ChartjsComponent } from '@coreui/angular-chartjs';
import { TradingService } from '../../core/services/trading.service';

@Component({
  templateUrl: 'dashboard.component.html',
  imports: [
    CommonModule,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent, BadgeComponent, ProgressComponent,
    WidgetStatFComponent, IconDirective, ChartjsComponent
  ]
})
export class DashboardComponent implements OnInit {
  readonly trading = inject(TradingService);

  readonly overview = this.trading.overview;
  readonly riskStatus = this.trading.riskStatus;
  readonly equityChartData = signal<any>({});
  readonly equityChartOptions = signal<any>({});

  private equityCurveEffect = effect(() => {
    const curve = this.trading.equityCurve();
    if (curve.length > 0) {
      this.buildEquityChart(curve);
    }
  });

  ngOnInit(): void {
    this.trading.loadOverview();
    this.trading.loadEquityCurve();
    this.trading.loadPositions();
    this.trading.loadRiskStatus();
  }

  private buildEquityChart(curve: { date: string; equity: number }[]): void {
    const labels = curve.map(p => p.date?.substring(0, 10) || '');
    const values = curve.map(p => p.equity);

    this.equityChartData.set({
      labels,
      datasets: [{
        label: 'Equity',
        data: values,
        borderColor: '#20c997',
        backgroundColor: 'rgba(32, 201, 151, 0.1)',
        fill: true,
        tension: 0.3,
      }]
    });

    this.equityChartOptions.set({
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: true, grid: { display: false } },
        y: { display: true }
      }
    });
  }
}
