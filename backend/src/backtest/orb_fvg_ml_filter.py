"""
ML Filter for ORB+FVG Strategy (Phase 2b).

Binary XGBoost classifier: TRADE (1) vs NO_TRADE (0).
Trained on Phase 1 backtest trade outcomes for US500.

Features per trade:
- orb_range_pct: ORB range as % of mid-price
- orb_body_ratio: ORB body vs range (bullishness of opening range)
- fvg_gap_pct: FVG gap size as % of price
- c2_range_pct: C2 (breakout candle) range as % of price
- time_since_open_min: minutes from NYSE open to FVG signal
- direction_is_buy: 1 for BUY, 0 for SELL
- day_of_week: 0=Mon .. 4=Fri
- hour_utc: hour of entry in UTC
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl
from loguru import logger

from src.strategy.orb_fvg_strategy import (
    FVGSignal,
    _minutes_utc,
    _nyse_utc_minutes,
    _NYSE_ORB_START,
    _NYSE_ORB_END,
    _NYSE_ENTRY_CUTOFF,
    _NYSE_SESSION_END,
    process_session,
)
from src.strategy.schemas import SignalDirection

_ET = ZoneInfo("America/New_York")

FEATURE_NAMES = [
    "orb_range_pct",
    "orb_body_ratio",
    "fvg_gap_pct",
    "c2_range_pct",
    "time_since_open_min",
    "direction_is_buy",
    "day_of_week",
    "hour_utc",
]


@dataclass
class TradeFeatures:
    """Features extracted from a single ORB+FVG trade setup."""
    orb_range_pct: float
    orb_body_ratio: float
    fvg_gap_pct: float
    c2_range_pct: float
    time_since_open_min: float
    direction_is_buy: int
    day_of_week: int
    hour_utc: int
    # Label: 1 = WIN (TP hit), 0 = LOSS (SL or EOD loss)
    label: int = 0

    def to_array(self) -> list[float]:
        return [
            self.orb_range_pct,
            self.orb_body_ratio,
            self.fvg_gap_pct,
            self.c2_range_pct,
            self.time_since_open_min,
            float(self.direction_is_buy),
            float(self.day_of_week),
            float(self.hour_utc),
        ]


def extract_features(
    day_bars: list[dict],
    fvg: FVGSignal,
    trade_pnl: float,
    exit_reason: str,
) -> TradeFeatures:
    """Extract ML features from a single day's ORB+FVG trade."""
    session_date = day_bars[0]["timestamp"]
    orb_start = _nyse_utc_minutes(session_date, _NYSE_ORB_START)
    orb_end = _nyse_utc_minutes(session_date, _NYSE_ORB_END)

    # ORB bars
    orb_bars = [b for b in day_bars if orb_start <= _minutes_utc(b["timestamp"]) < orb_end]

    if orb_bars:
        orb_high = max(b["high"] for b in orb_bars)
        orb_low = min(b["low"] for b in orb_bars)
        orb_open = orb_bars[0]["open"]
        orb_close = orb_bars[-1]["close"]
        mid = (orb_high + orb_low) / 2
        orb_range_pct = (orb_high - orb_low) / mid if mid > 0 else 0
        orb_body = abs(orb_close - orb_open)
        orb_range = orb_high - orb_low
        orb_body_ratio = orb_body / orb_range if orb_range > 0 else 0
    else:
        orb_range_pct = 0
        orb_body_ratio = 0
        mid = fvg.entry_price

    # FVG gap size
    c2 = fvg.c2_bar
    c2_range = c2["high"] - c2["low"]
    c2_range_pct = c2_range / mid if mid > 0 else 0

    # FVG gap: difference between C3.low and C1.high (bullish) or C1.low and C3.high (bearish)
    # We approximate from the signal's SL/TP spread
    fvg_gap_pct = abs(fvg.entry_price - fvg.stop_loss) / mid if mid > 0 else 0

    # Time since NYSE open
    entry_minute = _minutes_utc(c2["timestamp"])
    time_since_open = entry_minute - orb_start

    # Direction
    is_buy = 1 if fvg.direction == SignalDirection.BUY else 0

    # Date features
    ts = c2["timestamp"]
    dow = ts.weekday()  # 0=Mon
    hour = ts.hour

    # Label: WIN if TP hit, LOSS otherwise
    label = 1 if exit_reason == "TP" else 0

    return TradeFeatures(
        orb_range_pct=orb_range_pct,
        orb_body_ratio=orb_body_ratio,
        fvg_gap_pct=fvg_gap_pct,
        c2_range_pct=c2_range_pct,
        time_since_open_min=float(time_since_open),
        direction_is_buy=is_buy,
        day_of_week=dow,
        hour_utc=hour,
        label=label,
    )


