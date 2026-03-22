# Equity Curve Pro — Design Document

**Date**: 2026-03-10
**Goal**: Enrich the dashboard equity curve with rich tooltips, drawdown overlay, and per-point metrics.

## Backend Changes

### Enriched equity curve points

`GET /api/dashboard/equity-curve` returns enriched points:

```json
{
  "date": "2026-03-09",
  "equity": 10250.50,
  "daily_pnl": 45.20,
  "drawdown_pct": -2.1,
  "trade_count": 3,
  "win_count": 2,
  "cumulative_trades": 42,
  "cumulative_win_rate": 0.548
}
```

Calculated in `PositionRepository.get_performance_stats()`:
- `drawdown_pct`: peak-to-current percentage (running max)
- `daily_pnl`: sum of P&L for trades closed that day
- `trade_count` / `win_count`: daily counts
- `cumulative_trades` / `cumulative_win_rate`: running totals up to that point

### Files modified
- `backend/src/database/repositories/position_repository.py` — enrich equity_curve loop
- `backend/src/api/routers/dashboard.py` — pass new fields in EquityCurvePoint schema

## Frontend Changes

### Drawdown overlay (Bloomberg style)
- Second `AreaSeries` with negative drawdown % values
- Red semi-transparent fill (`rgba(255, 61, 87, 0.15)`)
- Separate left price scale
- Renders beneath the green equity curve

### Custom HTML tooltip
- Absolute-positioned div over chart, follows crosshair via `subscribeCrosshairMove`
- Compact 2-line layout:
  ```
  09 Mar 2026                         Equity: $10,250.50
  Day P&L: +$45.20  |  DD: -2.1%  |  3 trades (2W)  |  WR: 54.8%
  ```
- Semantic colors: P&L green/red, drawdown red, WR green >50% / red <40%
- Disappears when mouse leaves chart

### Files modified
- `frontend/src/app/shared/components/tv-chart/tv-chart.component.ts` — tooltip + drawdown series
- `frontend/src/app/views/dashboard/dashboard.component.ts` — compute drawdown series data
- `frontend/src/app/views/dashboard/dashboard.component.html` — no major changes

## Not included (YAGNI)
- Trade markers on chart (too noisy with 200+ trades)
- Click-to-lock tooltip
- Custom zoom/pan (Lightweight Charts handles this)
