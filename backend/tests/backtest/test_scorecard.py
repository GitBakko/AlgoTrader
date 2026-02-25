"""
Tests for the walk-forward OOS scorecard module and StrategyManager.from_optimal_thresholds().
"""

import json
from pathlib import Path

import pytest

from src.backtest.scorecard import (
    AssetScorecard,
    WalkForwardResult,
    build_scorecards,
    format_scorecard_table,
    load_optimal_thresholds,
    save_optimal_thresholds,
)
from src.strategy.strategy_manager import StrategyManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _good_result(epic: str = "XAUUSD") -> WalkForwardResult:
    """A result that passes all criteria → KEEP."""
    return WalkForwardResult(
        epic=epic,
        n_folds=5,
        sharpe=0.85,
        sortino=1.2,
        max_drawdown=0.12,
        win_rate=0.52,
        profit_factor=1.4,
        total_trades=80,
        total_return_pct=15.0,
        best_confidence_threshold=0.42,
        avg_oos_f1=0.56,
        mc_p_value=0.02,
        mc_risk_of_ruin=0.05,
    )


def _borderline_result(epic: str = "BTCUSD") -> WalkForwardResult:
    """A result that fails 1-2 criteria → REVIEW."""
    return WalkForwardResult(
        epic=epic,
        n_folds=5,
        sharpe=0.25,        # < 0.3 → FAIL
        sortino=0.3,
        max_drawdown=0.18,
        win_rate=0.45,
        profit_factor=1.1,
        total_trades=50,
        total_return_pct=5.0,
        best_confidence_threshold=0.45,
        avg_oos_f1=0.48,
        mc_p_value=0.04,
        mc_risk_of_ruin=0.08,
    )


def _bad_result(epic: str = "DOGUSD") -> WalkForwardResult:
    """A result that fails 3+ criteria → EXCLUDE."""
    return WalkForwardResult(
        epic=epic,
        n_folds=5,
        sharpe=-0.10,       # FAIL
        sortino=-0.2,
        max_drawdown=0.45,  # FAIL
        win_rate=0.30,      # FAIL
        profit_factor=0.6,
        total_trades=15,    # FAIL
        total_return_pct=-8.0,
        best_confidence_threshold=0.50,
        avg_oos_f1=0.35,
        mc_p_value=0.25,    # FAIL
        mc_risk_of_ruin=0.30,  # FAIL
    )


# ===========================================================================
# AssetScorecard decision tests
# ===========================================================================

class TestAssetScorecardDecision:
    """Test the multi-criteria decision framework."""

    def test_keep_decision_no_failures(self):
        """Asset with all criteria passing gets KEEP."""
        sc = AssetScorecard(result=_good_result())
        assert sc.decision == "KEEP"
        assert sc.failed_criteria == []

    def test_review_decision_one_failure(self):
        """Asset with 1 failure gets REVIEW."""
        sc = AssetScorecard(result=_borderline_result())
        assert sc.decision == "REVIEW"
        assert 1 <= len(sc.failed_criteria) <= 2

    def test_exclude_decision_three_or_more_failures(self):
        """Asset with 3+ failures gets EXCLUDE."""
        sc = AssetScorecard(result=_bad_result())
        assert sc.decision == "EXCLUDE"
        assert len(sc.failed_criteria) >= 3

    def test_failed_criteria_contain_specific_checks(self):
        """Verify specific criteria are checked."""
        sc = AssetScorecard(result=_bad_result())
        criteria_text = " ".join(sc.failed_criteria)
        assert "sharpe" in criteria_text
        assert "win_rate" in criteria_text
        assert "max_dd" in criteria_text


