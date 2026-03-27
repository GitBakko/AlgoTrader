"""
Walk-forward OOS scorecard: per-asset decision framework.

Collects walk-forward backtest results and applies a multi-criteria
decision framework to classify assets as KEEP / REVIEW / EXCLUDE
for live trading.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class WalkForwardResult:
    """Aggregated out-of-sample metrics from walk-forward backtest."""

    epic: str
    n_folds: int
    sharpe: float
    sortino: float
    max_drawdown: float  # as positive fraction (e.g. 0.15 = 15%)
    win_rate: float  # 0.0 - 1.0
    profit_factor: float
    total_trades: int
    total_return_pct: float  # e.g. 12.5 for +12.5%
    best_confidence_threshold: float
    avg_oos_f1: float  # average F1 across OOS folds
    mc_p_value: float = 0.0  # Monte Carlo sign-flip test
    mc_risk_of_ruin: float = 0.0  # Monte Carlo permutation


# Criteria thresholds: one failure -> REVIEW, 3+ -> EXCLUDE
_CRITERIA = {
    "sharpe_min": 0.3,
    "win_rate_min": 0.40,
    "max_drawdown_max": 0.30,
    "mc_p_value_max": 0.10,
    "mc_risk_of_ruin_max": 0.15,
    "total_trades_min": 20,
}


def _evaluate_criteria(r: WalkForwardResult) -> list[str]:
    """Return list of failed criteria names."""
    failed: list[str] = []
    if r.sharpe < _CRITERIA["sharpe_min"]:
        failed.append(f"sharpe {r.sharpe:.2f} < {_CRITERIA['sharpe_min']}")
    if r.win_rate < _CRITERIA["win_rate_min"]:
        failed.append(f"win_rate {r.win_rate:.1%} < {_CRITERIA['win_rate_min']:.0%}")
    if r.max_drawdown > _CRITERIA["max_drawdown_max"]:
        failed.append(f"max_dd {r.max_drawdown:.1%} > {_CRITERIA['max_drawdown_max']:.0%}")
    if r.mc_p_value > _CRITERIA["mc_p_value_max"]:
        failed.append(f"mc_pval {r.mc_p_value:.3f} > {_CRITERIA['mc_p_value_max']}")
    if r.mc_risk_of_ruin > _CRITERIA["mc_risk_of_ruin_max"]:
        failed.append(f"mc_ruin {r.mc_risk_of_ruin:.1%} > {_CRITERIA['mc_risk_of_ruin_max']:.0%}")
    if r.total_trades < _CRITERIA["total_trades_min"]:
        failed.append(f"trades {r.total_trades} < {_CRITERIA['total_trades_min']}")
    return failed


@dataclass
class AssetScorecard:
    """Per-asset decision after walk-forward evaluation."""

    result: WalkForwardResult
    decision: str = ""  # KEEP | REVIEW | EXCLUDE
    failed_criteria: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.failed_criteria:
            self.failed_criteria = _evaluate_criteria(self.result)
        if not self.decision:
            n_failed = len(self.failed_criteria)
            if n_failed == 0:
                self.decision = "KEEP"
            elif n_failed < 3:
                self.decision = "REVIEW"
            else:
                self.decision = "EXCLUDE"


def build_scorecards(results: list[WalkForwardResult]) -> list[AssetScorecard]:
    """Build scorecards for a batch of walk-forward results."""
    return [AssetScorecard(result=r) for r in results]


def save_optimal_thresholds(
    scorecards: list[AssetScorecard],
    output_path: Path,
    default_confidence: float = 0.40,
) -> None:
    """
    Save per-asset optimal confidence thresholds to JSON.

    Format:
        {
            "generated_at": "2026-02-18T10:00:00Z",
            "default_confidence": 0.40,
            "per_asset": {
                "XAUUSD": {"min_confidence": 0.42, "decision": "KEEP", "sharpe": 0.82},
                ...
            }
        }
    """
    per_asset = {}
    for sc in scorecards:
        r = sc.result
        per_asset[r.epic] = {
            "min_confidence": round(r.best_confidence_threshold, 3),
            "decision": sc.decision,
            "sharpe": round(r.sharpe, 3),
            "sortino": round(r.sortino, 3),
            "win_rate": round(r.win_rate, 3),
            "max_drawdown": round(r.max_drawdown, 3),
            "profit_factor": round(r.profit_factor, 3),
            "total_trades": r.total_trades,
            "total_return_pct": round(r.total_return_pct, 2),
            "failed_criteria": sc.failed_criteria,
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "default_confidence": default_confidence,
        "per_asset": per_asset,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_optimal_thresholds(path: Path) -> dict | None:
    """
    Load optimal thresholds from JSON file.

    Returns:
        Parsed dict or None if file doesn't exist.
    """
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def format_scorecard_table(scorecards: list[AssetScorecard]) -> str:
    """Format scorecards as a human-readable console table."""
    lines = []
    header = (
        f"{'Epic':<10} {'Decision':<8} {'Sharpe':>7} {'Sortino':>8} "
        f"{'WinRate':>8} {'MaxDD':>7} {'PF':>6} {'Trades':>7} "
        f"{'Return%':>8} {'Thresh':>7} {'Failed'}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for sc in sorted(scorecards, key=lambda s: s.result.sharpe, reverse=True):
        r = sc.result
        failed_str = "; ".join(sc.failed_criteria) if sc.failed_criteria else "-"
        line = (
            f"{r.epic:<10} {sc.decision:<8} {r.sharpe:>7.2f} {r.sortino:>8.2f} "
            f"{r.win_rate:>7.1%} {r.max_drawdown:>6.1%} {r.profit_factor:>6.2f} "
            f"{r.total_trades:>7} {r.total_return_pct:>7.1f}% "
            f"{r.best_confidence_threshold:>7.2f} {failed_str}"
        )
        lines.append(line)

    return "\n".join(lines)
