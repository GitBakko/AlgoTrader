"""Phase 1 expansion (2026-05-23): pin new RiskLimits defaults so
schema changes are visible in code review."""

from src.risk.schemas import RiskLimits


def test_default_max_position_pct_is_010() -> None:
    """Per-position cap halved 0.20 → 0.10 to keep 100 % gross at 10 slots."""
    assert RiskLimits().max_position_pct == 0.10


def test_default_max_total_open_positions_is_10() -> None:
    """Concurrent slot cap raised 5 → 10 for 19-asset basket diversification."""
    assert RiskLimits().max_total_open_positions == 10


def test_max_correlated_exposure_field_removed() -> None:
    """Dead config — was declared but never enforced in risk_manager.py.

    Removed to avoid confusion; dynamic correlation matrix multiplier
    enforces equivalent intent.
    """
    assert "max_correlated_exposure" not in RiskLimits.model_fields


def test_default_max_total_exposure_unchanged() -> None:
    """Total-exposure cap default unchanged at 1.0 — guard fix in
    risk_manager.py activates enforcement at this default."""
    assert RiskLimits().max_total_exposure == 1.0


def test_default_max_risk_per_trade_unchanged() -> None:
    """Per-trade risk cap untouched by Phase 1 expansion."""
    assert RiskLimits().max_risk_per_trade == 0.02


# --- Phase 1 expansion: dynamic correlation settings ---


def test_dynamic_correlation_enabled_default_true() -> None:
    """Independent of CORRELATION_REGIME_ENABLED (Phase 2 regime gate)."""
    from src.utils.config import Settings

    assert Settings().dynamic_correlation_enabled is True


def test_dynamic_correlation_bootstrap_min_assets_default_5() -> None:
    """Need >=5 epics with data to compute a meaningful NxN matrix."""
    from src.utils.config import Settings

    assert Settings().dynamic_correlation_bootstrap_min_assets == 5
