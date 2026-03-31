"""
Train HMM regime detectors and drift monitors for all active assets.
Saves fitted models to data/models/{epic}/regime/

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/train_regime_detector.py [--epic XAUUSD]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from loguru import logger

from src.data.data_access import DataAccessLayer
from src.features.builder import FeatureBuilder
from src.regime.drift_monitor import DriftMonitor
from src.regime.hmm_detector import HMMRegimeDetector
from src.utils.config import get_settings
from src.utils.constants import TRADABLE_ASSETS


def train_for_epic(epic: str, timeframe: str = "1h") -> bool:
    """Train HMM regime detector and drift monitor for a single asset."""
    logger.info(f"Training regime detector for {epic}/{timeframe}...")
    dal = DataAccessLayer()
    builder = FeatureBuilder(data_access=dal)

    try:
        df, feature_meta = builder.build_features(epic=epic, timeframe=timeframe, normalize=False)
    except Exception as e:
        logger.error(f"[{epic}] Feature build failed: {e}")
        return False

    if len(df) < 500:
        logger.warning(f"[{epic}] Not enough data ({len(df)} bars), skipping")
        return False

    settings = get_settings()

    # Train HMM
    detector = HMMRegimeDetector(
        n_states=4,
        confidence_threshold=settings.regime_gate_confidence_threshold,
    )
    try:
        detector.fit(df)
    except Exception as e:
        logger.error(f"[{epic}] HMM fit failed: {e}")
        return False

    # Train Drift Monitor
    drift = DriftMonitor(psi_threshold=settings.regime_gate_psi_threshold)
    feature_cols = [c for c in feature_meta.feature_names if c in df.columns]
    top_n = settings.regime_gate_top_features
    feature_arrays: dict[str, np.ndarray] = {}
    for col in feature_cols[:top_n]:
        vals = df[col].to_numpy()
        if np.issubdtype(vals.dtype, np.floating):
            vals = vals[~np.isnan(vals)]
        if len(vals) > 10:
            feature_arrays[col] = vals
    drift.fit(feature_arrays)

    # Save
    save_dir = Path(f"data/models/{epic}/regime")
    save_dir.mkdir(parents=True, exist_ok=True)
    detector.save(save_dir / "hmm_detector.pkl")
    drift.save(save_dir / "drift_monitor.pkl")
    with open(save_dir / "drift_features.json", "w") as f:
        json.dump(list(feature_arrays.keys()), f)

    logger.success(f"[{epic}] Regime detector saved to {save_dir}")
    return True


def main() -> None:
    """Train regime detectors for all or a specific asset."""
    parser = argparse.ArgumentParser(description="Train HMM regime detectors")
    parser.add_argument("--epic", type=str, default=None, help="Single epic to train")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (default: 1h)")
    args = parser.parse_args()

    epics = [args.epic] if args.epic else list(TRADABLE_ASSETS)
    success = sum(1 for epic in epics if train_for_epic(epic, args.timeframe))
    logger.info(f"Done: {success}/{len(epics)} regime detectors trained")


if __name__ == "__main__":
    main()
