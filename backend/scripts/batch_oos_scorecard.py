"""
Batch walk-forward OOS scorecard for all tradable assets.

Runs walk-forward backtest with threshold sweep and Monte Carlo
for each of the 20 tradable assets, builds scorecards, and saves
optimal per-asset confidence thresholds.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/batch_oos_scorecard.py
    .venv/Scripts/python.exe scripts/batch_oos_scorecard.py --no-monte-carlo
    .venv/Scripts/python.exe scripts/batch_oos_scorecard.py --epic XAUUSD
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from scripts.walk_forward_backtest import run_walk_forward_backtest
from src.backtest.scorecard import (
    WalkForwardResult,
    build_scorecards,
    format_scorecard_table,
    save_optimal_thresholds,
)
from src.utils.constants import TRADABLE_ASSETS

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "config" / "optimal_thresholds.json"


def main():
    parser = argparse.ArgumentParser(description="Batch Walk-Forward OOS Scorecard")
    parser.add_argument("--epic", type=str, default=None, help="Run for a single epic only")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (default: 1h)")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Initial capital")
    parser.add_argument("--risk", type=float, default=0.02, help="Risk per trade fraction")
    parser.add_argument("--tune", action="store_true", help="Enable Optuna tuning per asset")
    parser.add_argument("--tune-trials", type=int, default=40, help="Optuna trials")
    parser.add_argument("--no-monte-carlo", action="store_true", help="Skip Monte Carlo validation")
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT_PATH),
        help="Output path for optimal_thresholds.json",
    )
    args = parser.parse_args()

    epics = [args.epic] if args.epic else list(TRADABLE_ASSETS)
    do_mc = not args.no_monte_carlo
    output_path = Path(args.output)

    logger.info(f"Batch OOS Scorecard: {len(epics)} assets, timeframe={args.timeframe}")
    logger.info(f"Monte Carlo: {'ON' if do_mc else 'OFF'}, Tune: {'ON' if args.tune else 'OFF'}")
    logger.info(f"Output: {output_path}")

    results: list[WalkForwardResult] = []
    failed: list[str] = []
    t0 = time.time()

    for i, epic in enumerate(epics, 1):
        logger.info(f"\n[{i}/{len(epics)}] Processing {epic}...")
        t_start = time.time()

        try:
            wf_result = run_walk_forward_backtest(
                epic=epic,
                timeframe=args.timeframe,
                initial_capital=args.capital,
                risk_per_trade=args.risk,
                tune=args.tune,
                tune_trials=args.tune_trials,
                do_sweep_threshold=True,
                monte_carlo=do_mc,
            )

            if wf_result is not None:
                results.append(wf_result)
                elapsed = time.time() - t_start
                logger.info(
                    f"[{i}/{len(epics)}] {epic} done in {elapsed:.0f}s "
                    f"(Sharpe={wf_result.sharpe:.2f}, trades={wf_result.total_trades})"
                )
            else:
                failed.append(epic)
                logger.warning(f"[{i}/{len(epics)}] {epic} returned no result")

        except Exception as e:
            failed.append(epic)
            logger.error(f"[{i}/{len(epics)}] {epic} FAILED: {e}")
            import traceback
            traceback.print_exc()

    total_time = time.time() - t0
    logger.info(f"\nBatch complete: {len(results)}/{len(epics)} assets in {total_time:.0f}s")

    if failed:
        logger.warning(f"Failed assets: {', '.join(failed)}")

    if not results:
        logger.error("No results to process. Exiting.")
        return

    # Build scorecards
    scorecards = build_scorecards(results)

    # Print scorecard table
    print(f"\n{'='*100}")
    print("WALK-FORWARD OOS SCORECARD")
    print(f"{'='*100}")
    print(format_scorecard_table(scorecards))
    print()

    # Summary
    n_keep = sum(1 for s in scorecards if s.decision == "KEEP")
    n_review = sum(1 for s in scorecards if s.decision == "REVIEW")
    n_exclude = sum(1 for s in scorecards if s.decision == "EXCLUDE")
    print(f"Decisions: {n_keep} KEEP, {n_review} REVIEW, {n_exclude} EXCLUDE")
    print()

    # Save optimal thresholds
    save_optimal_thresholds(scorecards, output_path)
    logger.info(f"Saved optimal thresholds to {output_path}")


if __name__ == "__main__":
    main()
