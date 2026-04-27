/**
 * Paper Trading v2 — typed contracts shared by the cockpit page.
 *
 * Source: docs/handoff/paper-trading/HANDOFF.md §3 + §6.
 * Naming follows the handoff verbatim. Where the handoff used a euro-suffixed
 * field (`pnlEur`), the value is the position P&L expressed in the active
 * account currency (broker decides — Capital.com demo = "USDd"). Currency
 * formatting stays at the view layer.
 */

import type { CockpitState, CockpitMode, CockpitMarketStatus } from '../../shared/components/cockpit-header/cockpit-header.component';

export type PaperState = CockpitState;
export type PaperMode = CockpitMode;
export type MarketStatus = CockpitMarketStatus;
export type GaugeStatus = 'OK' | 'WARN' | 'ATTIVO' | 'ERROR' | 'PAUSED';
export type Direction = 'BUY' | 'SELL';
export type SignalDirection = Direction | 'HOLD';
export type SignalCellState = 'live' | 'closed' | 'rejected' | 'hold';
export type ModelStatus = 'ok' | 'missing' | 'stale';
export type FeedKind =
  | 'iteration'
  | 'signal-emit'
  | 'signal-reject'
  | 'position-open'
  | 'position-close'
  | 'error'
  | 'model-load';

/** Bot Vitals panel — heartbeat ECG + iter/uptime/errors + signals donut. */
export interface BotVitals {
  state: PaperState;
  uptime: string;
  lastTickAgo: number;
  iterations: number;
  intervalSec: number;
  errors: number;
  signals: BotSignalsBreakdown;
}

export interface BotSignalsBreakdown {
  total: number;
  executed: number;
  rejected: number;
  hold: number;
  /** Conversion ratio executed / total, 0..1. View renders as percentage. */
  conversion: number;
}

/** Risk Gauge Stack — 4 gauges (CB / Equity Filter / Kelly / Trading Stops). */
export interface RiskState {
  circuitBreakers: RiskCircuitBreakers;
  equityFilter: RiskEquityFilter;
  kelly: RiskKelly;
  tradingStops: RiskTradingStops;
}

export interface RiskCircuitBreakers {
  status: GaugeStatus;
  tripped: number;
  total: number;
}

export interface RiskEquityFilter {
  status: GaugeStatus;
  /** Current drawdown percent (0..100). */
  dd: number;
  /** Threshold percent (0..100). */
  threshold: number;
}

export interface RiskKelly {
  status: GaugeStatus;
  avg: number;
  /** Win rate percent (0..100). */
  win: number;
  /** Cumulative P&L in account currency. */
  pnl: number;
}

export interface RiskTradingStops {
  status: GaugeStatus;
  count: number;
}

/** Models Health Panel — header counts + per-asset status grid. */
export interface ModelsHealth {
  loaded: number;
  total: number;
  perAsset: ModelHealthCell[];
  meta?: ModelsHealthMeta;
}

export interface ModelHealthCell {
  epic: string;
  status: ModelStatus;
  /** Hex color used to tint the cell background/border. Falls back to neutral. */
  accent?: string;
}

/** Aggregate model metadata shown in the panel footer. */
export interface ModelsHealthMeta {
  /** Total feature count of the primary model (or aggregate). */
  features: number;
  version: string;
  /** Last trained date in dd/MM/yy. */
  lastTrained: string;
}

/** KPI Strip Compact — 6 cells. */
export interface KpiStrip {
  pnlOpen: number;
  pnlToday: number;
  openCount: number;
  /** Win rate percent (0..100). */
  winRate: number;
  signalsTotal: number;
  /** Risk-reward avg (e.g. 1.94 means 1:1.94). */
  rr: number;
  /** Live drawdown percent (negative or 0..-100). */
  ddLive: number;
  /** Drawdown gate threshold percent (e.g. 20). */
  ddGate: number;
  sparkOpen?: number[];
  sparkToday?: number[];
}

/** Position Card — the 7 mandatory fields per HANDOFF §3.6. */
export interface PaperTradingPosition {
  id: string;
  ticker: string;
  direction: Direction;
  /** Lots / size as reported by broker. */
  size: number;
  entry: number;
  stopLoss: number;
  takeProfit: number;
  current: number;
  /** Unrealized P&L in account currency. */
  pnlEur: number;
  /** Unrealized P&L percent vs entry notional. */
  pnlPct: number;
  /** Position uptime in seconds. */
  ageSec: number;
  trailing: boolean;
  /** Risk-reward ratio achieved at current price. */
  rr: number;
  /** 60-point sparkline of price since entry. */
  pricePath: number[];
}

/** Signals Heatmap cell — one per asset (21 total). */
export interface AssetSignal {
  epic: string;
  direction: SignalDirection;
  /** Confidence 0..100. */
  confidence: number;
  state: SignalCellState;
  /** HH:mm in user locale. */
  time: string;
}

/** Live Feed Timeline event row. */
export interface FeedEvent {
  id: string;
  /** ISO timestamp. */
  ts: string;
  kind: FeedKind;
  title: string;
  meta?: string;
}

/** GET /api/paper/state — composite live status. */
export interface PaperLoopState {
  status: PaperState;
  mode: PaperMode;
  uptime: string;
  iterations: number;
  errors: number;
  /** ISO timestamp of last tick. */
  lastTick: string;
  signals: BotSignalsBreakdown;
}

/** POST /api/paper/stop — generic ack. */
export interface PaperActionResponse {
  ok: boolean;
  message?: string;
}

/** POST /api/paper/emergency — close-all ack. */
export interface PaperEmergencyResponse extends PaperActionResponse {
  closed: number;
}
