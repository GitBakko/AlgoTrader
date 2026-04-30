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
  /** today_realized + sum(open.upl) — used for the Live P&L hero. */
  live_daily_pnl?: number;
  live_unrealized_pnl?: number;
  /** ISO 4217 currency code from broker account (e.g. "USD", "EUR"). */
  currency?: string;
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

/**
 * Live cockpit activity feed event (HANDOFF §3.8 + mocks/SignalsAndFeed.jsx).
 * One row per event from the merged backend stream `/api/trading/events`:
 * signals (emit / reject / pending), positions (open / close), notifications
 * (alerts, model lifecycle, errors).
 *
 * The structured fields (direction, confidence, price, strategy, detail) let
 * the FeedRow render the rich timeline shown in the mock — asset glyph +
 * strategy chip + direction badge + confidence + price + reason — without
 * extra round-trips per row.
 */
export interface FeedEvent {
  id: string;
  ts: string;
  kind:
    | 'signal-emit'
    | 'signal-reject'
    | 'signal-pending'
    | 'position-open'
    | 'position-close'
    | 'model-load'
    | 'error'
    | 'alert'
    | 'iteration';
  epic: string | null;
  /** Trade direction normalized to upper-case (`BUY|SELL|HOLD`). */
  direction?: string | null;
  /** Confidence percent (0..100), null when not available. */
  confidence?: number | null;
  /** Reference price (signal entry, position entry). */
  price?: number | null;
  /** Strategy that emitted the signal, e.g. `mean_reversion`/`ml_ensemble`. */
  strategy?: string | null;
  /** Human-readable reason or context (rejection reason, close reason+pnl). */
  detail?: string | null;
  title: string;
  /** Free-form caption (close_reason for position-close, strategy for
   *  signals). NEVER use as routing key — `deal_id` carries that. */
  meta?: string | null;
  /** Broker deal_id for position-open and position-close events.
   *  Routes the click handler to `signalAudit.openByDealId(...)`
   *  authoritatively, so pos-close- rows don't fall through to the
   *  openLatestByEpic fallback (which would surface the most recent
   *  signal — usually a HOLD reject — instead of the actual closed
   *  position's source signal). */
  deal_id?: string | null;
  severity?: 'info' | 'warning' | 'error' | 'critical' | string | null;
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
  /** ISO timestamp of the last *signal-generation* iteration (only fires when
   *  a new candle of the configured resolution closes — every 4h on
   *  mr_primary). Use `last_check_at` for housekeeping liveness. */
  last_run: string | null;
  /** ISO timestamp of the last housekeeping check (broker sync, reconciliation,
   *  trailing-stop update, SL violation, spread refresh). Updates every
   *  `interval_seconds` (15min by default) regardless of candle close —
   *  this is the right field to feed the cockpit "last tick" chip. */
  last_check_at?: string | null;
  /** ISO timestamp of the last successful loop start (Dashboard v2 uptime). */
  started_at?: string | null;
  /** Seconds since the loop started (Dashboard v2 uptime). */
  uptime_seconds?: number;
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
  // Dashboard v2 extensions
  tp_hit_rate?: number;
  tp_count?: number;
  daily_trade_count?: number;
  duration_medians?: DurationMedians | null;
}

export interface DurationMedians {
  win_avg_min: number;
  loss_avg_min: number;
  win_count: number;
  loss_count: number;
  late_exit_bias: boolean;
  bias_pct_over: number;
}

// Dashboard v2 — /api/trading/performance/breakdown
export interface TradeBreakdownOutcome {
  tp: number;
  sl: number;
  going: number;
  pnl: number;
}

export interface TradeBreakdownDay {
  date: string;
  buy: TradeBreakdownOutcome;
  sell: TradeBreakdownOutcome;
}

export interface TradeBreakdownResponse {
  timeframe: string;
  from?: string;
  to?: string;
  days: TradeBreakdownDay[];
  source: string;
}

// Dashboard v2 — /api/models/current
export interface CurrentModelInfo {
  model_id: string;
  model_type: string;
  num_features: number;
  version: string;
  last_trained: string | null;
}

export interface CurrentModelsResponse {
  count: number;
  by_epic: Record<string, CurrentModelInfo>;
  primary: (CurrentModelInfo & { epic: string }) | null;
}

