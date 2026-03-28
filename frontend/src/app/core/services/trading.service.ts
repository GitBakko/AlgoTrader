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
  PaperTradingStatus,
  PaperPosition,
  PaperSignal,
  ClosedPosition,
  PositionAggregates,
  TradingPerformance,
  TrainingStatus,
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

  // Markets
  readonly markets = signal<MarketInfo[]>([]);

  // Strategy
  readonly strategyConfigs = signal<StrategyConfig[]>([]);
  readonly riskLimitsData = signal<RiskLimits | null>(null);
  readonly allocationData = signal<Allocation | null>(null);

  // Models
  readonly models = signal<MLModel[]>([]);

  // Risk
  readonly riskStatus = signal<RiskStatus | null>(null);

  // Paper Trading
  readonly paperStatus = signal<PaperTradingStatus | null>(null);
  readonly paperPositions = signal<PaperPosition[]>([]);
  readonly paperSignals = signal<PaperSignal[]>([]);

  // Closed Positions & Performance
  readonly closedPositions = signal<ClosedPosition[]>([]);
  readonly closedTotal = signal<number>(0);
  readonly closedAggregates = signal<PositionAggregates | null>(null);
  readonly performance = signal<TradingPerformance | null>(null);

  // Training
  readonly trainingStatus = signal<TrainingStatus | null>(null);

  // Signal Notes (Trade Journal annotations)
  readonly signalNotes = signal<Record<string, string>>({});

  // ── Dashboard ──

  loadOverview(): void {
    this.api.get<DashboardOverview>('/api/dashboard/overview')
      .subscribe({ next: data => this.overview.set(data), error: () => {} });
  }

  loadEquityCurve(days = 30): void {
    this.api.get<EquityCurvePoint[]>('/api/dashboard/equity-curve', { days })
      .subscribe({ next: data => this.equityCurve.set(data), error: () => {} });
  }

  loadRiskStatus(): void {
    this.api.get<RiskStatus>('/api/system/risk-status')
      .subscribe({ next: data => this.riskStatus.set(data), error: () => {} });
  }

  // ── Positions ──

  loadPositions(): void {
    this.api.get<Position[]>('/api/positions/')
      .subscribe({ next: data => this.positions.set(data), error: () => {} });
  }

  closePosition(dealId: string) {
    return this.api.post<{ deal_id: string }>(`/api/positions/close/${dealId}`);
  }

  // ── Signals ──

  loadSignals(epic?: string): void {
    const params: Record<string, string> = {};
    if (epic) params['epic'] = epic;
    this.api.get<TradingSignal[]>('/api/signals/', params)
      .subscribe({ next: data => this.signals.set(data), error: () => {} });
  }

  generateSignal(epic = 'XAUUSD', confidence = 0.8, signalClass = 3) {
    return this.api.get<TradingSignal>('/api/signals/generate', {
      epic,
      confidence,
      signal_class: signalClass
    });
  }

  // ── Markets ──

  loadMarkets(q = ''): void {
    this.api.get<MarketInfo[]>('/api/markets/search', { q })
      .subscribe({ next: data => this.markets.set(data), error: () => {} });
  }

  searchMarkets(q = '') {
    return this.api.get<MarketInfo[]>('/api/markets/search', { q });
  }

  getMarketPrices(epic: string, resolution = 'HOUR', max = 200) {
    return this.api.get<OHLCCandle[]>(`/api/markets/${epic}/prices`, { resolution, max_candles: max });
  }

  // ── Strategy ──

  loadStrategyConfig(): void {
    this.api.get<StrategyConfig[]>('/api/strategy/config')
      .subscribe({ next: data => this.strategyConfigs.set(data), error: () => {} });
  }

  loadRiskLimits(): void {
    this.api.get<RiskLimits>('/api/strategy/risk-limits')
      .subscribe({ next: data => this.riskLimitsData.set(data), error: () => {} });
  }

  loadAllocation(regime?: string): void {
    const params: Record<string, string> = {};
    if (regime) params['regime'] = regime;
    this.api.get<Allocation>('/api/strategy/allocation', params)
      .subscribe({ next: data => this.allocationData.set(data), error: () => {} });
  }

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

  runBacktest(config: { epic: string; timeframe?: string; start_date?: string; end_date?: string; initial_equity?: number; risk_per_trade?: number; strategy?: string }) {
    return this.api.post<BacktestRun>('/api/backtest/run', config);
  }

  listBacktestRuns() {
    return this.api.get<BacktestRun[]>('/api/backtest/runs');
  }

  getBacktestDetail(runId: string) {
    return this.api.get<BacktestDetail>(`/api/backtest/runs/${runId}`);
  }

  // ── Models ──

  loadModels(): void {
    this.api.get<MLModel[]>('/api/models/')
      .subscribe({ next: data => this.models.set(data), error: () => {} });
  }

  listModels() {
    return this.api.get<MLModel[]>('/api/models/');
  }

  // ── Training ──

  loadTrainingStatus(): void {
    this.api.get<TrainingStatus>('/api/models/training/status')
      .subscribe({ next: data => this.trainingStatus.set(data), error: () => {} });
  }

  startTraining(epics?: string[]): void {
    const body: Record<string, unknown> = {};
    if (epics) body['epics'] = epics;
    this.api.post<unknown>('/api/models/training/start', body)
      .subscribe({ next: () => this.loadTrainingStatus(), error: () => {} });
  }

  startTrainingSingle(epic: string): void {
    this.api.post<unknown>('/api/models/training/start/' + epic)
      .subscribe({ next: () => this.loadTrainingStatus(), error: () => {} });
  }

  // ── System ──

  getSystemSettings() {
    return this.api.get<SystemSettings>('/api/system/settings');
  }

  getRiskStatus() {
    return this.api.get<RiskStatus>('/api/system/risk-status');
  }

  trainModel(epic: string) {
    return this.api.post<{ message: string; epic: string }>(`/api/models/train/${epic}`);
  }

  // ── Paper Trading ──

  loadPaperStatus(): void {
    this.api.get<PaperTradingStatus>('/api/trading/status')
      .subscribe({ next: data => this.paperStatus.set(data), error: () => {} });
  }

  loadPaperPositions(): void {
    this.api.get<PaperPosition[]>('/api/trading/positions')
      .subscribe({ next: data => this.paperPositions.set(data), error: () => {} });
  }

  loadPaperSignals(): void {
    this.api.get<PaperSignal[]>('/api/trading/signals')
      .subscribe({ next: data => this.paperSignals.set(data), error: () => {} });
  }

  startPaperTrading() {
    return this.api.post<PaperTradingStatus & { message: string }>('/api/trading/start');
  }

  stopPaperTrading() {
    return this.api.post<PaperTradingStatus & { message: string }>('/api/trading/stop');
  }

  // ── Closed Positions & Performance ──

  loadClosedPositions(params: {
    page?: number; page_size?: number;
    date_from?: string; date_to?: string;
    close_reason?: string; epic?: string;
  } = {}): void {
    const q: Record<string, string | number> = {};
    if (params.page) q['page'] = params.page;
    if (params.page_size) q['page_size'] = params.page_size;
    if (params.date_from) q['date_from'] = params.date_from;
    if (params.date_to) q['date_to'] = params.date_to;
    if (params.close_reason) q['close_reason'] = params.close_reason;
    if (params.epic) q['epic'] = params.epic;

    this.api.get<{
      positions: ClosedPosition[];
      total: number;
      aggregates: PositionAggregates;
    }>('/api/positions/closed', q)
      .subscribe({
        next: data => {
          this.closedPositions.set(data.positions);
          this.closedTotal.set(data.total);
          this.closedAggregates.set(data.aggregates);
        },
        error: () => {},
      });
  }

  loadPerformance(days = 30, epic?: string): void {
    const q: Record<string, string | number> = { days };
    if (epic) q['epic'] = epic;
    this.api.get<TradingPerformance>('/api/trading/performance', q)
      .subscribe({
        next: data => this.performance.set(data),
        error: () => {},
      });
  }

  emergencyStop() {
    return this.api.post<{
      message: string;
      loop_stopped: boolean;
      positions_closed: string[];
      errors: string[];
    }>('/api/trading/emergency-stop');
  }

  resetCircuitBreakers() {
    return this.api.post<{
      message: string;
      reset_breakers: string[];
    }>('/api/trading/reset-circuit-breakers');
  }

  // ── Signal Notes (Trade Journal) ──

  loadSignalNotes(): void {
    this.api.get<Record<string, string>>('/api/trading/signals/notes')
      .subscribe({ next: data => this.signalNotes.set(data), error: () => {} });
  }

  updateSignalNote(epic: string, signalTimestamp: string, notes: string) {
    return this.api.put<{ epic: string; signal_timestamp: string; notes: string } | { deleted: boolean }>(
      '/api/trading/signals/notes',
      { epic, signal_timestamp: signalTimestamp, notes },
    );
  }

  // ── CSV Export ──

  exportClosedPositionsCsv(params: {
    date_from?: string; date_to?: string;
    close_reason?: string; epic?: string;
  } = {}) {
    const q: Record<string, string> = {};
    if (params.date_from) q['date_from'] = params.date_from;
    if (params.date_to) q['date_to'] = params.date_to;
    if (params.close_reason) q['close_reason'] = params.close_reason;
    if (params.epic) q['epic'] = params.epic;
    return this.api.getBlob('/api/export/positions/csv', q);
  }
}