class TestBuildScorecards:
    """Test batch scorecard construction."""

    def test_builds_correct_count(self):
        results = [_good_result("XAUUSD"), _borderline_result("BTCUSD"), _bad_result("DOGUSD")]
        scorecards = build_scorecards(results)
        assert len(scorecards) == 3

    def test_decisions_distributed(self):
        results = [_good_result("XAUUSD"), _borderline_result("BTCUSD"), _bad_result("DOGUSD")]
        scorecards = build_scorecards(results)
        decisions = {sc.result.epic: sc.decision for sc in scorecards}
        assert decisions["XAUUSD"] == "KEEP"
        assert decisions["BTCUSD"] == "REVIEW"
        assert decisions["DOGUSD"] == "EXCLUDE"


# ===========================================================================
# Save/Load optimal thresholds
# ===========================================================================

class TestOptimalThresholds:
    """Test save/load of optimal_thresholds.json."""

    def test_save_and_load(self, tmp_path: Path):
        """Round-trip: save → load → verify."""
        scorecards = build_scorecards([
            _good_result("XAUUSD"),
            _borderline_result("BTCUSD"),
            _bad_result("DOGUSD"),
        ])
        out = tmp_path / "optimal_thresholds.json"
        save_optimal_thresholds(scorecards, out, default_confidence=0.40)

        assert out.exists()
        data = load_optimal_thresholds(out)
        assert data is not None
        assert data["default_confidence"] == 0.40
        assert "generated_at" in data
        assert "XAUUSD" in data["per_asset"]
        assert data["per_asset"]["XAUUSD"]["decision"] == "KEEP"
        assert data["per_asset"]["XAUUSD"]["min_confidence"] == 0.42
        assert data["per_asset"]["DOGUSD"]["decision"] == "EXCLUDE"

    def test_load_missing_file(self, tmp_path: Path):
        """load_optimal_thresholds returns None for missing file."""
        result = load_optimal_thresholds(tmp_path / "nonexistent.json")
        assert result is None

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        """save_optimal_thresholds creates missing parent directories."""
        out = tmp_path / "nested" / "deep" / "thresholds.json"
        scorecards = build_scorecards([_good_result()])
        save_optimal_thresholds(scorecards, out)
        assert out.exists()


# ===========================================================================
# StrategyManager.from_optimal_thresholds()
# ===========================================================================

class TestStrategyManagerFromThresholds:
    """Test StrategyManager loading per-asset thresholds."""

    def test_loads_thresholds_from_file(self, tmp_path: Path):
        """from_optimal_thresholds creates configs with per-asset min_confidence."""
        scorecards = build_scorecards([
            _good_result("XAUUSD"),
            _borderline_result("BTCUSD"),
            _bad_result("DOGUSD"),
        ])
        out = tmp_path / "thresholds.json"
        save_optimal_thresholds(scorecards, out)

        sm = StrategyManager.from_optimal_thresholds(path=out)

        # XAUUSD: KEEP → config loaded
        config_xau = sm._get_config("XAUUSD")
        assert config_xau.min_confidence == pytest.approx(0.42)

        # BTCUSD: REVIEW → config loaded
        config_btc = sm._get_config("BTCUSD")
        assert config_btc.min_confidence == pytest.approx(0.45)

        # DOGUSD: EXCLUDE → in excluded set
        assert "DOGUSD" in sm.excluded_epics

    def test_missing_file_uses_defaults(self, tmp_path: Path):
        """When file doesn't exist, fallback to default config."""
        sm = StrategyManager.from_optimal_thresholds(
            path=tmp_path / "missing.json"
        )
        assert sm._configs == {}
        assert sm.excluded_epics == set()

        # Default config should be generated on access
        config = sm._get_config("XAUUSD")
        assert config.min_confidence == pytest.approx(0.50)


# ===========================================================================
# Format table
# ===========================================================================

class TestFormatTable:
    """Test console table formatting."""

    def test_format_includes_all_epics(self):
        scorecards = build_scorecards([
            _good_result("XAUUSD"),
            _borderline_result("BTCUSD"),
        ])
        table = format_scorecard_table(scorecards)
        assert "XAUUSD" in table
        assert "BTCUSD" in table
        assert "KEEP" in table
        assert "REVIEW" in table
