/**
 * Shape expected from `GET /api/trading/performance/breakdown?tf=...`
 * (backend endpoint pending — see sprint plan).
 */
export interface TradeBreakdownDay {
  date: string;               // 'YYYY-MM-DD' UTC
  buy:  TradeOutcomeSide;
  sell: TradeOutcomeSide;
}

export interface TradeOutcomeSide {
  tp: number;
  sl: number;
  going: number;
  pnl: number;
}

export interface TradeBreakdownResponse {
  timeframe: string;
  days: TradeBreakdownDay[];  // ordered oldest → newest, weekends included with zero counts
}
