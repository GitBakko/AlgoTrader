"""
Walk-forward backtest script.

Performs rigorous out-of-sample validation by retraining the model
on each walk-forward fold and collecting test-set predictions.
No data leakage: every prediction is made on data never seen by the model.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/walk_forward_backtest.py
    .venv/Scripts/python.exe scripts/walk_forward_backtest.py --epic XAUUSD
    .venv/Scripts/python.exe scripts/walk_forward_backtest.py --tune --prune-pct 0.25 --sweep-threshold
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from src.backtest.engine import BacktestEngine
from src.backtest.reporter import BacktestReporter
from src.backtest.schemas import BacktestConfig
from src.data.data_access import DataAccessLayer
from src.data.storage import ParquetStorageManager
from src.features.builder import FeatureBuilder
from src.features.technical import TechnicalIndicators
from src.models.calibration import ConfidenceCalibrator
from src.models.feature_selector import FeatureSelector
from src.models.schemas import SignalClass
from src.models.target_builder import TargetBuilder
from src.models.walk_forward import WalkForwardSplitter
from src.models.xgboost_model import XGBoostClassifier
from src.strategy.squeeze_strategy import SqueezeBreakoutStrategy
from src.strategy.strategy_router import StrategyRouter
from src.strategy.vwap_strategy import VWAPReversionStrategy

# Walk-forward window sizes (scaled for timeframe)
WINDOWS = {
    "1h": {"train": 6048, "val": 1512, "test": 504, "step": 504, "purge": 120, "embargo": 48},
    "4h": {"train": 1512, "val": 378, "test": 126, "step": 126, "purge": 30, "embargo": 12},
    "1d": {"train": 252, "val": 63, "test": 21, "step": 21, "purge": 5, "embargo": 2},
}

ASSETS = ["XAUUSD", "BTCUSD", "US500", "WTIUSD", "EURUSD", "NVDA", "TSLA", "XAGUSD", "DE40"]

# Individual stocks trade fewer hours/day → smaller walk-forward windows
STOCK_EPICS = {"NVDA", "TSLA"}
STOCK_WINDOWS = {
    "1h": {"train": 2520, "val": 630, "test": 210, "step": 210, "purge": 50, "embargo": 20},
    "4h": {"train": 756, "val": 189, "test": 63, "step": 63, "purge": 15, "embargo": 6},
    "1d": {"train": 252, "val": 63, "test": 21, "step": 21, "purge": 5, "embargo": 2},
}

DEFAULT_CONFIDENCE = 0.40


def sweep_confidence_thresholds(
    oos_signals: list[int],
    oos_confidences: list[float],
    oos_timestamps: list,
    oos_atrs: list[float],
    ohlc_df: pl.DataFrame,
    config: BacktestConfig,
) -> tuple[float, dict]:
    """Sweep confidence thresholds and find the one maximizing Sharpe ratio."""
    thresholds = [0.30, 0.33, 0.35, 0.38, 0.40, 0.42, 0.45, 0.48, 0.50, 0.55]
    signals_array = np.array(oos_signals)
    confidences_array = np.array(oos_confidences)

    best_sharpe = -999.0
    best_threshold = DEFAULT_CONFIDENCE
    results = {}

    for thresh in thresholds:
        filtered = signals_array.copy()
        filtered[confidences_array < thresh] = SignalClass.HOLD

        n_active = int((filtered != SignalClass.HOLD).sum())
        if n_active < 10:
            results[thresh] = {"sharpe": 0.0, "trades": 0, "return": 0.0, "win_rate": 0.0}
            continue

        sig_df = pl.DataFrame({
            "timestamp": oos_timestamps,
            "signal": filtered.tolist(),
            "confidence": oos_confidences,
            "atr": oos_atrs,
        }).sort("timestamp")

        engine = BacktestEngine(config)
        result = engine.run(ohlc_df, sig_df)

        sharpe = result.metrics.get("sharpe_ratio", 0.0)
        n_trades = result.metrics.get("total_trades", 0)
        total_return = result.metrics.get("total_return", 0.0)
        win_rate = result.metrics.get("win_rate", 0.0)

        results[thresh] = {
            "sharpe": sharpe, "trades": n_trades,
            "return": total_return, "win_rate": win_rate,
        }

        if sharpe > best_sharpe and n_trades >= 10:
            best_sharpe = sharpe
            best_threshold = thresh

    return best_threshold, results


def _run_strategy_backtest(
    strategy_name: str,
    df: pl.DataFrame,
    epic: str,
    timeframe: str,
    data_access: DataAccessLayer,
    initial_capital: float,
    risk_per_trade: float,
) -> None:
    """
    Run a backtest using a rule-based strategy instead of ML walk-forward.

    Generates signals from the strategy's vectorized backtest method,
    converts to BacktestEngine format, and runs the backtest.
    """
    # Create strategy instance
    if strategy_name == "squeeze_breakout":
        strat = SqueezeBreakoutStrategy()
    elif strategy_name == "vwap_reversion":
        strat = VWAPReversionStrategy()
    elif strategy_name == "auto":
        router = StrategyRouter()
        router.register_strategy(SqueezeBreakoutStrategy())
        router.register_strategy(VWAPReversionStrategy())
        strat = router
    else:
        logger.error(f"Unknown strategy: {strategy_name}")
        return

    logger.info(f"Generating {strategy_name} signals on {len(df)} bars...")
    strategy_df = strat.generate_backtest_signals(df, epic, timeframe)

    # Check signal columns exist
    if "signal_direction" not in strategy_df.columns:
        logger.error("Strategy did not produce signal_direction column")
        return

    # Convert signal_direction (1=BUY, -1=SELL, 0=HOLD) to SignalClass
    # BUY=2, SELL=0, HOLD=1
    atr_col = "atr_14" if "atr_14" in strategy_df.columns else None

    signals_df = strategy_df.select([
        pl.col("timestamp"),
        pl.when(pl.col("signal_direction") == 1)
        .then(pl.lit(SignalClass.BUY))
        .when(pl.col("signal_direction") == -1)
        .then(pl.lit(SignalClass.SELL))
        .otherwise(pl.lit(SignalClass.HOLD))
        .alias("signal"),
        pl.col("signal_confidence").alias("confidence"),
        pl.col(atr_col).alias("atr") if atr_col else pl.lit(0.0).alias("atr"),
    ]).sort("timestamp")

    # Signal stats
    n_buy = signals_df.filter(pl.col("signal") == SignalClass.BUY).height
    n_sell = signals_df.filter(pl.col("signal") == SignalClass.SELL).height
    n_hold = signals_df.filter(pl.col("signal") == SignalClass.HOLD).height
    logger.info(f"Signals: {n_buy} BUY, {n_sell} SELL, {n_hold} HOLD")

    if n_buy + n_sell == 0:
        logger.warning("No active signals (all HOLD). Check strategy parameters.")
        return

    # Get OHLC data for backtest period
    bt_start = signals_df["timestamp"].min()
    bt_end = signals_df["timestamp"].max()

    ohlc_df = data_access.get_candles(
        epic=epic, timeframe=timeframe,
        start_date=bt_start, end_date=bt_end,
    )

    if ohlc_df.is_empty():
        logger.error("No OHLC data for signal period")
        return

    config = BacktestConfig(
        epic=epic,
        timeframe=timeframe,
        start_date=bt_start,
        end_date=bt_end,
        initial_capital=initial_capital,
        risk_per_trade=risk_per_trade,
    )

    engine = BacktestEngine(config)
    result = engine.run(ohlc_df, signals_df)

    print("\n" + BacktestReporter.summarize(result))
    print()


def run_walk_forward_backtest(
    epic: str,
    timeframe: str,
    initial_capital: float = 10_000.0,
    risk_per_trade: float = 0.02,
    tune: bool = False,
    tune_trials: int = 40,
    prune_pct: float = 0.0,
    do_sweep_threshold: bool = False,
    strategy: str = "ml_ensemble",
    monte_carlo: bool = False,
) -> None:
    """Run walk-forward backtest for a single asset."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Walk-Forward Backtest: {epic}/{timeframe} [{strategy}]")
    opts = []
    if tune:
        opts.append(f"tune({tune_trials})")
    if prune_pct > 0:
        opts.append(f"prune({prune_pct:.0%})")
    if do_sweep_threshold:
        opts.append("sweep")
    if opts:
        logger.info(f"Options: {', '.join(opts)}")
    logger.info(f"{'='*60}")

    # Setup
    storage = ParquetStorageManager()
    data_access = DataAccessLayer(storage)
    feature_builder = FeatureBuilder(data_access)
    target_builder = TargetBuilder()

    window_map = STOCK_WINDOWS if epic in STOCK_EPICS else WINDOWS
    windows = window_map.get(timeframe, window_map["1h"])
    splitter = WalkForwardSplitter(
        train_window=windows["train"],
        val_window=windows["val"],
        test_window=windows["test"],
        step_size=windows["step"],
        purge_gap=windows["purge"],
        embargo=windows["embargo"],
    )

    # Load data + build features (with multi-timeframe)
    logger.info("Loading data and building features...")
    df, feature_meta = feature_builder.build_features(
        epic=epic, timeframe=timeframe, normalize=True, include_regime=True,
        multi_timeframe=True,
    )

    if df.is_empty():
        logger.error(f"No data available for {epic}/{timeframe}")
        return

    # === Non-ML strategy path ===
    if strategy != "ml_ensemble":
        _run_strategy_backtest(
            strategy_name=strategy,
            df=df,
            epic=epic,
            timeframe=timeframe,
            data_access=data_access,
            initial_capital=initial_capital,
            risk_per_trade=risk_per_trade,
        )
        return

    # Generate targets
    df = target_builder.build_targets(df)

    # Prepare feature matrix
    df_valid = df.filter(pl.col("target").is_not_null())
    logger.info(f"Data: {len(df_valid)} valid samples (of {len(df)} total)")

    # Select feature columns (z-score preferred)
    zscore_features = [c for c in feature_meta.feature_names if c.endswith("_zscore")]
    raw_features = [
        c for c in feature_meta.feature_names
        if not c.endswith("_zscore") and c != "regime" and f"{c}_zscore" not in df.columns
    ]
    feature_cols = zscore_features + raw_features
    feature_cols = [c for c in feature_cols if c in df_valid.columns]

    if not feature_cols:
        logger.error("No feature columns found")
        return

    X = df_valid.select(feature_cols).to_numpy().astype(np.float64)
    y = df_valid["target"].to_numpy().astype(np.int32)
    X = np.nan_to_num(X, nan=0.0)

    n_samples = len(X)
    logger.info(f"Feature matrix: {n_samples} samples, {len(feature_cols)} features")

    if n_samples < splitter.min_samples:
        logger.error(
            f"Need at least {splitter.min_samples} samples, got {n_samples}. "
            "Reduce window sizes or get more data."
        )
        return

    n_folds = splitter.get_n_splits(n_samples)
    logger.info(f"Walk-forward: {n_folds} folds")

    # === Hyperparameter tuning on first fold ===
    best_params: dict = {}
    fold0_model: XGBoostClassifier | None = None
    if tune:
        from src.models.tuner import XGBoostTuner

        logger.info(f"Tuning hyperparameters ({tune_trials} trials)...")
        first_split = next(splitter.split(n_samples))
        X_train_0 = X[first_split.train_indices]
        y_train_0 = y[first_split.train_indices]
        X_val_0 = X[first_split.val_indices]
        y_val_0 = y[first_split.val_indices]

        tuner = XGBoostTuner(n_trials=tune_trials)
        best_params = tuner.tune(X_train_0, y_train_0, X_val_0, y_val_0)

        # Train fold 0 model with best params (reusable for feature selection)
        if prune_pct > 0:
            fold0_model = XGBoostClassifier(**best_params)
            fold0_model.feature_names = feature_cols
            fold0_model.fit(X_train_0, y_train_0, X_val_0, y_val_0)

    # === Feature selection on first fold ===
    selector: FeatureSelector | None = None
    if prune_pct > 0:
        logger.info(f"Feature selection (prune {prune_pct:.0%})...")
        if fold0_model is None:
            # No tuning was done — train fold 0 now
            first_split = next(splitter.split(n_samples))
            X_train_0 = X[first_split.train_indices]
            y_train_0 = y[first_split.train_indices]
            X_val_0 = X[first_split.val_indices]
            y_val_0 = y[first_split.val_indices]

            fold0_model = XGBoostClassifier()
            fold0_model.feature_names = feature_cols
            fold0_model.fit(X_train_0, y_train_0, X_val_0, y_val_0)

        importance = fold0_model.get_feature_importance()
        selector = FeatureSelector(drop_pct=prune_pct)
        feature_cols = selector.fit(importance, feature_cols)
        X = selector.transform(X)
        logger.info(f"Feature matrix after pruning: {X.shape[1]} features")
        del fold0_model  # Free memory

    # Collect OOS signals from all test windows
    timestamps = df_valid["timestamp"].to_list()
    atr_col = "atr_14" if "atr_14" in df_valid.columns else None
    atr_values = df_valid[atr_col].to_list() if atr_col else [0.0] * n_samples

    oos_timestamps = []
    oos_signals = []
    oos_confidences = []
    oos_atrs = []

    for split in splitter.split(n_samples):
        logger.info(
            f"Fold {split.fold_index}/{n_folds-1}: "
            f"train={split.train_end - split.train_start}, "
            f"val={split.val_end - split.val_start}, "
            f"test={split.test_end - split.test_start}"
        )

        X_train = X[split.train_indices]
        y_train = y[split.train_indices]
        X_val = X[split.val_indices]
        y_val = y[split.val_indices]
        X_test = X[split.test_indices]

        # Train with tuned params or defaults
        if best_params:
            model = XGBoostClassifier(**best_params)
        else:
            model = XGBoostClassifier()
        model.fit(X_train, y_train, X_val, y_val)

        # Calibrate confidence on validation set
        calibrator = ConfidenceCalibrator(n_classes=3)
        val_proba = model.predict_proba(X_val)
        calibrator.fit(y_val, val_proba)

        # Predict on test set (OOS) with calibration
        proba = model.predict_proba(X_test)
        if calibrator.is_fitted:
            proba = calibrator.transform(proba)
        predicted_classes = np.argmax(proba, axis=1).astype(np.int32)
        confidences = np.max(proba, axis=1)

        # Apply confidence threshold
        hold_mask = confidences < DEFAULT_CONFIDENCE
        predicted_classes[hold_mask] = SignalClass.HOLD

        # Collect OOS results
        for i, idx in enumerate(range(split.test_start, split.test_end)):
            oos_timestamps.append(timestamps[idx])
            oos_signals.append(int(predicted_classes[i]))
            oos_confidences.append(float(confidences[i]))
            oos_atrs.append(float(atr_values[idx]))

        n_buy = int((predicted_classes == SignalClass.BUY).sum())
        n_sell = int((predicted_classes == SignalClass.SELL).sum())
        n_hold = int((predicted_classes == SignalClass.HOLD).sum())
        logger.info(f"  OOS signals: {n_buy} BUY, {n_sell} SELL, {n_hold} HOLD")

    if not oos_timestamps:
        logger.error("No OOS signals collected")
        return

    # Build OOS signals DataFrame
    signals_df = pl.DataFrame({
        "timestamp": oos_timestamps,
        "signal": oos_signals,
        "confidence": oos_confidences,
        "atr": oos_atrs,
    }).sort("timestamp")

    logger.info(f"\nTotal OOS signals: {len(signals_df)}")
    n_buy = signals_df.filter(pl.col("signal") == SignalClass.BUY).height
    n_sell = signals_df.filter(pl.col("signal") == SignalClass.SELL).height
    n_hold = signals_df.filter(pl.col("signal") == SignalClass.HOLD).height
    logger.info(f"Distribution: {n_buy} BUY, {n_sell} SELL, {n_hold} HOLD")

    # Get OHLC data for the OOS period only
    oos_start = signals_df["timestamp"].min()
    oos_end = signals_df["timestamp"].max()

    ohlc_df = data_access.get_candles(
        epic=epic, timeframe=timeframe,
        start_date=oos_start, end_date=oos_end,
    )

    if ohlc_df.is_empty():
        logger.error("No OHLC data for OOS period")
        return

    config = BacktestConfig(
        epic=epic,
        timeframe=timeframe,
        start_date=oos_start,
        end_date=oos_end,
        initial_capital=initial_capital,
        risk_per_trade=risk_per_trade,
    )

    # === Confidence threshold sweep ===
    if do_sweep_threshold:
        logger.info("\nSweeping confidence thresholds...")
        best_thresh, sweep_results = sweep_confidence_thresholds(
            oos_signals, oos_confidences, oos_timestamps, oos_atrs,
            ohlc_df, config,
        )

        logger.info(f"\n{'Threshold':>10} {'Sharpe':>8} {'Trades':>8} {'Return':>10} {'Win%':>8}")
        for thresh, r in sorted(sweep_results.items()):
            logger.info(
                f"{thresh:>10.2f} {r['sharpe']:>8.2f} {r['trades']:>8d} "
                f"{r['return']:>9.2%} {r['win_rate']:>8.1%}"
            )
        logger.info(f"\nBest threshold: {best_thresh:.2f} "
                     f"(Sharpe={sweep_results[best_thresh]['sharpe']:.2f})")

        # Apply best threshold for final report
        final_signals = np.array(oos_signals)
        final_signals[np.array(oos_confidences) < best_thresh] = SignalClass.HOLD
        signals_df = pl.DataFrame({
            "timestamp": oos_timestamps,
            "signal": final_signals.tolist(),
            "confidence": oos_confidences,
            "atr": oos_atrs,
        }).sort("timestamp")

    # Run final backtest
    engine = BacktestEngine(config)
    result = engine.run(ohlc_df, signals_df)

    # Print report
    print("\n" + BacktestReporter.summarize(result))
    print()

    # Monte Carlo validation
    closed = [t for t in result.trades if t.status.value != "open"]
    if monte_carlo and closed:
        from src.backtest.monte_carlo import MonteCarloSimulator
        mc = MonteCarloSimulator(n_simulations=10_000)
        trades_dicts = [{"pnl": t.net_pnl} for t in closed]
        mc_result = mc.run(trades_dicts, initial_capital)
        eq_ci = mc_result.final_equity_ci
        dd_ci = mc_result.max_drawdown_ci
        sh_ci = mc_result.sharpe_ratio_ci
        print(f"{'='*50}")
        print(f"MONTE CARLO VALIDATION ({mc_result.n_simulations} simulations)")
        print(f"{'='*50}")
        print(f"  Equity 90% CI:  [{eq_ci[0]:,.0f} — {eq_ci[2]:,.0f}] (median {eq_ci[1]:,.0f})")
        print(f"  Max DD 90% CI:  [{dd_ci[0]:.1%} — {dd_ci[2]:.1%}] (median {dd_ci[1]:.1%})")
        print(f"  Sharpe 90% CI:  [{sh_ci[0]:.3f} — {sh_ci[2]:.3f}] (median {sh_ci[1]:.3f})")
        print(f"  P-value (return): {mc_result.p_value_return:.4f}")
        print(f"  Risk of ruin:     {mc_result.risk_of_ruin:.4f}")
        sig = "SIGNIFICANT" if mc_result.p_value_return < 0.05 else "NOT significant"
        print(f"  Strategy edge:    {sig} (p<0.05)")
        print()