// Dashboard v2 — /api/trading/performance/delta (Phase 4 §A)
export interface PerformanceDeltaResponse {
  timeframe: string;
  date_from: string;
  date_to: string;
  prev_from: string;
  prev_to: string;
  win_rate_current: number | null;
  win_rate_previous: number | null;
  delta_pp: number | null;
  n_current: number;
  n_previous: number;
  wins_current: number;
  losses_current: number;
  source: string;
}

// Dashboard v2 — /api/markets/{epic}/swap-accum (Phase 4 §B)
export interface SwapAccumDay {
  date: string;
  rate_pct: number;
  notional: number;
  swap: number;
}

export interface SwapAccumResponse {
  epic: string;
  currency: string;
  period_days: number;
  total_accum: number;
  per_day: SwapAccumDay[];
  source: string;
}

// Dashboard v2 — /api/markets/{epic}/overnight-swap
export interface OvernightSwapResponse {
  epic: string;
  currency: string;
  long_rate_daily: number;
  short_rate_daily: number;
  long_rate_pct: number;
  short_rate_pct: number;
  weekend_multiplier: number;
  next_charge_utc: string;
  source: 'broker' | 'static_fallback';
  instrument_raw?: Record<string, unknown> | null;
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
  /** Broker deal_id resolved from position_id at audit fetch time.
   *  Present only when status='EXECUTED' AND the signal is wired to a
   *  positions row. Used to drive the History tab in the audit drawer. */
  deal_id?: string | null;
  /** Position lifecycle status from positions.status (OPEN/CLOSED).
   *  Distinct from `status` (signal status: EXECUTED/REJECTED). */
  position_status?: 'OPEN' | 'CLOSED' | null;
  /** Position close_reason from positions.close_reason (TP/SL/MANUAL/...). */
  close_reason?: string | null;
  /** Realised P&L from positions.profit_loss (null while position is open). */
  position_profit_loss?: number | null;
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
  // Backend may omit a class entirely when its probability rounds to 0,
  // so each key is independently optional. Using Partial<Record> tells
  // the template the `?? 0` guards aren't dead code (silences NG8102).
  probabilities: Partial<Record<'buy' | 'sell' | 'hold', number>>;
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

// Paper Trading v2 (cockpit page)
export * from './paper-trading';

// Paper Trading v2 — 60s P&L snapshot history
export interface PaperPnlSnapshotPoint {
  ts: string;
  pnl_open: number;
  pnl_today: number;
  equity: number | null;
  open_count: number;
}

export interface PaperPnlHistoryResponse {
  points: PaperPnlSnapshotPoint[];
  minutes: number;
  source: string;
}

export interface PositionPnlSnapshotPoint {
  ts: string;
  pnl: number;
  pnl_pct: number;
  price: number;
}

export interface PositionPnlHistoryResponse {
  deal_id: string;
  points: PositionPnlSnapshotPoint[];
  minutes: number;
  source: string;
}

export interface PositionEvent {
  ts: string | null;
  /** Audit trail event type. Trailing-stop transitions:
   *   BREAKEVEN  — INITIAL → BREAKEVEN (price reached TP1, SL → entry)
   *   TP1_LOCK   — BREAKEVEN → TP1_LOCK (price reached TP2, SL → TP1)
   *   TP1_HIT    — partial close 50% at TP1 midpoint
   *   TRAIL_UPD  — ATR ratchet within TRAILING phase
   * Plus the legacy OPEN / CLOSE / MODIFY codes. */
  type: string;
  deal_reference: string | null;
  size: number | null;
  price: number | null;
  profit_loss: number | null;
  commission: number | null;
  close_reason?: string | null;
  /** Free-form audit reason. For trailing transitions this carries the
   *  human-readable explanation rendered as a tooltip in the drawer. */
  notes?: string | null;
  synthesised?: boolean;
}

export interface PositionEventsResponse {
  deal_id: string;
  events: PositionEvent[];
  position: {
    id: number | null;
    epic: string;
    direction: string;
    status: string;
    opened_at: string | null;
    closed_at: string | null;
    close_reason: string | null;
    entry_price: number | null;
    stop_loss: number | null;
    take_profit: number | null;
    profit_loss: number | null;
    size: number | null;
  } | null;
  source: string;
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
