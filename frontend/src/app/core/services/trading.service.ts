import { Injectable, inject, signal, computed } from '@angular/core';
import { ApiService } from './api.service';
import {
  DashboardOverview,
  Position,
  TradingSignal,
  MarketInfo,
  StrategyConfig,
  RiskLimits,
  Allocation,
  BacktestRun,
  BacktestDetail,
  MLModel,
  SystemSettings,
  RiskStatus,
  EquityCurvePoint,
  OHLCCandle,
} from '../models';

@Injectable({ providedIn: 'root' })
export class TradingService {
  private readonly api = inject(ApiService);

  // Dashboard
  readonly overview = signal<DashboardOverview | null>(null);
  readonly equityCurve = signal<EquityCurvePoint[]>([]);

  // Positions
  readonly positions = signal<Position[]>([]);
  readonly openCount = computed(() => this.positions().length);

  // Signals
  readonly signals = signal<TradingSignal[]>([]);

  // ── Dashboard ──

  loadOverview(): void {
    this.api.get<DashboardOverview>('/api/dashboard/overview')
      .subscribe(data => this.overview.set(data));
  }

  loadEquityCurve(days = 30): void {
    this.api.get<EquityCurvePoint[]>('/api/dashboard/equity-curve', { days })
      .subscribe(data => this.equityCurve.set(data));
  }

  // ── Positions ──

  loadPositions(): void {
    this.api.get<Position[]>('/api/positions/')
      .subscribe(data => this.positions.set(data));
  }

  closePosition(dealId: string) {
    return this.api.post<{ deal_id: string }>(`/api/positions/close/${dealId}`);
  }

  // ── Signals ──

  loadSignals(epic?: string): void {
    const params: Record<string, string> = {};
    if (epic) params['epic'] = epic;
    this.api.get<TradingSignal[]>('/api/signals/', params)
      .subscribe(data => this.signals.set(data));
  }

  generateSignal(epic = 'XAUUSD', confidence = 0.8, signalClass = 3) {
    return this.api.get<TradingSignal>('/api/signals/generate', {
      epic,
      confidence,
      signal_class: signalClass
    });
  }

  // ── Markets ──

  searchMarkets(q = '') {
    return this.api.get<MarketInfo[]>('/api/markets/search', { q });
  }

  getMarketPrices(epic: string, resolution = 'HOUR', max = 200) {
    return this.api.get<OHLCCandle[]>(`/api/markets/${epic}/prices`, { resolution, max_candles: max });
  }

  // ── Strategy ──

  getStrategyConfig() {
    return this.api.get<StrategyConfig[]>('/api/strategy/config');
  }

  updateStrategyConfig(config: StrategyConfig) {
    return this.api.put<{ updated: boolean }>('/api/strategy/config', config);
  }

  getAllocation(regime?: string) {
    const params: Record<string, string> = {};
    if (regime) params['regime'] = regime;
    return this.api.get<Allocation>('/api/strategy/allocation', params);
  }

  getRiskLimits() {
    return this.api.get<RiskLimits>('/api/strategy/risk-limits');
  }

  updateRiskLimits(limits: RiskLimits) {
    return this.api.put<{ updated: boolean }>('/api/strategy/risk-limits', limits);
  }

  // ── Backtest ──

  runBacktest(config: { epic: string; initial_equity?: number; risk_per_trade?: number }) {
    return this.api.post<BacktestRun>('/api/backtest/run', config);
  }

  listBacktestRuns() {
    return this.api.get<BacktestRun[]>('/api/backtest/runs');
  }

  getBacktestDetail(runId: string) {
    return this.api.get<BacktestDetail>(`/api/backtest/runs/${runId}`);
  }

  // ── Models ──

  listModels() {
    return this.api.get<MLModel[]>('/api/models/');
  }

  // ── System ──

  getSystemSettings() {
    return this.api.get<SystemSettings>('/api/system/settings');
  }

  getRiskStatus() {
    return this.api.get<RiskStatus>('/api/system/risk-status');
  }
}
