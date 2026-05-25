"""Phase 1 expansion — Optuna hyperparameter tuning on the full 19-asset basket.

Promoted from `phase1_optuna_top5.py` (2026-04-28) after the 2026-05-23 spread
audit + Phase 0 ri-validation expanded the tradable universe 5 → 19 assets.

Phase 0 ri-val report `2026-05-23_phase0_revalidate_excluded.md` returned
14 KEEP / 1 REVIEW (AMZN) / 0 EXCLUDE on the 15 originally-excluded epics
once `ASSET_SPREADS` was recalibrated from the 74h passive audit
(commits `15aba8d` + `7c3d074`).

This script tunes Optuna on the 19 assets (excluding AMZN — separate
deep-dive in `walk_forward_backtest.py --epic AMZN`).

Per-asset compute ≈ 70–90s with `--tune-trials 100`, so the full run is
roughly 25 min on the dev box.

Outputs:
- `data/config/optimal_thresholds_phase1_expanded_2026-05-23.json` —
  per-asset tuned thresholds.
- `logs/phase1_optuna_full_basket.log` — full run log (handled by loguru
  default sink + the caller's `--log-file` redirect if any).

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/phase1_optuna_full_basket.py
    .venv/Scripts/python.exe scripts/phase1_optuna_full_basket.py --tune-trials 100
    .venv/Scripts/python.exe scripts/phase1_optuna_full_basket.py --only USDCHF,USDCAD,USDJPY

Gate (post-recalib baseline, Phase 3 re-run mean Sharpe 3.95):
- Per-asset KEEP: Sharpe ≥ 0.3, WR ≥ 40 %, MaxDD < 30 % (same as Phase 0).
- Aggregate target: median Sharpe ≥ 1.0 over the 19-asset basket, since
  the +20 % vs top-5 target (≥ 4.74) is unrealistic on a basket that
  includes low-Sharpe stocks (NVDA 0.60, META 0.52) by design — the
  expansion thesis is *diversification*, not aggregate Sharpe lift.
- Report-only: top-5 sub-basket Sharpe should not regress vs Phase 3
  re-run (mean 3.95).
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

# 19-asset expanded basket from Phase 0 ri-val (2026-05-23). AMZN excluded
# pending its own Optuna deep-dive (Sharpe 0.12 / PF 1.06 in the
# no-tune sweep — needs to clear KEEP gate with tuning before it
# joins the basket).
EXPANDED_BASKET: tuple[str, ...] = (
    # Core top-5 (kept from original Phase 1; mean Sharpe 3.95 post-recalib)
    "SOLUSD",
    "BTCUSD",
    "ETHUSD",
    "XAUUSD",
    "BNBUSD",
    # Forex (newly viable post-recalib — top 3 of the ri-val ranking)
    "USDCHF",
    "USDCAD",
    "USDJPY",
    # Commodities (PLATINUM + COPPER promoted by ri-val; WTIUSD already KEEP)
    "WTIUSD",
    "PLATINUM",
    "COPPER",
    # Indices (DE40 promoted by ri-val; US500 always KEEP)
    "US500",
    "DE40",
    # US Stocks (7 promoted by ri-val; AMZN separate)
    "MSFT",
    "GOOGL",
    "AAPL",
    "TSLA",
    "AMD",
    "META",
    "NVDA",
)

# Baseline reference for gate reporting. Phase 3 re-run mean of the top-5
# basket on the recalibrated cost model.
PHASE3_RERUN_TOP5_MEAN_SHARPE = 3.95
TOP5_SUBSET: frozenset[str] = frozenset(
    ("SOLUSD", "BTCUSD", "ETHUSD", "XAUUSD", "BNBUSD")
)

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "config"
    / "optimal_thresholds_phase1_expanded_2026-05-23.json"
)


def _parse_only(arg: str | None) -> tuple[str, ...] | None:
    if not arg:
        return None
    tokens = [t.strip().upper() for t in arg.split(",") if t.strip()]
    unknown = [t for t in tokens if t not in EXPANDED_BASKET]
    if unknown:
        raise SystemExit(
            f"--only contains unknown epics: {', '.join(unknown)}. "
            f"Allowed: {', '.join(EXPANDED_BASKET)}"
        )
    return tuple(tokens)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1 expansion — Optuna 19-asset tuning"
    )
    parser.add_argument("--timeframe", type=str, default="4h")
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--risk", type=float, default=0.02)
    parser.add_argument("--tune-trials", type=int, default=100)
    parser.add_argument(
        "--prune-pct",
        type=float,
        default=0.25,
        help=(
            "Drop bottom N%% features by Fold-0 XGBoost importance (Phase 1-C). "
            "Default 0.25 matches the Phase 3 re-run."
        ),
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help=(
            "Comma-separated subset of EXPANDED_BASKET to tune "
            "(useful for quick re-runs of failed epics)."
        ),
    )
    parser.add_argument(
        "--monte-carlo",
        action="store_true",
        help="Run Monte-Carlo bootstrap on top of walk-forward (slower).",
    )
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    basket = _parse_only(args.only) or EXPANDED_BASKET
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"Phase 1 expansion Optuna tuning: {len(basket)} assets "
        f"(of {len(EXPANDED_BASKET)} basket), "
        f"timeframe={args.timeframe}, trials={args.tune_trials}, "
        f"prune_pct={args.prune_pct}"
    )
    logger.info(f"Output: {output_path}")

    results: list[WalkForwardResult] = []
    failed: list[str] = []
    t0 = time.time()

    for i, epic in enumerate(basket, 1):
        logger.info(f"\n[{i}/{len(basket)}] Tuning {epic}...")
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
                monte_carlo=args.monte_carlo,
            )
            if wf_result is not None:
                results.append(wf_result)
                logger.info(
                    f"  {epic} done in {time.time() - t_start:.0f}s — "
                    f"Sharpe {wf_result.sharpe:.2f} "
                    f"WR {wf_result.win_rate:.1%} "
                    f"DD {wf_result.max_drawdown:.1%}"
                )
            else:
                failed.append(epic)
                logger.warning(f"  {epic} returned None")
        except Exception as exc:
            failed.append(epic)
            logger.error(f"  {epic} FAILED: {exc}")

    elapsed = time.time() - t0
    logger.info(
        f"\nPhase 1 expansion sweep complete in {elapsed:.0f}s "
        f"({elapsed / 60:.1f} min)"
    )

    if not results:
        logger.error("No successful results — aborting before scorecard.")
        sys.exit(1)

    scorecards = build_scorecards(results)
    print(format_scorecard_table(scorecards))

    save_optimal_thresholds(scorecards, output_path)
    logger.info(f"Saved tuned thresholds to {output_path}")

    if failed:
        logger.warning(f"Failed: {', '.join(failed)}")

    # -------- Gate evaluation --------
    sharpes = [r.sharpe for r in results]
    sharpes_sorted = sorted(sharpes)
    median_sharpe = sharpes_sorted[len(sharpes_sorted) // 2]
    mean_sharpe = sum(sharpes) / len(sharpes)

    keep_per_asset = [
        r
        for r in results
        if r.sharpe >= 0.3 and r.win_rate >= 0.40 and r.max_drawdown <= 0.30
    ]
    keep_count = len(keep_per_asset)

    top5_results = [r for r in results if r.epic in TOP5_SUBSET]
    top5_mean = (
        sum(r.sharpe for r in top5_results) / len(top5_results)
        if top5_results
        else float("nan")
    )

    aggregate_target = 1.0  # median Sharpe ≥ 1.0 on 19-asset basket
    aggregate_pass = median_sharpe >= aggregate_target

    top5_regression_pct = (
        (top5_mean / PHASE3_RERUN_TOP5_MEAN_SHARPE - 1.0) * 100
        if top5_results
        else float("nan")
    )

    logger.info(
        "\nPhase 1 expansion gate:\n"
        f"  Assets evaluated:      {len(results)} / {len(basket)}\n"
        f"  Per-asset KEEP gate:   {keep_count} / {len(results)} pass "
        f"(Sharpe>=0.3 & WR>=40% & DD<=30%)\n"
        f"  Median Sharpe:         {median_sharpe:.2f} "
        f"(target >= {aggregate_target:.2f})\n"
        f"  Mean Sharpe:           {mean_sharpe:.2f}\n"
        f"  Top-5 mean Sharpe:     {top5_mean:.2f} "
        f"(vs Phase 3 re-run {PHASE3_RERUN_TOP5_MEAN_SHARPE:.2f}, "
        f"delta {top5_regression_pct:+.1f}%)\n"
        f"  Aggregate verdict:     "
        f"{'PASS' if aggregate_pass else 'FAIL'}"
    )


if __name__ == "__main__":
    main()
