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
}

export interface TradeEvent {
  event: string;
  deal_id: string;
  epic: string;
  direction: string;
  pnl: number;
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
export interface PaperSignal {
  epic: string;
  direction: string;
  confidence: number;
  entry_price: number;
  timestamp: string;
  status: string;  // predicted, executed, rejected, exec_failed, hold, market_closed
  rejection_reason?: string;
  error_detail?: BrokerErrorDetail;
  strategy_name?: string;  // "ml_ensemble", "squeeze_breakout", "vwap_reversion"
  _showRaw?: boolean;  // UI-only: toggle for raw error display
}
