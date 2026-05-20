"""
Phase 3-bis aggregator — consume `spread_audit.parquet`, produce
recalibration proposal + report for human review.

Mechanical-only: no LLM judgment, no auto-patch of `costs.py`. Produces:
- `docs/reports/2026-05-23_phase3-bis_spread_recalibration_PROPOSAL.md`
- `backend/src/backtest/costs.py.proposed` (side-by-side diff target)

Designed to be triggered by Windows Task Scheduler on 2026-05-23 after the
72h `spread_audit.py` run completes. Idempotent — re-running produces a
fresh report and overwrites the previous proposal.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/phase3_bis_aggregator.py
    .venv/Scripts/python.exe scripts/phase3_bis_aggregator.py --tradeable-only --min-samples 40
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.costs import ASSET_SPREADS  # noqa: E402
from src.utils.constants import TRADABLE_ASSETS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = REPO_ROOT / "data" / "diagnostics" / "spread_audit"
REPORTS_DIR = REPO_ROOT / "docs" / "reports"
COSTS_PATH = REPO_ROOT / "src" / "backtest" / "costs.py"


def _load_audit() -> pl.DataFrame:
    """Concat all monthly parquet partitions in spread_audit/."""
    files = sorted(AUDIT_DIR.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet partitions in {AUDIT_DIR}")
    dfs = [pl.read_parquet(f) for f in files]
    return pl.concat(dfs, how="vertical_relaxed")


def _aggregate(df: pl.DataFrame, tradeable_only: bool, min_samples: int) -> pl.DataFrame:
    """Compute per-epic p50/p95/max + proposed new spread (p95 × 1.1)."""
    if tradeable_only:
        df = df.filter(pl.col("market_status") == "TRADEABLE")
    agg = (
        df.group_by("epic")
        .agg([
            pl.len().alias("n_samples"),
            pl.col("spread").quantile(0.50).alias("p50_price"),
            pl.col("spread").quantile(0.95).alias("p95_price"),
            pl.col("spread").max().alias("max_price"),
            pl.col("spread_bps").quantile(0.50).alias("p50_bps"),
            pl.col("spread_bps").quantile(0.95).alias("p95_bps"),
            pl.col("spread_bps").max().alias("max_bps"),
            pl.col("asset_class").first().alias("asset_class"),
        ])
        .with_columns(
            (pl.col("p95_price") * 1.1).round(4).alias("proposed_new"),
        )
        .filter(pl.col("n_samples") >= min_samples)
        .sort("p95_bps", descending=True)
    )
    return agg


def _session_breakdown(df: pl.DataFrame) -> pl.DataFrame:
    """Per-epic spread breakdown by trading session (US/EU/Asia)."""
    df = df.filter(pl.col("market_status") == "TRADEABLE").with_columns(
        pl.col("ts_utc").dt.hour().alias("hour_utc"),
    ).with_columns(
        pl.when((pl.col("hour_utc") >= 13) & (pl.col("hour_utc") < 20))
        .then(pl.lit("US"))
        .when((pl.col("hour_utc") >= 6) & (pl.col("hour_utc") < 13))
        .then(pl.lit("EU"))
        .otherwise(pl.lit("Asia"))
        .alias("session"),
    )
    return (
        df.group_by(["epic", "session"])
        .agg([
            pl.col("spread_bps").quantile(0.95).round(2).alias("p95_bps"),
            pl.len().alias("n"),
        ])
        .pivot(values="p95_bps", index="epic", on="session", aggregate_function="first")
        .sort("epic")
    )


def _format_proposal_md(
    agg: pl.DataFrame,
    sessions: pl.DataFrame,
    df_raw: pl.DataFrame,
    args: argparse.Namespace,
) -> str:
    """Build the human-readable proposal report."""
    lines: list[str] = []
    lines.append("# Phase 3-bis — Spread Recalibration Proposal")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now(timezone.utc).isoformat()} UTC")
    lines.append(f"**Audit window**: {df_raw['ts_utc'].min()} → {df_raw['ts_utc'].max()}")
    lines.append(f"**Total observations**: {len(df_raw):,}")
    lines.append(f"**Filter**: tradeable_only={args.tradeable_only}, min_samples={args.min_samples}")
    lines.append("")
    lines.append("## Per-epic recalibration proposal")
    lines.append("")
    lines.append("| Epic | Class | n | p50 (price) | p95 (price) | max (price) | p95 bps | Current ASSET_SPREADS | **Proposed (p95×1.1)** | Δ |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in agg.iter_rows(named=True):
        epic = r["epic"]
        current = ASSET_SPREADS.get(epic, 0.5)
        proposed = r["proposed_new"]
        delta_pct = ((proposed - current) / current * 100.0) if current > 0 else float("nan")
        marker = " ⚠️" if abs(delta_pct) > 50 else ""
        lines.append(
            f"| {epic} | {r['asset_class']} | {r['n_samples']:,} | "
            f"{r['p50_price']:.4f} | {r['p95_price']:.4f} | {r['max_price']:.4f} | "
            f"{r['p95_bps']:.2f} | {current:.4f} | **{proposed:.4f}** | {delta_pct:+.1f}%{marker} |"
        )
    lines.append("")
    lines.append("Marker ⚠️ = |Δ| > 50% vs current — verify before applying.")
    lines.append("")
    lines.append("## Session breakdown (TRADEABLE only, p95 spread in bps)")
    lines.append("")
    cols = sessions.columns
    header = "| Epic | " + " | ".join(c for c in cols if c != "epic") + " |"
    sep = "|---|" + "|".join("---:" for c in cols if c != "epic") + "|"
    lines.append(header)
    lines.append(sep)
    for r in sessions.iter_rows(named=True):
        cells = []
        for c in cols:
            if c == "epic":
                continue
            v = r.get(c)
            cells.append(f"{v:.2f}" if isinstance(v, float) else "-")
        lines.append(f"| {r['epic']} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("US session = 13:00-20:00 UTC, EU = 06:00-13:00 UTC, Asia = 00:00-06:00 UTC.")
    lines.append("")
    lines.append("## Proposed `ASSET_SPREADS` dict (drop-in replacement)")
    lines.append("")
    lines.append("```python")
    lines.append("# Recalibrated 2026-05-23 from 72h passive `spread_audit.py` run.")
    lines.append("# p95 × 1.1 buffer (more aggressive than prior snap × 1.2 flat).")
    lines.append("ASSET_SPREADS = {")
    for r in agg.iter_rows(named=True):
        lines.append(f"    \"{r['epic']}\": {r['proposed_new']:.4f},  # n={r['n_samples']}, p95={r['p95_price']:.4f}")
    lines.append("}")
    lines.append("```")
    lines.append("")
    lines.append("## Required follow-up (manual, requires LLM judgment)")
    lines.append("")
    lines.append("1. Review proposed values, especially rows marked ⚠️.")
    lines.append("2. Apply patch: replace `ASSET_SPREADS` in `backend/src/backtest/costs.py`.")
    lines.append("3. Re-run Phase 3 backtest for each TRADABLE_ASSETS epic at 4h:")
    lines.append("   ```bash")
    lines.append("   cd backend")
    lines.append("   for epic in $(echo \"" + " ".join(TRADABLE_ASSETS) + "\"); do")
    lines.append("       .venv/Scripts/python.exe scripts/walk_forward_backtest.py \\")
    lines.append("           --epic $epic --timeframe 4h --capital 11000 --risk 0.02 \\")
    lines.append("           --tune --tune-trials 40 --monte-carlo")
    lines.append("   done")
    lines.append("   ```")
    lines.append("4. Verify Phase 0 gates (Sharpe ≥ 0.3, WR ≥ 40%, Max DD ≤ 30%) — exclude epics that fail by editing `_EXCLUDED_ASSETS` in `backend/src/utils/constants.py`.")
    lines.append("5. Re-verify Phase 4 BTC: same command, --epic BTCUSD --sweep-threshold.")
    lines.append("6. If KEEP basket survives + BTC still passes → authorize Binance Wave 2 (live testnet) per `docs/evolutive/BINANCE_MIGRATION_WAVE_PLAN.md`.")
    lines.append("7. Atomic commits:")
    lines.append("   - `feat(backtest): recalibrate ASSET_SPREADS from 72h live audit (Phase 3-bis)`")
    lines.append("   - `feat(phase0): exclude <epics> after Phase 3-bis cost re-run` (only if exclusions)")
    lines.append("   - `docs(phase3-bis): spread recalibration + Phase 3 re-run final report`")
    lines.append("")
    lines.append("## Artefacts")
    lines.append("")
    lines.append(f"- This proposal: `docs/reports/2026-05-23_phase3-bis_spread_recalibration_PROPOSAL.md`")
    lines.append(f"- Side-by-side patch target: `src/backtest/costs.py.proposed`")
    lines.append(f"- Raw audit data: `data/diagnostics/spread_audit/*.parquet`")
    lines.append("")
    return "\n".join(lines)


def _write_proposed_costs(agg: pl.DataFrame) -> Path:
    """Write a costs.py.proposed file alongside the current costs.py."""
    original = COSTS_PATH.read_text(encoding="utf-8")
    out_path = COSTS_PATH.with_suffix(".py.proposed")

    # Build the new ASSET_SPREADS block
    new_block_lines = [
        "# Recalibrated 2026-05-23 from 72h passive `spread_audit.py` run.",
        "# p95 × 1.1 buffer (more aggressive than prior snap × 1.2 flat).",
        "# Epics with <40 TRADEABLE samples retain their previous value (see PROPOSAL.md).",
        "ASSET_SPREADS = {",
    ]
    for r in agg.iter_rows(named=True):
        new_block_lines.append(
            f"    \"{r['epic']}\": {r['proposed_new']:.4f},  # n={r['n_samples']}"
        )
    # Add epics not in audit (fallback to current value)
    audit_epics = set(agg["epic"].to_list())
    for k, v in ASSET_SPREADS.items():
        if k not in audit_epics:
            new_block_lines.append(f"    \"{k}\": {v:.4f},  # retained from prior calibration (no fresh data)")
    new_block_lines.append("}")

    # Replace the existing ASSET_SPREADS block (between known markers)
    import re
    pattern = re.compile(
        r"# Capital\.com typical FULL bid-ask spreads.*?^\}\n",
        re.DOTALL | re.MULTILINE,
    )
    new_block_str = "\n".join(new_block_lines) + "\n"
    patched = pattern.sub(new_block_str, original, count=1)
    out_path.write_text(patched, encoding="utf-8")
    return out_path


def _notify(title: str, body: str) -> None:
    """Best-effort Windows toast notification. Silent on failure."""
    try:
        import subprocess
        ps_script = (
            f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, '
            f'ContentType = WindowsRuntime] | Out-Null; '
            f'$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; '
            f'$xml.LoadXml(\'<toast><visual><binding template="ToastGeneric"><text>{title}</text>'
            f'<text>{body}</text></binding></visual></toast>\'); '
            f'$t = New-Object Windows.UI.Notifications.ToastNotification $xml; '
            f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("MANTIS").Show($t)'
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            timeout=10, capture_output=True, text=True,
        )
    except Exception:
        pass  # notification is best-effort


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3-bis spread recalibration aggregator")
    parser.add_argument("--tradeable-only", action="store_true", default=True,
                        help="Filter to TRADEABLE market_status only (default true)")
    parser.add_argument("--min-samples", type=int, default=40,
                        help="Skip epics with fewer than N samples (default 40)")
    parser.add_argument("--out-report", type=Path, default=None)
    args = parser.parse_args()

    df = _load_audit()
    print(f"Loaded {len(df):,} observations from {AUDIT_DIR}")

    agg = _aggregate(df, args.tradeable_only, args.min_samples)
    print(f"Aggregated {len(agg)} epics with >= {args.min_samples} samples")

    sessions = _session_breakdown(df)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = args.out_report or (
        REPORTS_DIR / "2026-05-23_phase3-bis_spread_recalibration_PROPOSAL.md"
    )
    report_md = _format_proposal_md(agg, sessions, df, args)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"Wrote report: {report_path}")

    proposed_path = _write_proposed_costs(agg)
    print(f"Wrote proposed patch: {proposed_path}")

    _notify(
        "MANTIS Phase 3-bis ready",
        f"{len(agg)} epics recalibrated. Review {report_path.name}",
    )
    print("Done.")


if __name__ == "__main__":
    main()
