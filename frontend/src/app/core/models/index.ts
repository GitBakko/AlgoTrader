// API envelope
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  error?: string;
}

// Dashboard
export interface DashboardOverview {
  equity: number;
  daily_pnl: number;
  today_realized_pnl: number;
  total_pnl: number;
  open_positions_count: number;
  win_rate: number;
  sharpe_ratio: number;
  circuit_breaker_active: boolean;
  trading_mode: string;
}

export interface EquityCurvePoint {
  date: string;
  equity: number;
  drawdown_pct: number;
  daily_pnl: number;
  trade_count: number;
  win_count: number;
  cumulative_trades: number;
  cumulative_win_rate: number;
}

// Positions
export interface Position {
  deal_id: string;
  epic: string;
  direction: string;
  size: number;
  entry_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  current_pnl: number;
  opened_at: string | null;
}

// Signals
export interface TradingSignal {
  id: number | null;
  epic: string;
  direction: string;
  confidence: number;
  signal_class: number;
  entry_price: number;
  suggested_stop: number | null;
  suggested_tp: number | null;
  regime: string | null;
  timestamp: string;
  status: string;
}

// Markets
export interface MarketInfo {
  epic: string;
  name: string;
  bid: number | null;
  offer: number | null;
  high: number | null;
  low: number | null;
  change_pct: number | null;
}

export interface OHLCCandle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// Strategy
export interface StrategyConfig {
  epic: string;
  min_confidence: number;
  counter_trend_penalty: number;
  stop_multiplier: number;
  risk_reward_ratio: number;
  overbought_rsi: number;
  oversold_rsi: number;
}

export interface RiskLimits {
  max_risk_per_trade: number;
  max_daily_drawdown: number;
  max_total_drawdown: number;
  max_position_pct: number;
  max_correlated_exposure: number;
}

export interface Allocation {
  weights: Record<string, number>;
  regime: string | null;
}

// Backtest
export interface BacktestRun {
  id: string;
  epic: string;
  status: string;
  total_return_pct: number | null;
  sharpe_ratio: number | null;
  max_drawdown_pct: number | null;
  total_trades: number | null;
  win_rate: number | null;
  created_at: string;
}

export interface BacktestTrade {
  trade_id: number;
  epic: string;
  direction: string;
  entry_price: number;
  entry_time: string;
  exit_price: number | null;
  exit_time: string | null;
  size: number;
  status: string;
  pnl: number;
  fees: number;
  net_pnl: number;
  bars_held: number;
}

export interface MonteCarloResult {
  n_simulations: number;
  n_trades: number;
  final_equity: { p5: number; p50: number; p95: number; original: number };
  max_drawdown: { p5: number; p50: number; p95: number; original: number };
  sharpe_ratio: { p5: number; p50: number; p95: number; original: number };
  p_value_return: number;
  risk_of_ruin: number;
}

export interface BacktestDetail {
  summary: BacktestRun;
  config: Record<string, unknown>;
  equity_curve: { timestamp: string; equity: number }[];
  trades: BacktestTrade[];
  metrics: Record<string, number>;
  trade_metrics: Record<string, number>;
  monte_carlo?: MonteCarloResult;
}

// Models
export interface MLModel {
  id: string;
  name: string;
  type: string;
  epic: string;
  status: string;
  accuracy: number;
  f1_score: number;
  last_trained: string | null;
  version: string;
  num_features?: number;
}

// System
export interface SystemSettings {
  app_name: string;
  app_version: string;
  environment: string;
  trading_enabled: boolean;
  paper_trading: boolean;
  use_demo: boolean;
  min_confidence_threshold: number;
  max_risk_per_trade: number;
  max_daily_drawdown: number;
  max_total_drawdown: number;
}

export interface RiskStatus {
  peak_equity: number;
  current_equity: number;
  current_drawdown_pct: number;
  daily_pnl: number;
  circuit_breaker_active: boolean;
  circuit_breaker_reason: string | null;
}

// WebSocket
export interface PriceTick {
  epic: string;
  bid: number;
  offer: number;
  timestamp: string;
  price_source?: 'broker' | 'mock';
}

export interface WsStatus {
  type: 'ws_status';
  price_source: 'broker' | 'mock';
  reconnect_attempts: number;
  max_reconnect_attempts: number;
}

export interface TradeEvent {
  event: 'OPEN' | 'CLOSE';
  deal_id: string;
  epic: string;
  direction: string;
  pnl: number;
  size?: number;
  fill_price?: number;
  stop_loss?: number;
  take_profit?: number;
  close_reason?: string;
  timestamp?: string;
}

// Paper Trading Status (GET /api/trading/status)
export interface PaperTradingStatus {
  running: boolean;
  execution_mode: string; // "PAPER" | "DEMO" | "LIVE"
  interval_seconds: number;
  epics: string[];
  iteration_count: number;
  check_count: number;
  last_run: string | null;
  signal_count: number;
  trade_count: number;
  error_count: number;
  open_positions: number;
  total_unrealized_pnl: number;
  last_signals: Record<string, LastSignalInfo>;
  models_loaded: Record<string, ModelLoadedInfo>;
  last_candle_timestamps: Record<string, string>;
  message?: string;
  // Phase 8 fields (backend sends dict {type: reason} or empty {})
  circuit_breakers_tripped: Record<string, string> | string[];
  trailing_stops_tracked: number;
  equity_curve_below_sma: boolean;
  kelly_trade_history_size: number;
  kelly_stats: KellyStats | null;
  spread_blocked_epics?: Record<string, { spread: number; spread_pct: number; limit_pct: number; since: string }>;
}

