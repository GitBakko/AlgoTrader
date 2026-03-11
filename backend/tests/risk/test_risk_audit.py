"""Tests for risk check audit trail."""
import pytest
from src.risk.schemas import RiskCheckResult


def test_risk_check_result_has_audit_field():
    """RiskCheckResult should have an audit dict, empty by default."""
    result = RiskCheckResult(approved=True)
    assert isinstance(result.audit, dict)
    assert result.audit == {}


def test_risk_check_result_audit_survives_construction():
    """audit field should persist through normal construction."""
    result = RiskCheckResult(
        approved=True,
        audit={"circuit_breakers": {"passed": True}},
    )
    assert result.audit["circuit_breakers"]["passed"] is True


class TestRiskManagerAudit:
    """check_trade() should populate audit dict with each risk check."""

    def test_approved_trade_has_audit_keys(self):
        from src.risk.risk_manager import RiskManager
        from src.strategy.schemas import TradingSignal, SignalDirection

        rm = RiskManager(initial_equity=10000)
        signal = TradingSignal(
            epic="XAUUSD",
            direction=SignalDirection.BUY,
            confidence=0.67,
            signal_class=2,
            entry_price=2047.5,
            suggested_stop=2040.0,
            suggested_tp=2060.0,
        )
        result = rm.check_trade(signal, equity=10000, atr=16.8)
        assert result.approved is True
        assert "circuit_breakers" in result.audit
        assert "drawdown" in result.audit
        assert "stop_loss" in result.audit
        assert "correlation" in result.audit
        assert "sizing" in result.audit
        assert "confidence_tier" in result.audit

    def test_rejected_trade_has_partial_audit(self):
        from src.risk.risk_manager import RiskManager
        from src.strategy.schemas import TradingSignal, SignalDirection

        rm = RiskManager(initial_equity=10000)
        signal = TradingSignal(
            epic="XAUUSD",
            direction=SignalDirection.BUY,
            confidence=0.67,
            signal_class=2,
            entry_price=2047.5,
        )
        # Reject via invalid ATR
        result = rm.check_trade(signal, equity=10000, atr=0)
        assert result.approved is False
        # audit should still exist (may be empty for early rejections)
        assert isinstance(result.audit, dict)
