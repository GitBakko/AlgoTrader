import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from './api.service';

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

/**
 * H4-FE-AUDIT / H1-CORE: migrated from raw HttpClient to ApiService.
 * Each fetcher now reads the unwrapped envelope `data` directly.
 */
@Injectable({ providedIn: 'root' })
export class MonitoringService {
  private readonly api = inject(ApiService);

  // Reactive state
  signalLogs = signal<SignalLogsResponse | null>(null);
  executionLogs = signal<ExecutionLogsResponse | null>(null);
  riskEventLogs = signal<RiskEventLogsResponse | null>(null);
  performance = signal<PerformanceResponse | null>(null);
  loading = signal<boolean>(false);
  error = signal<string | null>(null);

  private async fetch<T>(
    path: string,
    params: Record<string, number>,
    setter: (data: T) => void,
    failureMessage: string,
  ): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const data = await firstValueFrom(this.api.get<T>(path, params));
      setter(data);
    } catch {
      // Surface the curated domain message regardless of whether the failure
      // came from a network error, HTTP error, or an envelope success:false
      // (audit M1.10 — unwrap() now throws on success:false at HTTP 200).
      this.error.set(failureMessage);
    } finally {
      this.loading.set(false);
    }
  }

  async getSignalLogs(days: number = 30): Promise<void> {
    return this.fetch<SignalLogsResponse>(
      '/api/monitoring/logs/signals', { days },
      d => this.signalLogs.set(d),
      'Failed to fetch signal logs',
    );
  }

  async getExecutionLogs(days: number = 30): Promise<void> {
    return this.fetch<ExecutionLogsResponse>(
      '/api/monitoring/logs/executions', { days },
      d => this.executionLogs.set(d),
      'Failed to fetch execution logs',
    );
  }

  async getRiskEventLogs(days: number = 30): Promise<void> {
    return this.fetch<RiskEventLogsResponse>(
      '/api/monitoring/logs/risk-events', { days },
      d => this.riskEventLogs.set(d),
      'Failed to fetch risk event logs',
    );
  }

  async getPerformanceOverview(days: number = 7): Promise<void> {
    return this.fetch<PerformanceResponse>(
      '/api/monitoring/stats/performance', { days },
      d => this.performance.set(d),
      'Failed to fetch performance overview',
    );
  }

  async refreshAll(days: number = 30): Promise<void> {
    await Promise.all([
      this.getSignalLogs(days),
      this.getExecutionLogs(days),
      this.getRiskEventLogs(days),
      this.getPerformanceOverview(Math.min(days, 7))
    ]);
  }
}
