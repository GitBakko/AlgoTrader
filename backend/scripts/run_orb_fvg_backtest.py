"""Run ORB+FVG backtest on all 4 US assets and print results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest.orb_fvg_runner import run_backtest, print_summary, save_result

ASSETS = ["US500", "NAS100", "NVDA", "TSLA"]
DATA_DIR = Path(__file__).parent.parent / "data" / "historical"


def main():
    print("=" * 60)
    print(" ORB+FVG Strategy - 12-Month Backtest")
    print("=" * 60)

    all_results = []

    for epic in ASSETS:
        data_path = DATA_DIR / epic / "1min"
        if not data_path.exists():
            print(f"\n[{epic}] No M1 data found, skipping")
            continue

        files = list(data_path.glob("*.parquet"))
        if not files:
            print(f"\n[{epic}] No parquet files found, skipping")
            continue

        print(f"\n[{epic}] Running backtest...")
        try:
            result = run_backtest(
                epic=epic,
                data_dir=str(DATA_DIR),
                initial_capital=10_000.0,
                risk_per_trade=0.02,
            )
            print_summary(result)
            path = save_result(result)
            print(f"  Saved to: {path}")
            all_results.append(result)
        except Exception as e:
            print(f"  [{epic}] ERROR: {e}")

    if all_results:
        print("\n" + "=" * 60)
        print(" COMBINED SUMMARY")
        print("=" * 60)
        total_trades = sum(r.trades_taken for r in all_results)
        total_pnl = sum(r.total_pnl for r in all_results)
        avg_wr = sum(r.win_rate for r in all_results) / len(all_results)
        avg_pf = sum(r.profit_factor for r in all_results) / len(all_results)
        avg_sharpe = sum(r.sharpe_ratio for r in all_results) / len(all_results)
        max_dd = max(r.max_drawdown_pct for r in all_results)

        print(f" Assets:        {len(all_results)}")
        print(f" Total Trades:  {total_trades}")
        print(f" Combined P&L:  ${total_pnl:,.2f}")
        print(f" Avg Win Rate:  {avg_wr:.1%}")
        print(f" Avg PF:        {avg_pf:.2f}")
        print(f" Avg Sharpe:    {avg_sharpe:.2f}")
        print(f" Worst DD:      {max_dd:.1%}")

        print(f"\n{'_' * 60}")
        if avg_wr > 0.50 and avg_pf > 1.5 and avg_sharpe > 1.0:
            print(" RECOMMENDATION: INTEGRATE into MANTIS (Phase 2)")
        elif avg_wr > 0.45 and avg_pf > 1.2:
            print(" RECOMMENDATION: PROMISING - add ML filter (Phase 2b)")
        else:
            print(" RECOMMENDATION: NOT VIABLE - needs redesign")
        print(f"{'_' * 60}")
    else:
        print("\nNo results. Did you download M1 data first?")
        print("Run: .venv/Scripts/python.exe scripts/download_m1_data.py")


if __name__ == "__main__":
    main()
