"""Phase 5 — RL adaptive layer ensemble evaluation.

Per `docs/evolutive/MANTIS_EVOLUTION_ROADMAP.md` §Phase 5:

  > Gymnasium Environment + Sharpe-based reward + PPO 500K steps with
  > walk-forward validation. Ensemble: XGBoost direction + RL timing/sizing.
  > Gate: ensemble beats XGBoost-only on OOS, Sharpe +15 %, max DD doesn't
  > increase.

This is a proof-of-concept first pass:
- Top-2 epics (BTC, SOL) — top performers from Phase 3.
- 50 000 PPO steps (not 500 000) per epic for runtime.
- Single-fold split: PPO trained on first 70 % of OOS-eligible data,
  evaluated on the remaining 30 %.
- Ensemble = post-hoc concordance filter:
    * XGB=BUY  AND PPO action=LONG_ENTRY → keep BUY
    * XGB=SELL AND PPO action=SHORT_ENTRY → keep SELL
    * otherwise → HOLD (block).

If the proof-of-concept clears the gate, expand to top-5 + 500k steps in
a follow-up Phase 5-bis.

Outputs:
- `data/config/phase5_rl_ensemble_eval.json`
- `data/models/{epic}/rl/ppo_phase5.zip` per trained epic.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/phase5_rl_ensemble_eval.py
    .venv/Scripts/python.exe scripts/phase5_rl_ensemble_eval.py \
        --steps 100000 --epics BTCUSD SOLUSD ETHUSD
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
from src.rl.environment import MantisRLEnvironment
from src.rl.schemas import RLAction, RLConfig

DEFAULT_TOP2 = ("BTCUSD", "SOLUSD")
WINDOWS_4H = {
    "train_window": 1512, "val_window": 378, "test_window": 126,
    "step_size": 126, "purge_gap": 30, "embargo": 12,
}
DEFAULT_CONFIDENCE = 0.40


@dataclass
class EnsembleResult:
    epic: str
    n_oos_bars: int
    n_xgb_signals: int
    n_kept: int
    sharpe_xgb: float
    sharpe_ens: float
    max_dd_xgb: float
    max_dd_ens: float
    return_xgb: float
    return_ens: float
    n_trades_xgb: int
    n_trades_ens: int
    sharpe_uplift_pct: float
    dd_increase_pct: float


def collect_oos_signals(
    epic: str, timeframe: str, prune_pct: float,
) -> tuple[list, list[int], list[float], list[float], pl.DataFrame, pl.DataFrame, list[str]]:
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

    timestamps = df_valid["timestamp"].to_list()
    atr_col = "atr_14" if "atr_14" in df_valid.columns else None
    atr_values = df_valid[atr_col].to_list() if atr_col else [0.0] * len(X)

    oos_t: list = []
    oos_s: list[int] = []
    oos_c: list[float] = []
    oos_a: list[float] = []
    oos_idx: list[int] = []  # index into df_valid for feature lookup

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
            oos_idx.append(idx)

    return oos_t, oos_s, oos_c, oos_a, df_valid, df_valid.select(["timestamp", "open", "high", "low", "close"]), feature_cols


def train_ppo(
    df_valid: pl.DataFrame, feature_cols: list[str],
    train_idx_end: int,
    total_timesteps: int,
    save_path: Path,
):
    """Train PPO on the first train_idx_end bars of df_valid."""
    from stable_baselines3 import PPO
    from src.drl.agents.ppo_agent import PPOAgent
    from src.drl.schemas import DRLConfig

    feats = df_valid.select(feature_cols).to_numpy().astype(np.float32)
    feats = np.nan_to_num(feats, nan=0.0)
    prices = df_valid["close"].to_numpy().astype(np.float64)

    train_feats = feats[:train_idx_end]
    train_prices = prices[:train_idx_end]

    rl_config = RLConfig(total_timesteps=total_timesteps)
    env = MantisRLEnvironment(train_feats, train_prices, rl_config)

    drl_config = DRLConfig(total_timesteps=total_timesteps, policy="MlpPolicy")
    agent = PPOAgent(env=env, config=drl_config)
    logger.info(f"Training PPO for {total_timesteps} steps on {train_idx_end} bars...")
    t0 = time.time()
    result = agent.train(total_timesteps=total_timesteps)
    logger.info(f"PPO training {result.algorithm} converged={result.converged} in {time.time() - t0:.0f}s")

    save_path.parent.mkdir(parents=True, exist_ok=True)
    agent.save(save_path.with_suffix(""))
    return agent


def predict_actions_for_oos(
    agent, df_valid: pl.DataFrame, feature_cols: list[str], oos_idx: list[int],
) -> list[int]:
    """For each OOS bar index, ask PPO what action to take with flat-state observation."""
    feats = df_valid.select(feature_cols).to_numpy().astype(np.float32)
    feats = np.nan_to_num(feats, nan=0.0)
    n_features = feats.shape[1]
    actions = []
    for idx in oos_idx:
        obs = np.concatenate([
            feats[idx],
            np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),  # flat-state
        ])
        action, _info = agent.predict(obs, deterministic=True)
        actions.append(int(action))
    return actions


def ensemble_filter(
    xgb_signals: list[int], rl_actions: list[int],
) -> tuple[list[int], int]:
    """XGB ∩ PPO concordance."""
    out = list(xgb_signals)
    blocked = 0
    for i, (s, a) in enumerate(zip(xgb_signals, rl_actions)):
        if s == SignalClass.HOLD:
            continue
        if s == SignalClass.BUY and a == RLAction.LONG_ENTRY:
            continue
        if s == SignalClass.SELL and a == RLAction.SHORT_ENTRY:
            continue
        out[i] = SignalClass.HOLD
        blocked += 1
    return out, blocked


def run_engine(
    epic, timeframe, timestamps, signals, confidences, atrs,
    ohlc_df, initial_capital, risk_per_trade,
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
    epic: str, timeframe: str, prune_pct: float,
    ppo_steps: int, train_pct: float,
    initial_capital: float, risk_per_trade: float,
) -> EnsembleResult | None:
    logger.info(f"\n{'='*60}\nPhase 5 RL ensemble: {epic}/{timeframe}\n{'='*60}")
    t0 = time.time()

    oos_t, oos_s, oos_c, oos_a, df_valid, ohlc_full, feature_cols = collect_oos_signals(
        epic, timeframe, prune_pct,
    )
    n_active = sum(1 for s in oos_s if s != SignalClass.HOLD)
    logger.info(f"[{epic}] OOS bars: {len(oos_t)}, active XGB signals: {n_active}")

    df_ts = df_valid["timestamp"].to_list()
    ts_to_idx = {ts: i for i, ts in enumerate(df_ts)}
    oos_idx = [ts_to_idx[ts] for ts in oos_t]
    train_idx_end = int(min(oos_idx) * train_pct)
    logger.info(f"[{epic}] Train PPO on bars [0:{train_idx_end}] ({train_idx_end} bars)")

    save_path = Path(f"data/models/{epic}/rl/ppo_phase5.zip")
    agent = train_ppo(df_valid, feature_cols, train_idx_end, ppo_steps, save_path)

    rl_actions = predict_actions_for_oos(agent, df_valid, feature_cols, oos_idx)
    logger.info(f"[{epic}] PPO action distribution OOS: " + ", ".join(
        f"{RLAction(a).name}={rl_actions.count(a)}" for a in range(5)
    ))

    ens_signals, n_blocked = ensemble_filter(oos_s, rl_actions)
    n_active_ens = sum(1 for s in ens_signals if s != SignalClass.HOLD)
    logger.info(f"[{epic}] Ensemble blocked {n_blocked} / kept {n_active_ens}")

    oos_start, oos_end = oos_t[0], oos_t[-1]
    storage = ParquetStorageManager()
    dal = DataAccessLayer(storage)
    ohlc_df = dal.get_candles(epic=epic, timeframe=timeframe, start_date=oos_start, end_date=oos_end)

    res_xgb = run_engine(epic, timeframe, oos_t, oos_s, oos_c, oos_a, ohlc_df, initial_capital, risk_per_trade)
    res_ens = run_engine(epic, timeframe, oos_t, ens_signals, oos_c, oos_a, ohlc_df, initial_capital, risk_per_trade)

    sh_xgb = res_xgb.metrics.get("sharpe_ratio", 0.0)
    sh_ens = res_ens.metrics.get("sharpe_ratio", 0.0)
    dd_xgb = abs(res_xgb.metrics.get("max_drawdown", 0.0))
    dd_ens = abs(res_ens.metrics.get("max_drawdown", 0.0))
    ret_xgb = res_xgb.metrics.get("total_return", 0.0) * 100
    ret_ens = res_ens.metrics.get("total_return", 0.0) * 100
    nt_xgb = res_xgb.metrics.get("total_trades", 0)
    nt_ens = res_ens.metrics.get("total_trades", 0)
    uplift = (sh_ens / sh_xgb - 1.0) * 100 if sh_xgb else 0.0
    dd_inc = (dd_ens / dd_xgb - 1.0) * 100 if dd_xgb else 0.0

    logger.info(
        f"[{epic}] Sharpe XGB {sh_xgb:.2f} -> Ens {sh_ens:.2f} ({uplift:+.1f}%) "
        f"DD {dd_xgb:.1%} -> {dd_ens:.1%} ({dd_inc:+.1f}%) "
        f"trades {nt_xgb}->{nt_ens} "
        f"{time.time() - t0:.0f}s"
    )
    return EnsembleResult(
        epic=epic,
        n_oos_bars=len(oos_t), n_xgb_signals=n_active, n_kept=n_active_ens,
        sharpe_xgb=sh_xgb, sharpe_ens=sh_ens,
        max_dd_xgb=dd_xgb, max_dd_ens=dd_ens,
        return_xgb=ret_xgb, return_ens=ret_ens,
        n_trades_xgb=nt_xgb, n_trades_ens=nt_ens,
        sharpe_uplift_pct=uplift, dd_increase_pct=dd_inc,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 — RL ensemble eval (top-2)")
    parser.add_argument("--epics", nargs="+", default=list(DEFAULT_TOP2))
    parser.add_argument("--timeframe", type=str, default="4h")
    parser.add_argument("--steps", type=int, default=50_000, help="PPO total_timesteps")
    parser.add_argument("--train-pct", type=float, default=0.7,
                        help="Fraction of pre-OOS bars used for PPO training")
    parser.add_argument("--prune-pct", type=float, default=0.5)
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--risk", type=float, default=0.02)
    parser.add_argument("--output", type=str,
                        default="data/config/phase5_rl_ensemble_eval.json")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[EnsembleResult] = []
    for epic in args.epics:
        try:
            r = evaluate_epic(
                epic, args.timeframe, prune_pct=args.prune_pct,
                ppo_steps=args.steps, train_pct=args.train_pct,
                initial_capital=args.capital, risk_per_trade=args.risk,
            )
            if r is not None:
                results.append(r)
        except Exception as exc:
            logger.error(f"[{epic}] FAILED: {exc}")
            import traceback
            traceback.print_exc()

    if not results:
        logger.error("No results")
        sys.exit(1)

    print("\nPhase 5 — RL Ensemble Scorecard")
    print(f"{'Epic':<10} {'Sh-XGB':>7} {'Sh-Ens':>7} {'Uplift':>8} "
          f"{'DD-XGB':>7} {'DD-Ens':>7} {'DDinc':>7} {'Trd-XGB':>8} {'Trd-Ens':>8}")
    for r in results:
        print(
            f"{r.epic:<10} {r.sharpe_xgb:>7.2f} {r.sharpe_ens:>7.2f} {r.sharpe_uplift_pct:>+7.1f}% "
            f"{r.max_dd_xgb:>7.1%} {r.max_dd_ens:>7.1%} {r.dd_increase_pct:>+6.1f}% "
            f"{r.n_trades_xgb:>8d} {r.n_trades_ens:>8d}"
        )

    pass_uplift = all(r.sharpe_uplift_pct >= 15.0 for r in results)
    pass_dd = all(r.max_dd_ens <= r.max_dd_xgb * 1.0001 for r in results)
    overall_pass = pass_uplift and pass_dd

    print(f"\nGate criteria:")
    print(f"  Sharpe uplift >= 15 % per epic: {'PASS' if pass_uplift else 'FAIL'}")
    print(f"  DD does not increase per epic : {'PASS' if pass_dd else 'FAIL'}")
    print(f"\nPhase 5 verdict: {'PASS' if overall_pass else 'FAIL'}")

    payload = {
        "timeframe": args.timeframe,
        "ppo_steps": args.steps,
        "train_pct": args.train_pct,
        "prune_pct": args.prune_pct,
        "per_epic": [
            {
                "epic": r.epic,
                "n_oos_bars": r.n_oos_bars,
                "n_xgb_signals": r.n_xgb_signals,
                "n_kept": r.n_kept,
                "sharpe_xgb": round(r.sharpe_xgb, 3),
                "sharpe_ens": round(r.sharpe_ens, 3),
                "max_dd_xgb": round(r.max_dd_xgb, 4),
                "max_dd_ens": round(r.max_dd_ens, 4),
                "return_xgb_pct": round(r.return_xgb, 2),
                "return_ens_pct": round(r.return_ens, 2),
                "n_trades_xgb": r.n_trades_xgb,
                "n_trades_ens": r.n_trades_ens,
                "sharpe_uplift_pct": round(r.sharpe_uplift_pct, 2),
                "dd_increase_pct": round(r.dd_increase_pct, 2),
            }
            for r in results
        ],
        "verdict": "PASS" if overall_pass else "FAIL",
        "criteria": {
            "uplift_pass": pass_uplift,
            "dd_pass": pass_dd,
        },
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(f"Saved eval to {output_path}")


if __name__ == "__main__":
    main()
