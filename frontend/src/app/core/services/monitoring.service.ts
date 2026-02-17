import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { firstValueFrom } from 'rxjs';

// ═══════════════════════════════════════════════════════════════════════════
// API Response Types
// ═══════════════════════════════════════════════════════════════════════════

export interface SignalStats {
  total_signals: number;
  executed: number;
  rejected: number;
  hold: number;
  execution_rate_pct: number;
}

export interface ExecutionStats {
  total_trades: number;
  open_positions: number;
  closed_trades: number;
  total_pnl: number;
  avg_pnl: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  avg_duration_hours: number;
}

export interface RiskStats {
  total_events: number;
  circuit_breaker_triggers: number;
  position_limit_hits: number;
  drawdown_limit_hits: number;
  max_drawdown_pct: number;
  avg_daily_pnl: number;
  last_event: string | null;
}

export interface PerformanceOverview {
  health_score: number;
  signals: {
    total: number;
    execution_rate_pct: number;
    top_strategy: string | null;
  };
  execution: {
    total_trades: number;
    open_positions: number;
    total_pnl: number;
    win_rate_pct: number;
    profit_factor: number;
  };
  risk: {
    circuit_breaker_triggers: number;
    max_drawdown_pct: number;
    avg_daily_pnl: number;
  };
}

export interface SignalLogsResponse {
  period: {
    start_date: string;
    end_date: string;
    days: number;
  };
  summary: SignalStats;
  by_epic: Record<string, number>;
  by_strategy: Record<string, number>;
  by_direction: Record<string, number>;
}

export interface ExecutionLogsResponse {
  period: {
    start_date: string;
    end_date: string;
    days: number;
  };
  summary: ExecutionStats;
  by_epic: Record<string, any>;
}

export interface RiskEventLogsResponse {
  period: {
    start_date: string;
    end_date: string;
    days: number;
  };
  summary: RiskStats;
  by_event_type: Record<string, number>;
}

export interface PerformanceResponse {
  period: {
    start_date: string;
    end_date: string;
    days: number;
  };
  health_score: number;
  signals: {
    total: number;
    execution_rate_pct: number;
    top_strategy: string | null;
  };
  execution: {
    total_trades: number;
    open_positions: number;
    total_pnl: number;
    win_rate_pct: number;
    profit_factor: number;
  };
  risk: {
    circuit_breaker_triggers: number;
    max_drawdown_pct: number;
    avg_daily_pnl: number;
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// Monitoring Service
// ═══════════════════════════════════════════════════════════════════════════

@Injectable({
  providedIn: 'root'
})
export class MonitoringService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/api/monitoring`;

  // Reactive state
  signalLogs = signal<SignalLogsResponse | null>(null);
  executionLogs = signal<ExecutionLogsResponse | null>(null);
  riskEventLogs = signal<RiskEventLogsResponse | null>(null);
  performance = signal<PerformanceResponse | null>(null);
  loading = signal<boolean>(false);
  error = signal<string | null>(null);

  /**
   * Get signal generation statistics
   */
  async getSignalLogs(days: number = 30): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      const response = await firstValueFrom(
        this.http.get<{ success: boolean; data: SignalLogsResponse }>(
          `${this.baseUrl}/logs/signals?days=${days}`
        )
      );

      if (response.success) {
        this.signalLogs.set(response.data);
      } else {
        throw new Error('Failed to fetch signal logs');
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      this.error.set(errorMsg);
      console.error('Error fetching signal logs:', err);
    } finally {
      this.loading.set(false);
    }
  }

  /**
   * Get trade execution statistics
   */
  async getExecutionLogs(days: number = 30): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      const response = await firstValueFrom(
        this.http.get<{ success: boolean; data: ExecutionLogsResponse }>(
          `${this.baseUrl}/logs/executions?days=${days}`
        )
      );

      if (response.success) {
        this.executionLogs.set(response.data);
      } else {
        throw new Error('Failed to fetch execution logs');
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      this.error.set(errorMsg);
      console.error('Error fetching execution logs:', err);
    } finally {
      this.loading.set(false);
    }
  }

  /**
   * Get risk management event statistics
   */
  async getRiskEventLogs(days: number = 30): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      const response = await firstValueFrom(
        this.http.get<{ success: boolean; data: RiskEventLogsResponse }>(
          `${this.baseUrl}/logs/risk-events?days=${days}`
        )
      );

      if (response.success) {
        this.riskEventLogs.set(response.data);
      } else {
        throw new Error('Failed to fetch risk event logs');
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      this.error.set(errorMsg);
      console.error('Error fetching risk event logs:', err);
    } finally {
      this.loading.set(false);
    }
  }

  /**
   * Get combined performance overview
   */
  async getPerformanceOverview(days: number = 7): Promise<void> {
    this.loading.set(true);
    this.error.set(null);

    try {
      const response = await firstValueFrom(
        this.http.get<{ success: boolean; data: PerformanceResponse }>(
          `${this.baseUrl}/stats/performance?days=${days}`
        )
      );

      if (response.success) {
        this.performance.set(response.data);
      } else {
        throw new Error('Failed to fetch performance overview');
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      this.error.set(errorMsg);
      console.error('Error fetching performance overview:', err);
    } finally {
      this.loading.set(false);
    }
  }

  /**
   * Refresh all monitoring data
   */
  async refreshAll(days: number = 30): Promise<void> {
    await Promise.all([
      this.getSignalLogs(days),
      this.getExecutionLogs(days),
      this.getRiskEventLogs(days),
      this.getPerformanceOverview(Math.min(days, 7))
    ]);
  }
}
