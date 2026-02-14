import { Component, OnInit, inject, signal, computed, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  CardModule,
  GridModule,
  ButtonModule,
  BadgeModule,
  ProgressModule,
  TableModule,
  ButtonGroupModule,
  FormModule,
  AlertModule
} from '@coreui/angular';
import { IconModule } from '@coreui/icons-angular';
import { MonitoringService } from '../../core/services/monitoring.service';

@Component({
  selector: 'app-system-logs',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    CardModule,
    GridModule,
    ButtonModule,
    BadgeModule,
    ProgressModule,
    TableModule,
    ButtonGroupModule,
    FormModule,
    AlertModule,
    IconModule
  ],
  templateUrl: './system-logs.component.html',
  styleUrls: ['./system-logs.component.scss']
})
export class SystemLogsComponent implements OnInit {
  private monitoringService = inject(MonitoringService);

  // Date range options
  selectedDays = signal<number>(30);
  dateRangeOptions = [
    { label: '7 Days', value: 7 },
    { label: '30 Days', value: 30 },
    { label: '90 Days', value: 90 }
  ];

  // Service state
  loading = this.monitoringService.loading;
  error = this.monitoringService.error;

  // Data
  performance = this.monitoringService.performance;
  signalLogs = this.monitoringService.signalLogs;
  executionLogs = this.monitoringService.executionLogs;
  riskEventLogs = this.monitoringService.riskEventLogs;

  // Computed values
  healthScoreColor = computed(() => {
    const score = this.performance()?.health_score ?? 0;
    if (score >= 85) return 'success';
    if (score >= 70) return 'warning';
    return 'danger';
  });

  healthScoreText = computed(() => {
    const score = this.performance()?.health_score ?? 0;
    if (score >= 85) return 'Excellent';
    if (score >= 70) return 'Good';
    if (score >= 50) return 'Fair';
    return 'Poor';
  });

  // By Epic breakdown (for charts/tables)
  epicBreakdown = computed(() => {
    const signalData = this.signalLogs()?.by_epic ?? {};
    const execData = this.executionLogs()?.by_epic ?? {};

    const epics = new Set([
      ...Object.keys(signalData),
      ...Object.keys(execData)
    ]);

    return Array.from(epics).map(epic => ({
      epic,
      signals: signalData[epic] ?? 0,
      trades: execData[epic]?.trades ?? 0,
      pnl: execData[epic]?.pnl ?? 0,
      win_rate: execData[epic]?.win_rate_pct ?? 0
    }));
  });

  // Strategy breakdown
  strategyBreakdown = computed(() => {
    const data = this.signalLogs()?.by_strategy ?? {};
    return Object.entries(data).map(([strategy, count]) => ({
      strategy,
      count
    }));
  });

  // Risk events breakdown
  riskEventsBreakdown = computed(() => {
    const data = this.riskEventLogs()?.by_event_type ?? {};
    return Object.entries(data).map(([type, count]) => ({
      type: this.formatEventType(type),
      count
    }));
  });

  ngOnInit(): void {
    this.loadData();
  }

  async loadData(): Promise<void> {
    await this.monitoringService.refreshAll(this.selectedDays());
  }

  async onDateRangeChange(days: number): Promise<void> {
    this.selectedDays.set(days);
    await this.loadData();
  }

  async refresh(): Promise<void> {
    await this.loadData();
  }

  // Helpers
  formatEventType(type: string): string {
    return type
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  formatCurrency(value: number): string {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value);
  }

  formatPercent(value: number): string {
    return `${value.toFixed(2)}%`;
  }

  formatNumber(value: number): string {
    return new Intl.NumberFormat('en-US').format(value);
  }
}