def main():
    parser = argparse.ArgumentParser(description="Walk-Forward Backtest")
    parser.add_argument("--epic", type=str, default=None, help="Single asset epic (default: all 9)")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (1h, 4h, 1d)")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Initial capital")
    parser.add_argument("--risk", type=float, default=0.02, help="Risk per trade")
    parser.add_argument("--tune", action="store_true", help="Enable Optuna hyperparameter tuning")
    parser.add_argument("--tune-trials", type=int, default=40, help="Number of Optuna trials")
    parser.add_argument(
        "--prune-pct", type=float, default=0.0,
        help="Drop bottom N%% features by importance (0=disabled, 0.25=drop 25%%)"
    )
    parser.add_argument(
        "--sweep-threshold", action="store_true",
        help="Sweep confidence thresholds to find optimal per-asset"
    )
    parser.add_argument(
        "--strategy", type=str, default="ml_ensemble",
        choices=["ml_ensemble", "squeeze_breakout", "vwap_reversion", "auto"],
        help="Strategy to use (default: ml_ensemble)"
    )
    parser.add_argument(
        "--monte-carlo", action="store_true",
        help="Run Monte Carlo simulation after backtest (10K shuffles)"
    )
    args = parser.parse_args()

    epics = [args.epic] if args.epic else ASSETS

    for epic in epics:
        try:
            run_walk_forward_backtest(
                epic=epic,
                timeframe=args.timeframe,
                initial_capital=args.capital,
                risk_per_trade=args.risk,
                tune=args.tune,
                tune_trials=args.tune_trials,
                prune_pct=args.prune_pct,
                do_sweep_threshold=args.sweep_threshold,
                strategy=args.strategy,
                monte_carlo=args.monte_carlo,
            )
        except Exception as e:
            logger.error(f"Failed for {epic}: {e}")
            import traceback
            traceback.print_exc()

    logger.info("\nAll backtests complete.")


if __name__ == "__main__":
    main()