def build_training_data(
    epic: str = "US500",
    data_dir: str = "data/historical",
    risk_per_trade: float = 0.02,
    initial_capital: float = 10_000.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Run backtest and extract features + labels for every trade.

    Returns (X, y) numpy arrays ready for XGBoost.
    """
    from src.backtest.orb_fvg_runner import _simulate_trade

    parquet_dir = Path(data_dir) / epic / "1min"
    files = sorted(parquet_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No M1 data in {parquet_dir}")

    frames = [pl.read_parquet(str(f)) for f in files]
    df = pl.concat(frames).sort("timestamp")
    df = df.with_columns(pl.col("timestamp").dt.date().alias("trade_date"))
    dates = df["trade_date"].unique().sort().to_list()

    features_list: list[TradeFeatures] = []

    for d in dates:
        day_df = df.filter(pl.col("trade_date") == d)
        day_bars = day_df.drop("trade_date").to_dicts()

        for bar in day_bars:
            ts = bar["timestamp"]
            if isinstance(ts, datetime) and ts.tzinfo is None:
                bar["timestamp"] = ts.replace(tzinfo=timezone.utc)

        fvg = process_session(day_bars)
        if fvg is None:
            continue

        # Find entry bar
        entry_idx = None
        for i, bar in enumerate(day_bars):
            if (
                abs(bar["open"] - fvg.entry_price) < 1e-9
                and _minutes_utc(bar["timestamp"]) > _minutes_utc(fvg.c2_bar["timestamp"])
            ):
                entry_idx = i
                break

        if entry_idx is None:
            entry_idx = min(8, len(day_bars) - 1)

        bars_after = day_bars[entry_idx + 1:]
        trade = _simulate_trade(fvg, bars_after, epic, str(d))

        feat = extract_features(day_bars, fvg, trade.pnl, trade.exit_reason)
        features_list.append(feat)

    X = np.array([f.to_array() for f in features_list], dtype=np.float32)
    y = np.array([f.label for f in features_list], dtype=np.int32)

    logger.info(
        f"Built training data: {len(features_list)} samples, "
        f"{y.sum()} wins ({y.mean():.1%}), {len(y) - y.sum()} losses"
    )

    return X, y


def train_filter(
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
) -> dict:
    """
    Train XGBoost binary classifier with time-series cross-validation.

    Returns dict with 'model', 'cv_scores', 'feature_importance'.
    """
    from xgboost import XGBClassifier
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    tscv = TimeSeriesSplit(n_splits=n_splits)

    cv_metrics: list[dict] = []
    best_model = None
    best_f1 = -1

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        model = XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=len(y_train[y_train == 0]) / max(len(y_train[y_train == 1]), 1),
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
        )

        model.fit(X_train, y_train)
        y_pred = model.predict(X_val)

        metrics = {
            "fold": fold,
            "accuracy": accuracy_score(y_val, y_pred),
            "precision": precision_score(y_val, y_pred, zero_division=0),
            "recall": recall_score(y_val, y_pred, zero_division=0),
            "f1": f1_score(y_val, y_pred, zero_division=0),
            "val_size": len(y_val),
            "val_win_rate": float(y_val.mean()),
            "pred_trade_rate": float(y_pred.mean()),
        }
        cv_metrics.append(metrics)

        if metrics["f1"] > best_f1:
            best_f1 = metrics["f1"]
            best_model = model

        logger.info(
            f"  Fold {fold}: acc={metrics['accuracy']:.3f} prec={metrics['precision']:.3f} "
            f"rec={metrics['recall']:.3f} f1={metrics['f1']:.3f} "
            f"trade_rate={metrics['pred_trade_rate']:.1%}"
        )

    # Train final model on all data
    final_model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=len(y[y == 0]) / max(len(y[y == 1]), 1),
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )
    final_model.fit(X, y)

    # Feature importance
    importance = dict(zip(FEATURE_NAMES, final_model.feature_importances_.tolist()))

    return {
        "model": final_model,
        "cv_metrics": cv_metrics,
        "feature_importance": importance,
        "avg_f1": np.mean([m["f1"] for m in cv_metrics]),
        "avg_precision": np.mean([m["precision"] for m in cv_metrics]),
        "avg_recall": np.mean([m["recall"] for m in cv_metrics]),
    }


def run_walkforward_backtest(
    epic: str = "US500",
    data_dir: str = "data/historical",
    initial_capital: float = 10_000.0,
    risk_per_trade: float = 0.02,
    train_window: int = 60,
    threshold: float = 0.5,
) -> dict:
    """
    Walk-forward backtest: train on first N trades, predict trade N+1, roll forward.

    This prevents look-ahead bias. The model only sees past trades when making
    predictions, exactly like real trading.

    Args:
        train_window: minimum number of trades before ML filter activates
        threshold: probability threshold for TRADE decision

    Returns comparison dict with filtered vs unfiltered metrics.
    """
    from xgboost import XGBClassifier
    from src.backtest.orb_fvg_runner import _simulate_trade, _calculate_metrics, ORBBacktestResult

    parquet_dir = Path(data_dir) / epic / "1min"
    files = sorted(parquet_dir.glob("*.parquet"))
    frames = [pl.read_parquet(str(f)) for f in files]
    df = pl.concat(frames).sort("timestamp")
    df = df.with_columns(pl.col("timestamp").dt.date().alias("trade_date"))
    dates = df["trade_date"].unique().sort().to_list()

    result_all = ORBBacktestResult(epic=epic, period="all")
    result_filtered = ORBBacktestResult(epic=epic, period="filtered")
    equity_all = initial_capital
    equity_filtered = initial_capital

    # Accumulate features/labels for walk-forward training
    all_features: list[list[float]] = []
    all_labels: list[int] = []

    filtered_out = 0
    filtered_out_would_win = 0
    filtered_out_would_lose = 0
    current_model = None
    retrain_every = 20  # retrain every N new trades

    for d in dates:
        result_all.total_sessions += 1
        result_filtered.total_sessions += 1

        day_df = df.filter(pl.col("trade_date") == d)
        day_bars = day_df.drop("trade_date").to_dicts()

        for bar in day_bars:
            ts = bar["timestamp"]
            if isinstance(ts, datetime) and ts.tzinfo is None:
                bar["timestamp"] = ts.replace(tzinfo=timezone.utc)

        fvg = process_session(day_bars)
        if fvg is None:
            result_all.sessions_skipped += 1
            result_filtered.sessions_skipped += 1
            result_all.daily_equity.append(equity_all)
            result_filtered.daily_equity.append(equity_filtered)
            continue

        # Find entry bar
        entry_idx = None
        for i, bar in enumerate(day_bars):
            if (
                abs(bar["open"] - fvg.entry_price) < 1e-9
                and _minutes_utc(bar["timestamp"]) > _minutes_utc(fvg.c2_bar["timestamp"])
            ):
                entry_idx = i
                break

        if entry_idx is None:
            entry_idx = min(8, len(day_bars) - 1)

        bars_after = day_bars[entry_idx + 1:]
        risk_per_unit = abs(fvg.entry_price - fvg.stop_loss)
        if risk_per_unit <= 0:
            result_all.sessions_skipped += 1
            result_filtered.sessions_skipped += 1
            result_all.daily_equity.append(equity_all)
            result_filtered.daily_equity.append(equity_filtered)
            continue

        trade = _simulate_trade(fvg, bars_after, epic, str(d))

        # Unfiltered: always take the trade
        position_size_all = (equity_all * risk_per_trade) / risk_per_unit
        trade_all = _simulate_trade(fvg, bars_after, epic, str(d))
        trade_all.pnl = trade_all.pnl * position_size_all
        equity_all += trade_all.pnl
        result_all.trades.append(trade_all)
        result_all.daily_equity.append(equity_all)

        # Extract features for this trade
        feat = extract_features(day_bars, fvg, trade.pnl, trade.exit_reason)
        X_pred = np.array([feat.to_array()], dtype=np.float32)

        # Walk-forward: only use ML filter if we have enough training data
        take_trade = True
        if current_model is not None and len(all_features) >= train_window:
            prob = current_model.predict_proba(X_pred)[0][1]
            take_trade = prob >= threshold

        if take_trade:
            position_size_filt = (equity_filtered * risk_per_trade) / risk_per_unit
            trade_filt = _simulate_trade(fvg, bars_after, epic, str(d))
            trade_filt.pnl = trade_filt.pnl * position_size_filt
            equity_filtered += trade_filt.pnl
            result_filtered.trades.append(trade_filt)
            result_filtered.daily_equity.append(equity_filtered)
        else:
            filtered_out += 1
            if trade.exit_reason == "TP":
                filtered_out_would_win += 1
            else:
                filtered_out_would_lose += 1
            result_filtered.sessions_skipped += 1
            result_filtered.daily_equity.append(equity_filtered)

        # Add to training set AFTER prediction (no look-ahead)
        all_features.append(feat.to_array())
        all_labels.append(feat.label)

        # Retrain periodically once we have enough data
        n = len(all_features)
        if n >= train_window and n % retrain_every == 0:
            X_train = np.array(all_features, dtype=np.float32)
            y_train = np.array(all_labels, dtype=np.int32)
            n_pos = y_train.sum()
            n_neg = len(y_train) - n_pos
            spw = n_neg / max(n_pos, 1)

            current_model = XGBClassifier(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                scale_pos_weight=spw,
                eval_metric="logloss",
                random_state=42,
                verbosity=0,
            )
            current_model.fit(X_train, y_train)

    _calculate_metrics(result_all, initial_capital)
    _calculate_metrics(result_filtered, initial_capital)

    return {
        "unfiltered": result_all,
        "filtered": result_filtered,
        "filtered_out_total": filtered_out,
        "filtered_out_would_win": filtered_out_would_win,
        "filtered_out_would_lose": filtered_out_would_lose,
        "threshold": threshold,
        "train_window": train_window,
        "total_trades_seen": len(all_features),
    }