export interface KellyStats {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  min_required: number;
  active: boolean;
  method: string;
  avg_win?: number;
  avg_loss?: number;
  kelly_fraction?: number;
  half_kelly?: number;
}

export interface LastSignalInfo {
  direction: string;
  confidence: number;
  entry_price: number;
  timestamp: string;
  status?: string;
  rejection_reason?: string;
  error_detail?: BrokerErrorDetail;
}

export interface ModelLoadedInfo {
  model_id: string;
  model_type: string;
  num_features: number;
  created_at: string;
  version: string;
}

// Paper Trading Positions (GET /api/trading/positions)
export interface LevelDeviation {
  requested_sl: number;
  requested_tp: number;
  actual_sl: number;
  actual_tp: number;
  sl_deviation: number;     // actual - requested
  tp_deviation: number;
  sl_deviation_pct: number; // % of entry
  tp_deviation_pct: number;
}

export interface PaperPosition {
  deal_id: string;
  epic: string;
  direction: string;
  size: number;
  level: number;         // entry fill price
  stop_level: number | null;
  profit_level: number | null;
  opened_at: string;
  trailing_stop_phase?: string; // "INITIAL" | "BREAKEVEN" | "TP1_LOCK" | "TRAILING"
  risk_managed_locally?: boolean; // true if SL/TP managed by MANTIS (not broker)
  upl?: number | null;          // Broker's unrealized P&L (always accurate)
  market_status?: string | null; // TRADEABLE, CLOSED, etc.
  level_deviation?: LevelDeviation; // Difference between requested and broker-actual SL/TP
}

// Structured broker error detail (from broker_error_parser)
export interface BrokerErrorDetail {
  error_type: string;    // "market_closed", "insufficient_funds", "rate_limit", etc.
  summary: string;       // Short Italian message
  details: string | null;
  market_hours: Record<string, string> | null;
  raw: string;           // Original error message
}

// Paper Trading Signal History (GET /api/trading/signals)
export interface SlCooldownInfo {
  sl_count: number;
  max_strikes: number;
  penalty: number;       // 1.0, 0.70, 0.40, 0.0
  blocked: boolean;
  window_hours: number;
}

export interface PaperSignal {
  epic: string;
  direction: string;
  confidence: number;
  entry_price: number;
  suggested_stop?: number | null;
  suggested_tp?: number | null;
  regime?: string | null;
  timestamp: string;
  status: string;  // predicted, executed, rejected, exec_failed, hold, market_closed
  rejection_reason?: string;
  error_detail?: BrokerErrorDetail;
  strategy_name?: string;  // "ml_ensemble", "squeeze_breakout", "vwap_reversion"
  sl_cooldown?: SlCooldownInfo | null;
  _showRaw?: boolean;  // UI-only: toggle for raw error display
}

// Closed Positions History
export interface ClosedPosition {
  deal_id: string;
  epic: string;
  direction: string;
  size: number;
  entry_price: number;
  exit_price: number | null;
  profit_loss: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  close_reason: string | null;
  opened_at: string | null;
  closed_at: string | null;
  duration_minutes: number | null;
}

export interface PositionAggregates {
  total_pnl: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
}

export interface TradingPerformance {
  trade_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  total_pnl: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  best_trade: number;
  worst_trade: number;
  pnl_by_epic: Record<string, number>;
  last_trade_by_epic?: Record<string, string>;
  equity_curve: { date: string; value: number }[];
  source: string;
  sharpe_ratio?: number;
  sortino_ratio?: number;
  calmar_ratio?: number;
  max_drawdown?: number;
}

// --- Signal Audit Trail ---

export interface SignalAudit {
  id: number;
  epic: string;
  direction: 'BUY' | 'SELL';
  confidence: number;
  status: 'EXECUTED' | 'REJECTED';
  generated_at: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  position_id: number | null;
  features: SignalFeatures;
}

export interface SignalFeatures {
  version: number;
  rejection_reason: string | null;
  votes: Record<string, { value: number; [key: string]: any }>;
  gates: Record<string, { passed: boolean; [key: string]: any } | null>;
  ml: SignalMl | null;
  risk: SignalRisk | null;
  market_snapshot: Record<string, number | string>;
}

export interface SignalMl {
  signal_class: number;
  signal_name: string;
  confidence: number;
  probabilities: Record<string, number>;
  agreement: string;
  confidence_before: number;
  confidence_after: number;
}

export interface SignalRisk {
  circuit_breakers: { passed: boolean; [key: string]: any };
  drawdown: { passed: boolean; [key: string]: any };
  stop_loss: { [key: string]: any };
  correlation: { [key: string]: any };
  sizing: { [key: string]: any };
  confidence_tier: { [key: string]: any };
}

export interface SignalHistoryItem {
  id: number;
  epic: string;
  direction: 'BUY' | 'SELL';
  confidence: number;
  status: 'EXECUTED' | 'REJECTED';
  generated_at: string;
  rejection_reason: string | null;
  position_pnl: number | null;
  position_status: string | null;
}

// Notifications
export * from './notification.model';

// News and Sentiment
export * from './news.model';

// Training
export interface TrainingJobInfo {
  epic: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error: string | null;
  metrics: { f1_macro: number; accuracy: number; num_features: number } | null;
  progress: string;
}

export interface TrainingStatus {
  running: boolean;
  max_parallel: number;
  jobs: Record<string, TrainingJobInfo>;
  queue: string[];
  completed_count: number;
  failed_count: number;
}

// Authentication and Authorization
export * from './auth.models';
