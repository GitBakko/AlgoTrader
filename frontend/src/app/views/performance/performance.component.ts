import {
  Component, ChangeDetectionStrategy, inject, OnInit, signal, computed,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardComponent, CardBodyComponent, CardHeaderComponent,
  ColComponent, RowComponent,
} from '@coreui/angular';
import { HttpClient } from '@angular/common/http';
import { ChartjsComponent } from '@coreui/angular-chartjs';
import { TradingService } from '../../core/services/trading.service';
import { TvChartComponent, LineDataPoint } from '../../shared/components/tv-chart/tv-chart.component';
import { CorrelationHeatmapComponent, CorrelationData } from './correlation-heatmap.component';
import { environment } from '../../../environments/environment';
import { ApiResponse } from '../../core/models';

@Component({
  selector: 'app-performance',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    CardComponent, CardBodyComponent, CardHeaderComponent,
    ColComponent, RowComponent,
    ChartjsComponent,
    TvChartComponent,
    CorrelationHeatmapComponent,
  ],
  templateUrl: './performance.component.html',
  styleUrl: './performance.component.scss',
})
export class PerformanceComponent implements OnInit {
  private readonly trading = inject(TradingService);
  private readonly http = inject(HttpClient);
  readonly performance = this.trading.performance;
  readonly correlationData = signal<CorrelationData | null>(null);

  readonly selectedPeriod = signal(30);
  readonly periods = [
    { value: 7, label: '7g' },
    { value: 30, label: '30g' },
    { value: 90, label: '90g' },
    { value: 365, label: '1A' },
    { value: 0, label: 'Tutto' },
  ];

  ngOnInit(): void {
    this.loadData();
    this.loadCorrelation();
  }

  selectPeriod(days: number): void {
    this.selectedPeriod.set(days);
    this.loadData();
  }

  private loadData(): void {
    const days = this.selectedPeriod();
    this.trading.loadPerformance(days || 3650);
  }

  private loadCorrelation(): void {
    this.http.get<ApiResponse<CorrelationData>>(
      `${environment.apiUrl}/api/analytics/correlation-matrix?days=90`
    ).subscribe({
      next: res => {
        if (res.success) this.correlationData.set(res.data);
      },
    });
  }

  // Equity curve for TvChart
  readonly equityLineData = computed<LineDataPoint[]>(() => {
    const perf = this.performance();
    if (!perf?.equity_curve) return [];
    return perf.equity_curve.map(p => ({
      time: p.date?.substring(0, 10) || '',
      value: p.value,
    }));
  });

  // P&L by asset sorted
  readonly pnlByAsset = computed(() => {
    const perf = this.performance();
    if (!perf?.pnl_by_epic) return [];
    return Object.entries(perf.pnl_by_epic)
      .map(([epic, pnl]) => ({ epic, pnl }))
      .sort((a, b) => b.pnl - a.pnl);
  });

  readonly maxAbsPnl = computed(() => {
    const items = this.pnlByAsset();
    if (items.length === 0) return 1;
    return Math.max(...items.map(i => Math.abs(i.pnl)));
  });

  // Win rate by asset chart data
  readonly winRateChartData = computed(() => {
    const perf = this.performance();
    if (!perf?.pnl_by_epic) return null;
    // We only have pnl_by_epic, not win_rate_by_epic, so skip this chart
    return null;
  });

  // P&L distribution histogram
  readonly pnlDistChartData = computed(() => {
    const perf = this.performance();
    if (!perf?.equity_curve || perf.equity_curve.length < 2) return null;
    // Compute trade-by-trade P&L from equity curve diffs
    const values = perf.equity_curve.map(p => p.value);
    const pnls: number[] = [];
    for (let i = 1; i < values.length; i++) {
      pnls.push(+(values[i] - values[i - 1]).toFixed(2));
    }
    if (pnls.length === 0) return null;

    // Build histogram bins
    const minPnl = Math.min(...pnls);
    const maxPnl = Math.max(...pnls);
    const range = maxPnl - minPnl;
    if (range === 0) return null;
    const binCount = Math.min(20, Math.max(5, Math.ceil(Math.sqrt(pnls.length))));
    const binSize = range / binCount;
    const bins: { label: string; count: number; color: string }[] = [];
    for (let i = 0; i < binCount; i++) {
      const low = minPnl + i * binSize;
      const high = low + binSize;
      const count = pnls.filter(p => p >= low && (i === binCount - 1 ? p <= high : p < high)).length;
      bins.push({
        label: `${low.toFixed(0)}`,
        count,
        color: low >= 0 ? 'rgba(57, 255, 20, 0.7)' : 'rgba(255, 61, 87, 0.7)',
      });
    }

    return {
      labels: bins.map(b => b.label),
      datasets: [{
        label: 'Frequenza',
        data: bins.map(b => b.count),
        backgroundColor: bins.map(b => b.color),
        borderWidth: 0,
        borderRadius: 2,
      }],
    };
  });

  readonly pnlDistChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items: any[]) => `P&L: $${items[0]?.label ?? ''}`,
          label: (item: any) => `${item.raw} trades`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: 'rgba(255,255,255,0.5)', font: { size: 10 } },
      },
      y: {
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: 'rgba(255,255,255,0.5)', font: { size: 10 } },
      },
    },
  };

  // P&L per asset bar chart
  readonly pnlAssetChartData = computed(() => {
    const items = this.pnlByAsset();
    if (items.length === 0) return null;
    return {
      labels: items.map(i => i.epic),
      datasets: [{
        label: 'P&L ($)',
        data: items.map(i => i.pnl),
        backgroundColor: items.map(i =>
          i.pnl >= 0 ? 'rgba(57, 255, 20, 0.7)' : 'rgba(255, 61, 87, 0.7)'
        ),
        borderWidth: 0,
        borderRadius: 2,
      }],
    };
  });

  readonly pnlAssetChartOptions = {
    indexAxis: 'y' as const,
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (item: any) => `$ ${item.raw?.toFixed(2)}`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: 'rgba(255,255,255,0.5)', font: { size: 10 } },
      },
      y: {
        grid: { display: false },
        ticks: { color: 'rgba(255,255,255,0.7)', font: { size: 11, family: 'IBM Plex Mono' } },
      },
    },
  };

  readonly Math = Math;
}
