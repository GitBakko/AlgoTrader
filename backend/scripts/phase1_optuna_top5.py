"""Phase 1 — Optuna hyperparameter tuning on the top-5 KEEP basket.

Per `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 1:

  > Hyperparameter tuning on top 5 assets only (Optuna, 100+ trials per asset)

Uses the existing walk-forward harness (`scripts/walk_forward_backtest.py`)
with `tune=True`, then re-runs the scorecard logic on the tuned results
so the gate criteria (Sharpe > 0.3, WR > 40 %, MaxDD < 30 %) are applied
verbatim against the new models.

Outputs:
- `data/config/optimal_thresholds_phase1.json` — per-asset tuned thresholds
- `logs/phase1_optuna_top5.log` — full run log

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/phase1_optuna_top5.py
    .venv/Scripts/python.exe scripts/phase1_optuna_top5.py --tune-trials 200
"""

from __future__ import annotations

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

# Top-5 KEEP basket from Phase 0 (2026-04-28). Mean Sharpe 4.21 baseline,
# Phase 1 gate target +20 % → 5.05.
TOP5: tuple[str, ...] = (
    "SOLUSD",
    "BTCUSD",
    "ETHUSD",
    "XAUUSD",
    "BNBUSD",
)

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent / "data" / "config" / "optimal_thresholds_phase1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 — Optuna top-5 tuning")
    parser.add_argument("--timeframe", type=str, default="4h")
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--risk", type=float, default=0.02)
    parser.add_argument("--tune-trials", type=int, default=100)
    parser.add_argument(
        "--prune-pct",
        type=float,
        default=0.0,
        help="Drop bottom N%% features by Fold-0 XGBoost importance (Phase 1-C).",
    )
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"Phase 1 Optuna tuning: {len(TOP5)} assets, "
        f"timeframe={args.timeframe}, trials={args.tune_trials}"
    )
    logger.info(f"Output: {output_path}")

    results: list[WalkForwardResult] = []
    failed: list[str] = []
    t0 = time.time()

    for i, epic in enumerate(TOP5, 1):
        logger.info(f"\n[{i}/{len(TOP5)}] Tuning {epic}...")
        t_start = time.time()
        try:
            wf_result = run_walk_forward_backtest(
                epic=epic,
                timeframe=args.timeframe,
                initial_capital=args.capital,
                risk_per_trade=args.risk,
                tune=True,
                tune_trials=args.tune_trials,
                prune_pct=args.prune_pct,
                do_sweep_threshold=True,
                monte_carlo=False,
            )
            if wf_result is not None:
                results.append(wf_result)
                logger.info(
                    f"  {epic} done in {time.time() - t_start:.0f}s — "
                    f"Sharpe {wf_result.sharpe:.2f} WR {wf_result.win_rate:.1%}"
                )
            else:
                failed.append(epic)
                logger.warning(f"  {epic} returned None")
        except Exception as exc:
            failed.append(epic)
            logger.error(f"  {epic} FAILED: {exc}")

    elapsed = time.time() - t0
    logger.info(f"\nPhase 1 sweep complete in {elapsed:.0f}s")

    if not results:
        logger.error("No successful results — aborting before scorecard.")
        sys.exit(1)

    scorecards = build_scorecards(results)
    print(format_scorecard_table(scorecards))

    save_optimal_thresholds(scorecards, output_path)
    logger.info(f"Saved tuned thresholds to {output_path}")

    if failed:
        logger.warning(f"Failed: {', '.join(failed)}")

    # Phase 1 gate check vs Phase 0 baseline.
    phase0_sharpe_top5 = 4.21
    phase1_mean = sum(r.sharpe for r in results) / max(1, len(results))
    delta_pct = (phase1_mean / phase0_sharpe_top5 - 1.0) * 100
    target = phase0_sharpe_top5 * 1.20
    logger.info(
        f"\nPhase 1 gate vs Phase 0 baseline:\n"
        f"  Phase 0 top-5 mean Sharpe: {phase0_sharpe_top5:.2f}\n"
        f"  Phase 1 top-5 mean Sharpe: {phase1_mean:.2f} ({delta_pct:+.1f}% delta)\n"
        f"  Phase 1 gate target:       {target:.2f} (+20 %)\n"
        f"  Result: {'PASS' if phase1_mean >= target else 'FAIL'}"
    )


if __name__ == "__main__":
    main()
