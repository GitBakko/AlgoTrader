"""
MANTIS AI — SHAP Prune A/B Validation
=====================================
Validates whether SHAP-based feature pruning hurts the XGBoost model BEFORE
any production change. Apples-to-apples walk-forward:

  * SAME features build (FeatureBuilder, prod flags) + SAME targets + SAME
    WalkForwardSplitter + SAME hyperparameters + SAME seed (xgb random_state=42).
  * ONLY the feature set differs: baseline (full meta.feature_names) vs pruned
    (SHAP keep-list from data/shap_analysis/{epic}_1h_features.json).

Injection point: ModelTrainer.train_on_dataframe(feature_names=...) — the trainer
restricts to that list (intersect df, minus EXCLUDE_FEATURES). NO trainer core edit.
save_best=False — never overwrites the production model.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/validate_prune.py --epic BTCUSD
    .venv/Scripts/python.exe scripts/validate_prune.py --epic BTCUSD --timeframe 1h
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

SHAP_DIR = ROOT / "data" / "shap_analysis"


def _avg(metrics: dict, key: str):
    v = (metrics or {}).get(key)
    return float(v) if v is not None else float("nan")


def run_variant(label, df, feature_names, epic, timeframe, splitter):
    """Train one walk-forward variant on a prebuilt df. Returns avg test metrics."""
    from src.models.trainer import ModelTrainer
    from src.models.xgboost_model import XGBoostClassifier

    trainer = ModelTrainer(splitter=splitter)
    model = XGBoostClassifier(feature_names=feature_names)
    print(f"\n  ▶ {label}: {len(feature_names)} feature richieste ...")
    result = trainer.train_on_dataframe(
        model=model,
        df=df,
        feature_names=feature_names,
        epic=epic,
        timeframe=timeframe,
        save_best=False,  # NEVER clobber production model
    )
    test = result.avg_test_metrics or {}
    val = result.avg_val_metrics or {}
    return {
        "label": label,
        "n_features_requested": len(feature_names),
        "num_folds": result.num_folds,
        "test_f1_macro": _avg(test, "f1_macro"),
        "test_accuracy": _avg(test, "accuracy"),
        "test_log_loss": _avg(test, "log_loss"),
        "test_f1_BUY": _avg(test, "f1_BUY"),
        "test_f1_SELL": _avg(test, "f1_SELL"),
        "test_f1_HOLD": _avg(test, "f1_HOLD"),
        "val_f1_macro": _avg(val, "f1_macro"),
    }


def main():
    p = argparse.ArgumentParser(description="SHAP prune A/B walk-forward validation")
    p.add_argument("--epic", type=str, default="BTCUSD")
    p.add_argument("--timeframe", type=str, default="1h")
    p.add_argument("--lookback-days", type=int, default=400)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    np.random.seed(args.seed)
    epic, tf = args.epic.upper(), args.timeframe

    from src.data.data_access import DataAccessLayer
    from src.features.builder import FeatureBuilder
    from src.models.asset_metadata import compute_walk_forward_windows
    from src.models.target_builder import TargetBuilder
    from src.models.versioning import ModelVersioning
    from src.models.walk_forward import WalkForwardSplitter
    from src.models.xgboost_model import XGBoostClassifier

    # ── 1. Baseline feature set (current prod model) + SHAP keep-list ─────────
    versioning = ModelVersioning(base_dir=ROOT / "data" / "models")
    models = [m for m in versioning.list_models(epic) if m.model_type == "xgboost"]
    if not models:
        print(f"❌ Nessun modello XGBoost per {epic}")
        sys.exit(1)
    _, meta = versioning.load_model(XGBoostClassifier, epic, models[0].model_id)
    baseline_feats = list(meta.feature_names or [])

    shap_json = SHAP_DIR / f"{epic}_{tf}_features.json"
    if not shap_json.exists():
        print(f"❌ Manca {shap_json} — esegui prima scripts/shap_analysis.py --epic {epic}")
        sys.exit(1)
    keep_feats = json.loads(shap_json.read_text())["keep_features"]

    print(f"🦗 PRUNE A/B — {epic}/{tf}")
    print(f"   baseline: {len(baseline_feats)} feat (model {models[0].model_id})")
    print(f"   pruned:   {len(keep_feats)} feat (SHAP keep)")

    # ── 2. Build features + targets ONCE (shared by both variants) ────────────
    end = datetime.now().replace(tzinfo=None)
    start = end - timedelta(days=args.lookback_days)
    has_multi_tf = any(f.startswith(("4h_", "1d_")) for f in baseline_feats)
    has_cross = any(f.startswith(("corr_", "lead_", "sector_")) for f in baseline_feats)

    builder = FeatureBuilder(data_access=DataAccessLayer())
    df, _ = builder.build_features(
        epic=epic,
        timeframe=tf,
        start_date=start,
        end_date=end,
        normalize=True,
        include_regime=True,
        multi_timeframe=has_multi_tf,
        cross_asset=has_cross,
        sil_data=None,
    )
    df = TargetBuilder().build_targets(df)
    print(f"   dataset: {len(df)} righe")

    # Walk-forward windows identical to production orchestrator.
    w = compute_walk_forward_windows(epic, tf)
    splitter = WalkForwardSplitter(
        train_window=w["train_window"],
        val_window=w["val_window"],
        test_window=w["test_window"],
        step_size=w["step_size"],
        purge_gap=5,
        embargo=2,  # match production orchestrator
    )

    # ── 3. Run both variants ──────────────────────────────────────────────────
    base = run_variant("BASELINE", df, baseline_feats, epic, tf, splitter)
    pruned = run_variant("PRUNED", df, keep_feats, epic, tf, splitter)

    # ── 4. Compare ────────────────────────────────────────────────────────────
    print(f"\n{'='*64}\n📊 A/B RESULT — {epic}/{tf}\n{'='*64}")
    print(f"  {'metric':<16}{'baseline':>12}{'pruned':>12}{'Δ':>12}")
    print(f"  {'-'*16}{'-'*12}{'-'*12}{'-'*12}")
    metrics = [
        ("f1_macro", "test_f1_macro", True),
        ("accuracy", "test_accuracy", True),
        ("log_loss", "test_log_loss", False),  # lower is better
        ("f1_BUY", "test_f1_BUY", True),
        ("f1_SELL", "test_f1_SELL", True),
        ("f1_HOLD", "test_f1_HOLD", True),
        ("val_f1_macro", "val_f1_macro", True),
    ]
    verdict_ok = True
    for name, key, higher_better in metrics:
        b, pr = base[key], pruned[key]
        delta = pr - b
        flag = ""
        if name in ("f1_macro", "test_f1_macro"):
            # primary gate: pruned must not lose >2% absolute f1_macro
            if delta < -0.02:
                verdict_ok = False
                flag = "  ⚠️ REGRESSION"
        print(f"  {name:<16}{b:>12.4f}{pr:>12.4f}{delta:>+12.4f}{flag}")

    print(f"\n  folds: baseline={base['num_folds']} pruned={pruned['num_folds']}")
    print(
        f"  feature: {base['n_features_requested']} → {pruned['n_features_requested']} "
        f"(-{(1 - pruned['n_features_requested']/max(base['n_features_requested'],1))*100:.0f}%)"
    )

    out = SHAP_DIR / f"{epic}_{tf}_prune_ab.json"
    out.write_text(json.dumps({"baseline": base, "pruned": pruned}, indent=2))
    print(f"\n  💾 {out}")

    print(
        f"\n{'✅ PRUNE OK' if verdict_ok else '❌ PRUNE REGREDISCE'} "
        f"(gate: f1_macro non perde >2% assoluto)"
    )


if __name__ == "__main__":
    main()
