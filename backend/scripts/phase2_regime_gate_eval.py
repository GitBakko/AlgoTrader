"""Phase 2 — Regime Gate evaluation on the top-5 KEEP basket.

Per `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 2:

  > HMM Regime Detector (4-state) + Drift Monitor (PSI) -> Regime-Gated Signal
  > Generator. Confidence threshold 0.65 (below = NO_TRADE), PSI > 0.20 = block.

This script does post-hoc evaluation: re-runs the Phase 1 walk-forward on the
top-5 KEEP basket, then for every non-HOLD OOS signal queries the trained HMM
regime detector to decide pass/block. Compares ungated vs gated metrics and
applies the Phase 2 gate criteria.

Prerequisites:
- `data/models/{epic}/regime/hmm_detector.pkl` for each top-5 epic
  (run `scripts/train_regime_detector.py --epic <e> --timeframe 4h` first)

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/phase2_regime_gate_eval.py
    .venv/Scripts/python.exe scripts/phase2_regime_gate_eval.py --gate-window 200
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import polars as pl
from loguru import logger

from src.backtest.engine import BacktestEngine
from src.backtest.schemas import BacktestConfig
from src.data.data_access import DataAccessLayer
from src.data.storage import ParquetStorageManager
from src.features.builder import FeatureBuilder
from src.models.calibration import ConfidenceCalibrator
from src.models.feature_selector import FeatureSelector
from src.models.schemas import SignalClass
from src.models.target_builder import TargetBuilder
from src.models.walk_forward import WalkForwardSplitter
from src.models.xgboost_model import XGBoostClassifier
from src.regime.hmm_detector import HMMRegimeDetector

TOP5: tuple[str, ...] = ("SOLUSD", "BTCUSD", "ETHUSD", "XAUUSD", "BNBUSD")
WINDOWS_4H = {
    "train_window": 1512, "val_window": 378, "test_window": 126,
    "step_size": 126, "purge_gap": 30, "embargo": 12,
}
DEFAULT_CONFIDENCE = 0.40


@dataclass
class GateEvalResult:
    epic: str
    n_signals_in: int
    n_signals_blocked: int
    block_rate: float
    sharpe_ungated: float
    sharpe_gated: float
    max_dd_ungated: float
    max_dd_gated: float
    return_ungated: float
    return_gated: float
    n_trades_ungated: int
    n_trades_gated: int
    blocked_trades_pnl: float  # net P&L of trades whose open-time was gate-blocked
    profitable_trades_blocked: int
    profitable_trades_total: int
    fp_block_rate: float       # profitable_trades_blocked / profitable_trades_total
    dd_reduction_pct: float    # (1 - gated/ungated) * 100


def collect_oos_signals(
    epic: str,
    timeframe: str,
    prune_pct: float,
) -> tuple[list, list[int], list[float], list[float], pl.DataFrame, pl.DataFrame]:
    """Re-run the Phase 1 walk-forward and return OOS signals + raw OHLC + df_valid."""
    storage = ParquetStorageManager()
    dal = DataAccessLayer(storage)
    builder = FeatureBuilder(dal)
    target_builder = TargetBuilder()

    df, feature_meta = builder.build_features(
        epic=epic, timeframe=timeframe,
        normalize=True, include_regime=True, multi_timeframe=True,
    )
    df = target_builder.build_targets(df)
    df_valid = df.filter(pl.col("target").is_not_null())

    zscore_features = [c for c in feature_meta.feature_names if c.endswith("_zscore")]
    raw_features = [
        c for c in feature_meta.feature_names
        if not c.endswith("_zscore") and c != "regime" and f"{c}_zscore" not in df.columns
    ]
    feature_cols = [c for c in zscore_features + raw_features if c in df_valid.columns]

    X = df_valid.select(feature_cols).to_numpy().astype(np.float64)
    y = df_valid["target"].to_numpy().astype(np.int32)
    X = np.nan_to_num(X, nan=0.0)

    splitter = WalkForwardSplitter(**WINDOWS_4H)
    timestamps = df_valid["timestamp"].to_list()
    atr_col = "atr_14" if "atr_14" in df_valid.columns else None
    atr_values = df_valid[atr_col].to_list() if atr_col else [0.0] * len(X)

    if prune_pct > 0:
        first_split = next(splitter.split(len(X)))
        m0 = XGBoostClassifier()
        m0.feature_names = feature_cols
        m0.fit(
            X[first_split.train_indices], y[first_split.train_indices],
            X[first_split.val_indices], y[first_split.val_indices],
        )
        importance = m0.get_feature_importance()
        selector = FeatureSelector(drop_pct=prune_pct)
        feature_cols = selector.fit(importance, feature_cols)
        X = selector.transform(X)
        del m0

    oos_t: list = []
    oos_s: list[int] = []
    oos_c: list[float] = []
    oos_a: list[float] = []

    for split in splitter.split(len(X)):
        m = XGBoostClassifier()
        m.fit(
            X[split.train_indices], y[split.train_indices],
            X[split.val_indices], y[split.val_indices],
        )
        cal = ConfidenceCalibrator(n_classes=3)
        cal.fit(y[split.val_indices], m.predict_proba(X[split.val_indices]))
        proba = m.predict_proba(X[split.test_indices])
        if cal.is_fitted:
            proba = cal.transform(proba)
        preds = np.argmax(proba, axis=1).astype(np.int32)
        confs = np.max(proba, axis=1)
        preds[confs < DEFAULT_CONFIDENCE] = SignalClass.HOLD

        for i, idx in enumerate(range(split.test_start, split.test_end)):
            oos_t.append(timestamps[idx])
            oos_s.append(int(preds[i]))
            oos_c.append(float(confs[i]))
            oos_a.append(float(atr_values[idx]))

    oos_start, oos_end = oos_t[0], oos_t[-1]
    ohlc_df = dal.get_candles(
        epic=epic, timeframe=timeframe, start_date=oos_start, end_date=oos_end,
    )
    return oos_t, oos_s, oos_c, oos_a, ohlc_df, df_valid


def apply_gate(
    df_valid: pl.DataFrame,
    oos_t: list,
    oos_s: list[int],
    hmm: HMMRegimeDetector,
    gate_window: int,
    confidence_threshold: float,
) -> tuple[list[int], list[bool]]:
    """Replay HMM gate per non-HOLD signal. Return (gated_signals, blocked_mask)."""
    df_ts = df_valid["timestamp"].to_list()
    ts_to_idx = {ts: i for i, ts in enumerate(df_ts)}

    gated = list(oos_s)
    blocked_mask = [False] * len(oos_s)

    ohlc_cols = ["open", "high", "low", "close"]
    if "volume" in df_valid.columns:
        ohlc_cols.append("volume")
    raw = df_valid.select(["timestamp", *ohlc_cols])

    for i, (ts, sig) in enumerate(zip(oos_t, oos_s)):
        if sig == SignalClass.HOLD:
            continue
        idx = ts_to_idx.get(ts)
        if idx is None or idx < gate_window:
            continue
        window_df = raw.slice(idx - gate_window, gate_window)
        try:
            state = hmm.predict(window_df)
        except Exception as exc:
            logger.debug(f"HMM predict failed at {ts}: {exc}")
            continue
        if state.confidence < confidence_threshold:
            gated[i] = SignalClass.HOLD
            blocked_mask[i] = True

    return gated, blocked_mask


def run_engine(
    epic: str, timeframe: str,
    timestamps: list, signals: list[int], confidences: list[float], atrs: list[float],
    ohlc_df: pl.DataFrame,
    initial_capital: float, risk_per_trade: float,
):
    sig_df = pl.DataFrame({
        "timestamp": timestamps,
        "signal": signals,
        "confidence": confidences,
        "atr": atrs,
    }).sort("timestamp")
    config = BacktestConfig(
        epic=epic, timeframe=timeframe,
        start_date=sig_df["timestamp"].min(), end_date=sig_df["timestamp"].max(),
        initial_capital=initial_capital, risk_per_trade=risk_per_trade,
    )
    return BacktestEngine(config).run(ohlc_df, sig_df)


def evaluate_epic(
    epic: str, timeframe: str, gate_window: int,
    confidence_threshold: float, prune_pct: float,
    initial_capital: float, risk_per_trade: float,
) -> GateEvalResult | None:
    logger.info(f"\n{'='*60}\nPhase 2 gate eval: {epic}/{timeframe}\n{'='*60}")
    hmm_path = Path(f"data/models/{epic}/regime/hmm_detector.pkl")
    if not hmm_path.exists():
        logger.warning(f"[{epic}] HMM detector missing at {hmm_path}, skipping")
        return None

    t0 = time.time()
    hmm = HMMRegimeDetector.load(hmm_path)
    hmm.confidence_threshold = confidence_threshold

    oos_t, oos_s, oos_c, oos_a, ohlc_df, df_valid = collect_oos_signals(
        epic, timeframe, prune_pct=prune_pct,
    )

    n_active_in = sum(1 for s in oos_s if s != SignalClass.HOLD)
    logger.info(f"[{epic}] OOS bars: {len(oos_t)}, active signals: {n_active_in}")

    gated, blocked = apply_gate(
        df_valid, oos_t, oos_s, hmm,
        gate_window=gate_window, confidence_threshold=confidence_threshold,
    )
    n_blocked = sum(blocked)
    n_active_out = sum(1 for s in gated if s != SignalClass.HOLD)
    logger.info(f"[{epic}] gate blocked {n_blocked} / kept {n_active_out}")

    res_un = run_engine(
        epic, timeframe, oos_t, oos_s, oos_c, oos_a, ohlc_df,
        initial_capital, risk_per_trade,
    )
    res_gd = run_engine(
        epic, timeframe, oos_t, gated, oos_c, oos_a, ohlc_df,
        initial_capital, risk_per_trade,
    )

    blocked_ts = {oos_t[i] for i, b in enumerate(blocked) if b}
    blocked_pnl = 0.0
    profitable_total = 0
    profitable_blocked = 0
    for tr in res_un.trades:
        if tr.status.value == "open":
            continue
        if tr.net_pnl > 0:
            profitable_total += 1
        if tr.entry_time in blocked_ts:
            blocked_pnl += tr.net_pnl
            if tr.net_pnl > 0:
                profitable_blocked += 1

    sh_un = res_un.metrics.get("sharpe_ratio", 0.0)
    sh_gd = res_gd.metrics.get("sharpe_ratio", 0.0)
    dd_un = abs(res_un.metrics.get("max_drawdown", 0.0))
    dd_gd = abs(res_gd.metrics.get("max_drawdown", 0.0))
    ret_un = res_un.metrics.get("total_return", 0.0) * 100
    ret_gd = res_gd.metrics.get("total_return", 0.0) * 100
    nt_un = res_un.metrics.get("total_trades", 0)
    nt_gd = res_gd.metrics.get("total_trades", 0)
    dd_red = (1.0 - dd_gd / dd_un) * 100 if dd_un > 0 else 0.0
    fp_rate = (profitable_blocked / profitable_total) if profitable_total > 0 else 0.0
    block_rate = (n_blocked / n_active_in) if n_active_in > 0 else 0.0

    logger.info(
        f"[{epic}] Sharpe {sh_un:.2f}->{sh_gd:.2f} · "
        f"DD {dd_un:.1%}->{dd_gd:.1%} ({dd_red:+.1f}%) · "
        f"trades {nt_un}->{nt_gd} · "
        f"blockedPnL {blocked_pnl:+.2f} · "
        f"FP-block {profitable_blocked}/{profitable_total} ({fp_rate:.1%}) · "
        f"{time.time() - t0:.0f}s"
    )

    return GateEvalResult(
        epic=epic,
        n_signals_in=n_active_in,
        n_signals_blocked=n_blocked,
        block_rate=block_rate,
        sharpe_ungated=sh_un, sharpe_gated=sh_gd,
        max_dd_ungated=dd_un, max_dd_gated=dd_gd,
        return_ungated=ret_un, return_gated=ret_gd,
        n_trades_ungated=nt_un, n_trades_gated=nt_gd,
        blocked_trades_pnl=blocked_pnl,
        profitable_trades_blocked=profitable_blocked,
        profitable_trades_total=profitable_total,
        fp_block_rate=fp_rate,
        dd_reduction_pct=dd_red,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 — Regime gate eval (top-5)")
    parser.add_argument("--timeframe", type=str, default="4h")
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--risk", type=float, default=0.02)
    parser.add_argument("--prune-pct", type=float, default=0.5)
    parser.add_argument("--gate-window", type=int, default=200)
    parser.add_argument("--confidence", type=float, default=0.65)
    parser.add_argument("--output", type=str,
                        default="data/config/phase2_regime_gate_eval.json")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[GateEvalResult] = []
    for epic in TOP5:
        try:
            r = evaluate_epic(
                epic, args.timeframe,
                gate_window=args.gate_window,
                confidence_threshold=args.confidence,
                prune_pct=args.prune_pct,
                initial_capital=args.capital, risk_per_trade=args.risk,
            )
            if r is not None:
                results.append(r)
        except Exception as exc:
            logger.error(f"[{epic}] FAILED: {exc}")
            import traceback
            traceback.print_exc()

    if not results:
        logger.error("No results — aborting before report")
        sys.exit(1)

    # Aggregates
    mean_dd_red = float(np.mean([r.dd_reduction_pct for r in results]))
    sum_blocked_pnl = float(np.sum([r.blocked_trades_pnl for r in results]))
    sum_profitable_blocked = int(sum(r.profitable_trades_blocked for r in results))
    sum_profitable_total = int(sum(r.profitable_trades_total for r in results))
    fp_rate_overall = (
        sum_profitable_blocked / sum_profitable_total
        if sum_profitable_total > 0 else 0.0
    )

    # Phase 2 gate criteria
    pass_dd = mean_dd_red > 20.0
    pass_blocked_pnl = sum_blocked_pnl < 0.0
    pass_fp = fp_rate_overall < 0.30

    overall_pass = pass_dd and pass_blocked_pnl and pass_fp

    # Print scorecard
    print("\nPhase 2 — Regime Gate Scorecard")
    print(f"{'Epic':<10} {'Sh-un':>7} {'Sh-gt':>7} {'DD-un':>7} {'DD-gt':>7} "
          f"{'DDred':>7} {'Trd-un':>7} {'Trd-gt':>7} {'BlkPnL':>10} {'FPblk':>7}")
    for r in results:
        print(
            f"{r.epic:<10} {r.sharpe_ungated:>7.2f} {r.sharpe_gated:>7.2f} "
            f"{r.max_dd_ungated:>7.1%} {r.max_dd_gated:>7.1%} "
            f"{r.dd_reduction_pct:>6.1f}% {r.n_trades_ungated:>7d} {r.n_trades_gated:>7d} "
            f"{r.blocked_trades_pnl:>10.2f} {r.fp_block_rate:>7.1%}"
        )

    print(f"\nGate criteria:")
    print(f"  DD reduction > 20 %     : mean {mean_dd_red:+.1f}% -> {'PASS' if pass_dd else 'FAIL'}")
    print(f"  Blocked trades net < 0  : ${sum_blocked_pnl:+.2f} -> {'PASS' if pass_blocked_pnl else 'FAIL'}")
    print(f"  FP block rate < 30 %    : {fp_rate_overall:.1%} -> {'PASS' if pass_fp else 'FAIL'}")
    print(f"\nPhase 2 gate verdict: {'PASS' if overall_pass else 'FAIL'}")

    # Persist
    payload = {
        "timeframe": args.timeframe,
        "gate_window": args.gate_window,
        "confidence_threshold": args.confidence,
        "prune_pct": args.prune_pct,
        "per_epic": [
            {
                "epic": r.epic,
                "n_signals_in": r.n_signals_in,
                "n_signals_blocked": r.n_signals_blocked,
                "block_rate": round(r.block_rate, 4),
                "sharpe_ungated": round(r.sharpe_ungated, 3),
                "sharpe_gated": round(r.sharpe_gated, 3),
                "max_dd_ungated": round(r.max_dd_ungated, 4),
                "max_dd_gated": round(r.max_dd_gated, 4),
                "return_ungated_pct": round(r.return_ungated, 2),
                "return_gated_pct": round(r.return_gated, 2),
                "n_trades_ungated": r.n_trades_ungated,
                "n_trades_gated": r.n_trades_gated,
                "blocked_trades_pnl": round(r.blocked_trades_pnl, 2),
                "profitable_trades_blocked": r.profitable_trades_blocked,
                "profitable_trades_total": r.profitable_trades_total,
                "fp_block_rate": round(r.fp_block_rate, 4),
                "dd_reduction_pct": round(r.dd_reduction_pct, 2),
            }
            for r in results
        ],
        "aggregate": {
            "mean_dd_reduction_pct": round(mean_dd_red, 2),
            "sum_blocked_trades_pnl": round(sum_blocked_pnl, 2),
            "fp_block_rate_overall": round(fp_rate_overall, 4),
            "phase2_gate_verdict": "PASS" if overall_pass else "FAIL",
            "criteria": {
                "dd_reduction_pass": pass_dd,
                "blocked_pnl_pass": pass_blocked_pnl,
                "fp_block_pass": pass_fp,
            },
        },
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(f"Saved eval result to {output_path}")


if __name__ == "__main__":
    main()
