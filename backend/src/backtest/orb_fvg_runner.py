"""
ORB+FVG M1 Backtest Runner.

Loads per-day M1 parquet data, runs the ORB+FVG session logic on each day,
simulates trades bar-by-bar (SL / TP / EOD exits), and produces summary
metrics (win rate, Sharpe, profit factor, drawdown, etc.).
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path

import polars as pl
from loguru import logger

from src.strategy.orb_fvg_strategy import (
    FVGSignal,
    _minutes_utc,
    _nyse_utc_minutes,
    _NYSE_SESSION_END,
    process_session,
)
from src.strategy.schemas import SignalDirection

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ORBTrade:
    """Single ORB+FVG trade result."""

    date: str
    epic: str
    direction: str  # "BUY" / "SELL"
    orb_high: float
    orb_low: float
    fvg_type: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float = 0.0
    exit_reason: str = ""  # "TP" / "SL" / "EOD"
    pnl: float = 0.0
    bars_in_trade: int = 0


@dataclass
class ORBBacktestResult:
    """Aggregate result for a full backtest run."""

    epic: str
    period: str
    total_sessions: int = 0
    trades_taken: int = 0
    sessions_skipped: int = 0
    win_rate: float = 0.0
    avg_rr_achieved: float = 0.0
    total_pnl: float = 0.0
    max_consecutive_losses: int = 0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    trades: list[ORBTrade] = field(default_factory=list)
    daily_equity: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------


def _simulate_trade(
    fvg: FVGSignal,
    bars_after_entry: list[dict],
    epic: str,
    date_str: str,
) -> ORBTrade:
    """
    Walk through *bars_after_entry* bar-by-bar checking for SL, TP, or EOD.

    Returns a filled ORBTrade with raw (unscaled) P&L.
    """
    is_buy = fvg.direction == SignalDirection.BUY

    trade = ORBTrade(
        date=date_str,
        epic=epic,
        direction="BUY" if is_buy else "SELL",
        orb_high=0.0,  # filled by caller if needed
        orb_low=0.0,
        fvg_type=fvg.fvg_type,
        entry_price=fvg.entry_price,
        stop_loss=fvg.stop_loss,
        take_profit=fvg.take_profit,
    )

    # Compute session end for this date (DST-aware)
    if bars_after_entry:
        session_end_utc = _nyse_utc_minutes(bars_after_entry[0]["timestamp"], _NYSE_SESSION_END)
    else:
        session_end_utc = 20 * 60  # fallback: 20:00 UTC

    for idx, bar in enumerate(bars_after_entry):
        # Check EOD first — if we are at/past session end, close at bar close
        if _minutes_utc(bar["timestamp"]) >= session_end_utc:
            trade.exit_price = bar["close"]
            trade.exit_reason = "EOD"
            trade.bars_in_trade = idx + 1
            break

        if is_buy:
            # SL hit?
            if bar["low"] <= fvg.stop_loss:
                trade.exit_price = fvg.stop_loss
                trade.exit_reason = "SL"
                trade.bars_in_trade = idx + 1
                break
            # TP hit?
            if bar["high"] >= fvg.take_profit:
                trade.exit_price = fvg.take_profit
                trade.exit_reason = "TP"
                trade.bars_in_trade = idx + 1
                break
        else:
            # SL hit?
            if bar["high"] >= fvg.stop_loss:
                trade.exit_price = fvg.stop_loss
                trade.exit_reason = "SL"
                trade.bars_in_trade = idx + 1
                break
            # TP hit?
            if bar["low"] <= fvg.take_profit:
                trade.exit_price = fvg.take_profit
                trade.exit_reason = "TP"
                trade.bars_in_trade = idx + 1
                break
    else:
        # Ran out of bars without hitting SL/TP/EOD — close at last bar
        if bars_after_entry:
            last = bars_after_entry[-1]
            trade.exit_price = last["close"]
            trade.exit_reason = "EOD"
            trade.bars_in_trade = len(bars_after_entry)

    # Raw P&L (unscaled)
    if is_buy:
        trade.pnl = trade.exit_price - trade.entry_price
    else:
        trade.pnl = trade.entry_price - trade.exit_price

    return trade


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _calculate_metrics(
    result: ORBBacktestResult,
    initial_capital: float,
) -> None:
    """Compute aggregate metrics in-place on *result*."""
    trades = result.trades

    if not trades:
        return

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    result.trades_taken = len(trades)
    result.win_rate = len(wins) / len(trades) if trades else 0.0
    result.total_pnl = sum(pnls)

    # Profit factor
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    result.profit_factor = (
        gross_profit / gross_loss if gross_loss > 0 else float("inf")
    )

    # Average R:R achieved
    rr_values: list[float] = []
    for t in trades:
        risk = abs(t.entry_price - t.stop_loss)
        if risk > 0:
            rr_values.append(t.pnl / risk)
    result.avg_rr_achieved = (
        statistics.mean(rr_values) if rr_values else 0.0
    )

    # Max consecutive losses
    max_cl = 0
    current_cl = 0
    for p in pnls:
        if p <= 0:
            current_cl += 1
            max_cl = max(max_cl, current_cl)
        else:
            current_cl = 0
    result.max_consecutive_losses = max_cl

    # Max drawdown %
    equity = initial_capital
    peak = equity
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    result.max_drawdown_pct = max_dd

    # Sharpe ratio (annualised, daily-ish returns)
    if len(pnls) >= 2:
        mean_pnl = statistics.mean(pnls)
        std_pnl = statistics.stdev(pnls)
        result.sharpe_ratio = (
            (mean_pnl / std_pnl) * sqrt(252) if std_pnl > 0 else 0.0
        )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_backtest(
    epic: str,
    data_dir: str = "data/historical",
    initial_capital: float = 10_000.0,
    risk_per_trade: float = 0.02,
) -> ORBBacktestResult:
    """
    Run an ORB+FVG backtest over all available M1 parquet data for *epic*.

    Returns an ORBBacktestResult with per-trade details and aggregate metrics.
    """
    parquet_dir = Path(data_dir) / epic / "1min"

    files = sorted(parquet_dir.glob("*.parquet")) if parquet_dir.exists() else []
    if not files:
        logger.warning("No M1 parquet files found in {}", parquet_dir)
        return ORBBacktestResult(epic=epic, period="N/A")

    # Load and concatenate all parquet files
    frames = [pl.read_parquet(str(f)) for f in files]
    df = pl.concat(frames).sort("timestamp")

    # Add a date column and group by trading day
    df = df.with_columns(pl.col("timestamp").dt.date().alias("trade_date"))
    dates = df["trade_date"].unique().sort().to_list()

    first_date = str(dates[0]) if dates else "?"
    last_date = str(dates[-1]) if dates else "?"
    period = f"{first_date} to {last_date}"

    result = ORBBacktestResult(epic=epic, period=period)
    equity = initial_capital

    for d in dates:
        result.total_sessions += 1

        day_df = df.filter(pl.col("trade_date") == d)
        day_bars = day_df.drop("trade_date").to_dicts()

        # Ensure timestamps are datetime objects
        for bar in day_bars:
            ts = bar["timestamp"]
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    bar["timestamp"] = ts.replace(tzinfo=timezone.utc)
            else:
                # polars may return date or string — skip this day
                continue

        fvg = process_session(day_bars)

        if fvg is None:
            result.sessions_skipped += 1
            result.daily_equity.append(equity)
            continue

        # Find bars after entry for simulation
        # Entry is at C4.open — find the bar index in day_bars
        entry_idx = None
        for i, bar in enumerate(day_bars):
            if (
                abs(bar["open"] - fvg.entry_price) < 1e-9
                and _minutes_utc(bar["timestamp"]) > _minutes_utc(fvg.c2_bar["timestamp"])
            ):
                entry_idx = i
                break

        if entry_idx is None:
            # Fallback: approximate as ORB(5) + FVG(3) = bar 8 after ORB start
            entry_idx = min(8, len(day_bars) - 1)

        bars_after = day_bars[entry_idx + 1:]

        # Position sizing: risk-based
        risk_per_unit = abs(fvg.entry_price - fvg.stop_loss)
        if risk_per_unit <= 0:
            result.sessions_skipped += 1
            result.daily_equity.append(equity)
            continue

        position_size = (equity * risk_per_trade) / risk_per_unit
        date_str = str(d)

        trade = _simulate_trade(fvg, bars_after, epic, date_str)
        trade.orb_high = max(
            (b["high"] for b in day_bars[:5]), default=0.0
        )
        trade.orb_low = min(
            (b["low"] for b in day_bars[:5]), default=0.0
        )

        # Scale P&L by position size
        trade.pnl = trade.pnl * position_size
        equity += trade.pnl

        result.trades.append(trade)
        result.daily_equity.append(equity)

    _calculate_metrics(result, initial_capital)
    return result


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def save_result(
    result: ORBBacktestResult,
    output_dir: str = "data/backtest_results",
) -> Path:
    """Serialise backtest result to JSON and return the file path."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    filename = f"orb_fvg_{result.epic}_{result.period.replace(' ', '_')}.json"
    filepath = out / filename
    filepath.write_text(json.dumps(asdict(result), indent=2, default=str))
    logger.info("Saved backtest result to {}", filepath)
    return filepath


def print_summary(result: ORBBacktestResult) -> None:
    """Pretty-print backtest summary to console."""
    print(f"\n{'=' * 60}")
    print(f"  ORB+FVG Backtest: {result.epic}")
    print(f"  Period: {result.period}")
    print(f"{'=' * 60}")
    print(f"  Total sessions:         {result.total_sessions}")
    print(f"  Trades taken:           {result.trades_taken}")
    print(f"  Sessions skipped:       {result.sessions_skipped}")
    print(f"  Win rate:               {result.win_rate:.1%}")
    print(f"  Avg R:R achieved:       {result.avg_rr_achieved:.2f}")
    print(f"  Total P&L:              {result.total_pnl:,.2f}")
    print(f"  Profit factor:          {result.profit_factor:.2f}")
    print(f"  Max consec. losses:     {result.max_consecutive_losses}")
    print(f"  Max drawdown:           {result.max_drawdown_pct:.1%}")
    print(f"  Sharpe ratio:           {result.sharpe_ratio:.2f}")
    print(f"{'=' * 60}\n")
