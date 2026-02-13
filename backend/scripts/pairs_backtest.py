"""
Pairs backtest script for Gold-Bitcoin cointegration strategy.

Loads historical data for XAUUSD and BTCUSD, runs the pairs backtester,
and optionally runs Monte Carlo validation.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/pairs_backtest.py
    .venv/Scripts/python.exe scripts/pairs_backtest.py --equity 20000 --monte-carlo
    .venv/Scripts/python.exe scripts/pairs_backtest.py --timeframe 4h --entry-z 1.5
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from loguru import logger

from src.backtest.pairs_backtester import PairsBacktester
from src.data.storage import ParquetStorageManager
from src.strategy.pairs.pairs_strategy import PairsConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Pairs Backtest Gold-Bitcoin")
    parser.add_argument("--timeframe", default="1h", choices=["1h", "4h", "1d"])
    parser.add_argument("--equity", type=float, default=10000.0)
    parser.add_argument("--entry-z", type=float, default=2.0, help="Z-score entry threshold")
    parser.add_argument("--exit-z", type=float, default=0.5, help="Z-score exit threshold")
    parser.add_argument("--stop-z", type=float, default=3.0, help="Z-score stop-loss")
    parser.add_argument("--max-hold", type=int, default=168, help="Max bars to hold")
    parser.add_argument("--cost", type=float, default=0.001, help="Transaction cost per leg (%)")
    parser.add_argument("--monte-carlo", action="store_true", help="Run Monte Carlo validation")
    parser.add_argument("--mc-sims", type=int, default=10000, help="Monte Carlo simulations")
    args = parser.parse_args()

    data_dir = Path(__file__).parent.parent / "data" / "historical"
    storage = ParquetStorageManager(str(data_dir))

    # Load XAUUSD and BTCUSD
    logger.info(f"Loading XAUUSD and BTCUSD data (timeframe={args.timeframe})...")
    df_gold = storage.read_candles("XAUUSD", args.timeframe)
    df_btc = storage.read_candles("BTCUSD", args.timeframe)

    if df_gold.is_empty() or df_btc.is_empty():
        logger.error("No data found. Run download_data.py first.")
        sys.exit(1)

    logger.info(f"  XAUUSD: {len(df_gold)} candles")
    logger.info(f"  BTCUSD: {len(df_btc)} candles")

    # Align by timestamp (inner join)
    df_gold = df_gold.sort("timestamp")
    df_btc = df_btc.sort("timestamp")

    merged = df_gold.select(["timestamp", "close"]).rename({"close": "close_a"}).join(
        df_btc.select(["timestamp", "close"]).rename({"close": "close_b"}),
        on="timestamp",
        how="inner",
    )

    logger.info(f"  Aligned: {len(merged)} overlapping bars")

    if len(merged) < 400:
        logger.error("Not enough overlapping data (need at least 400 bars)")
        sys.exit(1)

    prices_a = merged["close_a"].to_numpy().astype(np.float64)
    prices_b = merged["close_b"].to_numpy().astype(np.float64)

    # Configure and run
    config = PairsConfig(
        entry_z=args.entry_z,
        exit_z=args.exit_z,
        stop_z=args.stop_z,
        max_hold_bars=args.max_hold,
        equity_per_leg=args.equity / 2,
    )

    logger.info(
        f"\nRunning pairs backtest: entry_z={config.entry_z}, exit_z={config.exit_z}, "
        f"stop_z={config.stop_z}, max_hold={config.max_hold_bars} bars"
    )

    backtester = PairsBacktester(config)
    result = backtester.run(
        prices_a=prices_a,
        prices_b=prices_b,
        initial_equity=args.equity,
        transaction_cost_pct=args.cost,
    )

    # Print results
    print("\n" + "=" * 60)
    print("PAIRS BACKTEST RESULTS: XAUUSD / BTCUSD")
    print("=" * 60)
    print(f"  Timeframe:        {args.timeframe}")
    print(f"  Bars:             {len(merged)}")
    print(f"  Initial equity:   ${args.equity:,.2f}")
    print(f"  Final equity:     ${result.final_equity:,.2f}")
    print(f"  Total P&L:        ${result.total_pnl:,.2f} ({result.total_pnl / args.equity * 100:+.1f}%)")
    print(f"  Total trades:     {result.total_trades}")
    print(f"  Win rate:         {result.win_rate:.1%}")
    print(f"  Avg win:          ${result.avg_win:,.2f}")
    print(f"  Avg loss:         ${result.avg_loss:,.2f}")
    print(f"  Avg hold bars:    {result.avg_hold_bars:.1f}")
    print(f"  Max drawdown:     {result.max_drawdown_pct:.1%}")
    print(f"  Sharpe ratio:     {result.sharpe_ratio:.2f}")

    if result.trades:
        print(f"\n  Last 5 trades:")
        for t in result.trades[-5:]:
            print(
                f"    {t['action']:15s} PnL=${t['pnl']:+8.2f} "
                f"bars={t['bars_held']:3d} {t['exit_reason']}"
            )

    # Monte Carlo validation
    if args.monte_carlo and result.trades:
        from src.backtest.monte_carlo import MonteCarloSimulator

        logger.info(f"\nRunning Monte Carlo ({args.mc_sims} simulations)...")
        mc = MonteCarloSimulator(n_simulations=args.mc_sims)
        mc_result = mc.run(
            trades=result.trades,
            initial_capital=args.equity,
            original_metrics={
                "final_equity": result.final_equity,
                "max_drawdown": result.max_drawdown_pct,
                "sharpe": result.sharpe_ratio,
            },
        )

        print(f"\n  Monte Carlo ({mc_result.n_simulations} sims):")
        print(f"    Equity CI (5/50/95):    ${mc_result.final_equity_ci[0]:,.0f} / "
              f"${mc_result.final_equity_ci[1]:,.0f} / ${mc_result.final_equity_ci[2]:,.0f}")
        print(f"    Max DD CI (5/50/95):    {mc_result.max_drawdown_ci[0]:.1%} / "
              f"{mc_result.max_drawdown_ci[1]:.1%} / {mc_result.max_drawdown_ci[2]:.1%}")
        print(f"    P-value (random>=actual): {mc_result.p_value_return:.4f}")
        print(f"    Risk of ruin (50% loss):  {mc_result.risk_of_ruin:.4f}")

    print("=" * 60)


if __name__ == "__main__":
    main()
