"""
Train and evaluate the ORB+FVG ML filter for US500 using walk-forward testing.

Walk-forward: train on first N trades, predict trade N+1, retrain every 20 trades.
No look-ahead bias — the model only sees past trades when making predictions.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/train_orb_fvg_filter.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest.orb_fvg_ml_filter import (
    build_training_data,
    train_filter,
    run_walkforward_backtest,
    FEATURE_NAMES,
)


def main():
    print("=" * 60)
    print(" ORB+FVG ML Filter — Walk-Forward Backtest")
    print("=" * 60)

    # Step 1: Build training data for CV analysis
    print("\n[1/3] Building training data from US500 backtest...")
    X, y = build_training_data(epic="US500")
    print(f"  Samples: {len(y)}, Wins: {y.sum()} ({y.mean():.1%}), Losses: {len(y) - y.sum()}")

    # Step 2: Cross-validation analysis (for feature importance only)
    print("\n[2/3] CV analysis (feature importance)...")
    result = train_filter(X, y, n_splits=5)

    print(f"  CV Avg F1: {result['avg_f1']:.3f}")
    print(f"\n  Feature Importance:")
    sorted_imp = sorted(result["feature_importance"].items(), key=lambda x: -x[1])
    for name, imp in sorted_imp:
        bar = "#" * int(imp * 50)
        print(f"    {name:25s} {imp:.3f} {bar}")

    # Step 3: Walk-forward backtest (proper out-of-sample)
    print("\n[3/3] Walk-forward backtest (train_window=60, retrain every 20)...")
    print(f"  First 60 trades: no filter (training phase)")
    print(f"  Trade 61+: ML filter active, retrained every 20 trades")

    header = f"  {'Threshold':>10} {'Trades':>8} {'WR':>8} {'PF':>8} {'Sharpe':>8} {'DD':>8} {'P&L':>12} {'Filtered':>10}"
    print(f"\n{header}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12} {'-'*10}")

    for threshold in [0.0, 0.30, 0.40, 0.50, 0.60]:
        comparison = run_walkforward_backtest(
            epic="US500",
            train_window=60,
            threshold=threshold if threshold > 0 else 999,  # 999 = always trade
        )

        r = comparison["filtered"]
        fo = comparison["filtered_out_total"]
        fow = comparison["filtered_out_would_win"]
        fol = comparison["filtered_out_would_lose"]

        label = "baseline" if threshold == 0 else f"p>={threshold:.2f}"
        print(
            f"  {label:>10} "
            f"{r.trades_taken:>8} "
            f"{r.win_rate:>7.1%} "
            f"{r.profit_factor:>8.2f} "
            f"{r.sharpe_ratio:>8.2f} "
            f"{r.max_drawdown_pct:>7.1%} "
            f"{'${:,.0f}'.format(r.total_pnl):>12} "
            f"{fo:>5} ({fow}W/{fol}L)"
        )

    print("\n" + "=" * 60)
    print(" DONE — Results above are TRUE out-of-sample (walk-forward)")
    print("=" * 60)


if __name__ == "__main__":
    main()
