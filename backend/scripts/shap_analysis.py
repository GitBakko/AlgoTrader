"""
MANTIS AI — SHAP Feature Importance Analysis (v2)
=================================================
Rewrite of the original gain-importance-in-disguise script.

WHY THE REWRITE
---------------
The engineered feature matrix (ema_*, macd, rsi, cross-asset, sil_* ... 199 cols)
is NEVER persisted in this project — the trainer builds it on the fly via
`FeatureBuilder.build_features()` from OHLC in `data/historical/`. The previous
script globbed for `{epic}*.parquet`, never matched (files are `YYYY-MM.parquet`),
and silently fell back to XGBoost gain importance — so it never computed SHAP.

This version reproduces the PRODUCTION stack offline:
    ModelVersioning.list_models(epic)         # latest by created_at (not name sort)
        -> versioning.load_model(XGBoostClassifier, epic, id)   # model + metadata
    FeatureBuilder.build_features(...)         # same flags inferred from feature_names
        -> align columns EXACTLY to metadata.feature_names (fill missing -> 0)
    shap.TreeExplainer(booster).shap_values(X) # handles list / (n,f,c) / (n,f)

Produces:
  1. SHAP values per asset (global + per-class BUY/SELL/HOLD)
  2. Ranking by mean|SHAP|, cumulative %, thematic group
  3. Pruning (cumulative <= threshold) cross-checked vs EXCLUDE_FEATURES
  4. Redundancy: clusters of features with |corr| > threshold in the real matrix
  5. Report + CSV + JSON + (optional) plots

Usage (run from backend/):
    .venv/Scripts/python.exe scripts/shap_analysis.py
    .venv/Scripts/python.exe scripts/shap_analysis.py --epic BTCUSD
    .venv/Scripts/python.exe scripts/shap_analysis.py --epic BTCUSD --prune-threshold 0.85
    .venv/Scripts/python.exe scripts/shap_analysis.py --gain      # gain fallback, no shap dep
    .venv/Scripts/python.exe scripts/shap_analysis.py --quiet

Extra deps (only for real SHAP / plots):
    pip install shap matplotlib
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

# ── Path setup: backend/ on sys.path so `import src.*` resolves ──────────────
ROOT = Path(__file__).resolve().parents[1]  # == backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows consoles default to cp1252 and choke on the report emojis.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

DEFAULT_MODELS_DIR = ROOT / "data" / "models"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "shap_analysis"

# Class index -> name (matches src.models.schemas.SignalClass: 0=SELL,1=HOLD,2=BUY)
CLASS_NAMES = {0: "SELL", 1: "HOLD", 2: "BUY"}


# ═════════════════════════════════════════════════════════════════════════════
# PURE FUNCTIONS  (no model / no network — unit-tested in tests/models/)
# ═════════════════════════════════════════════════════════════════════════════

# Ordered (group, prefixes) — first prefix that `startswith`-matches wins.
# Longer / more specific prefixes are listed before generic ones on purpose.
FEATURE_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("structure", ("bos_", "choch_", "structure_")),
    ("trend", ("ema_", "macd", "adx", "plus_di", "minus_di", "sma_", "trend_", "di_")),
    ("momentum", ("rsi", "stoch", "returns", "return_", "roc", "mom_")),
    (
        "volatility",
        (
            "atr",
            "bb_",
            "kc_",
            "hvol",
            "squeeze_",
            "vwap_sd",
            "high_low_range",
            "range_",
        ),
    ),
    ("volume", ("obv", "volume", "vwap")),
    (
        "price_action",
        (
            "close_position",
            "price_position",
            "gap_",
            "open_",
            "hl_",
            "candle_",
            "body_",
            "wick_",
        ),
    ),
    ("regime", ("regime_",)),
    ("session", ("hour_", "dow_", "session_", "minute_")),
    ("sil_macro", ("sil_", "vix_", "dxy_", "yield_", "macro_", "breakeven_")),
    (
        "sentiment",
        (
            "insider_",
            "analyst_",
            "price_target_",
            "earnings_",
            "news_sentiment",
            "sentiment_",
        ),
    ),
    ("cross_asset", ("corr_", "rolling_corr_", "lead_lag_", "lead_", "sector_")),
]

# Higher-timeframe prefixes stripped before thematic classification.
_TF_PREFIXES = ("4h_", "1d_", "1w_")


def classify_feature(name: str) -> str:
    """Assign a feature to a thematic group via longest-specific prefix match.

    Strips multi-timeframe (``4h_``/``1d_``) and ``_zscore`` decorations first so
    ``4h_ema_50`` and ``ema_50_zscore`` land in the same group as ``ema_50``.
    """
    n = name.lower()
    for tf in _TF_PREFIXES:
        if n.startswith(tf):
            n = n[len(tf) :]
            break
    if n.endswith("_zscore"):
        n = n[: -len("_zscore")]

    for group, prefixes in FEATURE_GROUPS:
        if any(n.startswith(p) for p in prefixes):
            return group
    return "other"


def aggregate_mean_abs_shap(shap_output, n_features: int) -> tuple[np.ndarray, np.ndarray | None]:
    """Normalize any TreeExplainer output into mean|SHAP| arrays.

    SHAP/XGBoost return shape varies by version for a 3-class model:
      * old shap  -> list of C arrays, each (n_samples, n_features)
      * shap>=0.41 -> ndarray (n_samples, n_features, n_classes)
      * binary/regression -> ndarray (n_samples, n_features)

    Returns:
        global_mean_abs: (n_features,)  — mean over samples and classes
        per_class_mean_abs: (n_features, n_classes) or None for single-output
    """
    if isinstance(shap_output, list):
        # list of (n, f) -> (n, f, c)
        arr = np.stack([np.asarray(a) for a in shap_output], axis=-1)
    else:
        arr = np.asarray(shap_output)

    if arr.ndim == 3:  # (n, f, c)
        if arr.shape[1] != n_features and arr.shape[2] == n_features:
            # some versions emit (n, c, f) — transpose to (n, f, c)
            arr = np.transpose(arr, (0, 2, 1))
        per_class = np.abs(arr).mean(axis=0)  # (f, c)
        global_mean = per_class.mean(axis=1)  # (f,)
        return global_mean, per_class
    if arr.ndim == 2:  # (n, f)
        return np.abs(arr).mean(axis=0), None
    raise ValueError(f"Unexpected SHAP output ndim={arr.ndim}, shape={arr.shape}")


def build_ranking(
    feature_names: list[str],
    mean_abs: np.ndarray,
    prune_threshold: float,
) -> list[dict]:
    """Rank features by mean|SHAP| desc with cumulative % and keep flag."""
    mean_abs = np.asarray(mean_abs, dtype=np.float64)
    total = float(mean_abs.sum())
    order = np.argsort(mean_abs)[::-1]

    ranking: list[dict] = []
    cumulative = 0.0
    for rank, idx in enumerate(order):
        val = float(mean_abs[idx])
        pct = (val / total * 100.0) if total > 0 else 0.0
        cumulative += pct
        ranking.append(
            {
                "rank": rank + 1,
                "feature": feature_names[idx],
                "mean_abs_shap": val,
                "pct_of_total": round(pct, 4),
                "cumulative_pct": round(cumulative, 4),
                "group": classify_feature(feature_names[idx]),
                "keep": cumulative <= prune_threshold * 100.0,
            }
        )
    return ranking


def find_redundant_clusters(
    X: np.ndarray,
    feature_names: list[str],
    corr_threshold: float = 0.9,
) -> list[list[str]]:
    """Cluster features whose pairwise |Pearson corr| exceeds the threshold.

    Greedy union-find over the abs-correlation matrix. Constant columns
    (std == 0 -> nan corr) never join a cluster. Returns clusters of size >= 2.
    """
    X = np.asarray(X, dtype=np.float64)
    n = X.shape[1]
    if n != len(feature_names) or n < 2:
        return []

    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(X, rowvar=False)
    corr = np.abs(np.nan_to_num(corr, nan=0.0))

    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if corr[i, j] > corr_threshold:
                union(i, j)

    groups: dict[int, list[str]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(feature_names[i])

    return sorted(
        (members for members in groups.values() if len(members) >= 2),
        key=len,
        reverse=True,
    )


def group_distribution(ranking: list[dict]) -> dict[str, float]:
    """Aggregate pct_of_total by thematic group."""
    out: dict[str, float] = {}
    for r in ranking:
        out[r["group"]] = out.get(r["group"], 0.0) + r["pct_of_total"]
    return {k: round(v, 3) for k, v in sorted(out.items(), key=lambda kv: kv[1], reverse=True)}


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION  (touches src.* — production stack)
# ═════════════════════════════════════════════════════════════════════════════


def load_latest_xgb(models_dir: Path, epic: str):
    """Load the latest XGBoost model for an epic via ModelVersioning.

    Returns (model, metadata) or (None, None) if no xgboost model exists.
    """
    from src.models.versioning import ModelVersioning
    from src.models.xgboost_model import XGBoostClassifier

    versioning = ModelVersioning(base_dir=models_dir)
    models = [m for m in versioning.list_models(epic) if m.model_type == "xgboost"]
    if not models:
        return None, None
    latest = models[0]  # list_models already sorts by created_at desc
    model, meta = versioning.load_model(XGBoostClassifier, epic, latest.model_id)
    return model, meta


def build_aligned_matrix(
    meta,
    timeframe: str,
    lookback_days: int,
    n_samples: int,
) -> tuple[np.ndarray | None, list[str]]:
    """Rebuild the feature matrix offline and align to ``meta.feature_names``.

    Mirrors prediction_service flag inference. Returns (X (n, 199), feature_names)
    where feature_names == meta.feature_names (order preserved, missing cols -> 0).
    """

    from src.data.data_access import DataAccessLayer
    from src.features.builder import FeatureBuilder

    feature_names: list[str] = list(meta.feature_names or [])
    if not feature_names:
        return None, []

    has_multi_tf = any(f.startswith(("4h_", "1d_")) for f in feature_names)
    has_cross_asset = any(f.startswith(("corr_", "lead_", "sector_")) for f in feature_names)

    # storage.read_candles compares against naive file dates — pass naive UTC.
    end = datetime.now(UTC).replace(tzinfo=None)
    start = end - timedelta(days=lookback_days)

    builder = FeatureBuilder(data_access=DataAccessLayer())
    df, matrix = builder.build_features(
        epic=meta.epic,
        timeframe=timeframe,
        start_date=start,
        end_date=end,
        normalize=True,
        include_regime=True,
        multi_timeframe=has_multi_tf,
        cross_asset=has_cross_asset,
        sil_data=None,
    )
    if df.is_empty() or matrix.num_features == 0:
        return None, feature_names

    present = [c for c in feature_names if c in df.columns]
    missing = [c for c in feature_names if c not in df.columns]
    if missing:
        print(
            f"  ⚠️  {len(missing)}/{len(feature_names)} feature non presenti nel build "
            f"(riempite con 0): es. {missing[:5]}"
        )

    df_present = df.select(present).tail(n_samples) if present else df.head(0)
    n_rows = len(df_present)
    if n_rows == 0:
        return None, feature_names

    # Assemble full (n, len(feature_names)) matrix in model order, missing -> 0.
    col_data = {c: df_present[c].to_numpy() for c in present}
    cols = [
        col_data[name] if name in col_data else np.zeros(n_rows, dtype=np.float64)
        for name in feature_names
    ]
    X = np.column_stack(cols).astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X, feature_names


def compute_shap(model, X: np.ndarray, n_features: int):
    """TreeExplainer on the raw booster. Returns raw shap_output (version-agnostic)."""
    import shap  # lazy: only needed for real SHAP

    booster = model._model.get_booster()
    explainer = shap.TreeExplainer(booster)
    print(f"  🔢 SHAP TreeExplainer su {X.shape[0]} campioni × {X.shape[1]} feature...")
    return explainer.shap_values(X)


def gain_importance_vector(model, feature_names: list[str]) -> np.ndarray:
    """Gain importance as a vector aligned to feature_names (fallback / --gain)."""
    gain = model.get_feature_importance()  # name -> gain
    return np.array([float(gain.get(name, 0.0)) for name in feature_names], dtype=np.float64)


# ═════════════════════════════════════════════════════════════════════════════
# REPORT / IO
# ═════════════════════════════════════════════════════════════════════════════


def analyze_epic(
    epic: str,
    models_dir: Path,
    output_dir: Path,
    prune_threshold: float,
    corr_threshold: float,
    n_samples: int,
    lookback_days: int,
    use_gain: bool,
    quiet: bool,
) -> dict:
    model, meta = load_latest_xgb(models_dir, epic)
    if model is None:
        print(f"  ⚠️  Nessun modello XGBoost per {epic}. Skip.")
        return {}

    timeframe = getattr(meta, "timeframe", "1h") or "1h"
    feature_names = list(meta.feature_names or [])
    n_features = len(feature_names)
    print(
        f"\n{'='*64}\n📊 {meta.epic} | {timeframe} | model={meta.model_id} | {n_features} feature\n{'='*64}"
    )

    per_class = None
    redundant: list[list[str]] = []
    mode = "shap"

    X = None
    if not use_gain:
        X, feature_names = build_aligned_matrix(meta, timeframe, lookback_days, n_samples)

    if use_gain or X is None:
        if not use_gain:
            print("  ⚠️  Matrice feature non ricostruibile → fallback gain importance.")
        mean_abs = gain_importance_vector(model, feature_names)
        mode = "gain"
    else:
        try:
            raw = compute_shap(model, X, n_features)
            mean_abs, per_class = aggregate_mean_abs_shap(raw, n_features)
            redundant = find_redundant_clusters(X, feature_names, corr_threshold)
        except ImportError:
            print("  ℹ️  `shap` non installato → fallback gain. (pip install shap)")
            mean_abs = gain_importance_vector(model, feature_names)
            mode = "gain"

    ranking = build_ranking(feature_names, mean_abs, prune_threshold)
    groups = group_distribution(ranking)
    keep = [r["feature"] for r in ranking if r["keep"]]
    prune = [r["feature"] for r in ranking if not r["keep"]]
    zero = [r["feature"] for r in ranking if r["mean_abs_shap"] == 0.0]

    if not quiet:
        _print_report(
            meta,
            timeframe,
            ranking,
            groups,
            keep,
            prune,
            zero,
            redundant,
            prune_threshold,
            mode,
            per_class,
        )

    _save(meta, timeframe, ranking, keep, prune, groups, redundant, output_dir, mode)

    if not use_gain and X is not None and per_class is not None and not quiet:
        _try_plot(meta, timeframe, X, feature_names, ranking, output_dir)

    return {
        "epic": meta.epic,
        "timeframe": timeframe,
        "model_id": meta.model_id,
        "mode": mode,
        "n_features_total": n_features,
        "n_features_keep": len(keep),
        "n_features_prune": len(prune),
        "n_features_zero": len(zero),
        "keep_features": keep,
        "prune_features": prune,
        "zero_features": zero,
        "group_distribution": groups,
        "redundant_clusters": redundant,
        "ranking": ranking,
    }


def _print_report(
    meta,
    timeframe,
    ranking,
    groups,
    keep,
    prune,
    zero,
    redundant,
    prune_threshold,
    mode,
    per_class,
):
    thr = int(prune_threshold * 100)
    src = "SHAP (mean|value|)" if mode == "shap" else "GAIN importance (fallback)"
    print(f"\n  Sorgente importanza: {src}")

    print(f"\n📈 TOP 30 — {meta.epic}/{timeframe}")
    print(f"  {'#':>4}  {'feature':<38}  {'imp%':>6}  {'cum%':>6}  group")
    print(f"  {'-'*4}  {'-'*38}  {'-'*6}  {'-'*6}  {'-'*12}")
    for r in ranking[:30]:
        mark = "✅" if r["keep"] else "  "
        print(
            f"  {r['rank']:>4}  {r['feature']:<38}  {r['pct_of_total']:>5.1f}%  "
            f"{r['cumulative_pct']:>5.1f}%  {r['group']} {mark}"
        )

    print("\n🏷️  GRUPPI (% importanza totale):")
    for g, pct in groups.items():
        print(f"  {g:<14} {pct:>6.1f}%  {'█' * int(pct / 2)}")

    print(f"\n✂️  PRUNING (soglia cumulativa {thr}%):")
    print(f"  keep:  {len(keep):>4}   prune: {len(prune):>4}   zero-importance: {len(zero):>4}")
    if ranking:
        red = (1 - len(keep) / len(ranking)) * 100
        print(f"  riduzione: {len(ranking)} → {len(keep)} (-{red:.0f}%)")

    if redundant:
        print("\n🔁 RIDONDANZA (|corr| alto — candidati a fusione/drop):")
        for cl in redundant[:12]:
            print(f"  • {{{', '.join(cl[:6])}{' …' if len(cl) > 6 else ''}}}  (n={len(cl)})")

    if zero:
        print(
            f"\n🗑️  ZERO-IMPORTANCE ({len(zero)}): {', '.join(zero[:15])}"
            f"{' …' if len(zero) > 15 else ''}"
        )


def _save(meta, timeframe, ranking, keep, prune, groups, redundant, output_dir, mode):
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = meta.epic.replace("/", "_")

    csv_path = output_dir / f"{safe}_{timeframe}_ranking.csv"
    header = "rank,feature,mean_abs_shap,pct_of_total,cumulative_pct,group,keep"
    rows = [
        f"{r['rank']},{r['feature']},{r['mean_abs_shap']:.8f},"
        f"{r['pct_of_total']:.4f},{r['cumulative_pct']:.4f},{r['group']},{r['keep']}"
        for r in ranking
    ]
    csv_path.write_text(header + "\n" + "\n".join(rows))

    json_path = output_dir / f"{safe}_{timeframe}_features.json"
    json_path.write_text(
        json.dumps(
            {
                "epic": meta.epic,
                "timeframe": timeframe,
                "model_id": meta.model_id,
                "mode": mode,
                "n_features_keep": len(keep),
                "n_features_prune": len(prune),
                "group_distribution": groups,
                "keep_features": keep,
                "features_to_exclude": prune,
                "redundant_clusters": redundant,
            },
            indent=2,
        )
    )
    print(f"\n  💾 {csv_path.name} + {json_path.name}")


def _try_plot(meta, timeframe, X, feature_names, ranking, output_dir):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  ℹ️  matplotlib assente → niente grafici (pip install matplotlib)")
        return
    try:
        top = ranking[:25][::-1]
        names = [r["feature"] for r in top]
        vals = [r["mean_abs_shap"] for r in top]
        fig, ax = plt.subplots(figsize=(9, 8))
        ax.barh(names, vals, color="#00d97e")
        ax.set_title(f"{meta.epic}/{timeframe} — mean|SHAP| top 25")
        ax.set_xlabel("mean |SHAP|")
        fig.tight_layout()
        p = output_dir / f"{meta.epic.replace('/', '_')}_{timeframe}_shap_top.png"
        fig.savefig(p, dpi=140, bbox_inches="tight")
        plt.close(fig)
        print(f"  🖼️  {p.name}")
    except Exception as e:  # noqa: BLE001 - plotting is best-effort
        print(f"  ⚠️  plot fallito: {e}")


def cross_asset_summary(results: list[dict]):
    from collections import Counter

    if len(results) < 2:
        return
    print(f"\n{'='*64}\n🌍 CROSS-ASSET\n{'='*64}")
    n = len(results)

    keep_counter: Counter[str] = Counter()
    zero_counter: Counter[str] = Counter()
    group_tot: Counter[str] = Counter()
    for r in results:
        keep_counter.update(r.get("keep_features", []))
        zero_counter.update(r.get("zero_features", []))
        for g, pct in r.get("group_distribution", {}).items():
            group_tot[g] += pct

    universal = [f for f, c in keep_counter.items() if c == n]
    always_zero = [f for f, c in zero_counter.items() if c == n]

    print(f"\n🏆 KEEP universali ({n}/{n}): {', '.join(sorted(universal)[:25]) or '(nessuna)'}")
    if always_zero:
        print(
            f"\n🗑️  ZERO ovunque (rimuovere da feature engineering): {', '.join(sorted(always_zero))}"
        )
    print(f"\n🏷️  GRUPPI (media su {n} modelli):")
    for g, tot in group_tot.most_common():
        avg = tot / n
        print(f"  {g:<14} {avg:>6.1f}%  {'█' * int(avg / 2)}")


def main():
    p = argparse.ArgumentParser(description="MANTIS SHAP feature analysis (v2)")
    p.add_argument(
        "--epic",
        type=str,
        default=None,
        help="Asset singolo (es. BTCUSD). Default: tutti.",
    )
    p.add_argument("--models-dir", type=str, default=str(DEFAULT_MODELS_DIR))
    p.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument(
        "--prune-threshold",
        type=float,
        default=0.85,
        help="Cumulativo importanza da tenere (0.85=85%%)",
    )
    p.add_argument("--corr-threshold", type=float, default=0.9, help="Soglia |corr| per ridondanza")
    p.add_argument("--n-samples", type=int, default=2000, help="Campioni recenti per SHAP")
    p.add_argument(
        "--lookback-days",
        type=int,
        default=365,
        help="Finestra storico per ricostruire le feature",
    )
    p.add_argument("--gain", action="store_true", help="Usa gain importance (no shap, no rebuild)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    np.random.seed(args.seed)
    models_dir = Path(args.models_dir)
    output_dir = Path(args.output_dir)

    print("🦗 MANTIS — SHAP Feature Analysis v2")
    print(f"   models:    {models_dir}")
    print(f"   output:    {output_dir}")
    print(f"   threshold: {int(args.prune_threshold*100)}% cumulative | corr>{args.corr_threshold}")
    print(f"   mode:      {'GAIN' if args.gain else 'SHAP'}")

    if not models_dir.exists():
        print(f"\n❌ models dir inesistente: {models_dir}")
        sys.exit(1)

    if args.epic:
        epics = [args.epic.upper()]
    else:
        epics = sorted(d.name for d in models_dir.iterdir() if d.is_dir())

    results: list[dict] = []
    for epic in epics:
        try:
            res = analyze_epic(
                epic=epic,
                models_dir=models_dir,
                output_dir=output_dir,
                prune_threshold=args.prune_threshold,
                corr_threshold=args.corr_threshold,
                n_samples=args.n_samples,
                lookback_days=args.lookback_days,
                use_gain=args.gain,
                quiet=args.quiet,
            )
            if res:
                results.append(res)
        except Exception as e:  # noqa: BLE001 - per-asset isolation
            print(f"\n❌ {epic}: {e}")
            import traceback

            traceback.print_exc()

    if len(results) >= 2:
        cross_asset_summary(results)

    if results:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "global_report.json").write_text(
            json.dumps(
                {
                    "n_models": len(results),
                    "models": [{k: v for k, v in r.items() if k != "ranking"} for r in results],
                },
                indent=2,
            )
        )
        print("\n💾 global_report.json")

    print(f"\n✅ Done → {output_dir}")


if __name__ == "__main__":
    main()
