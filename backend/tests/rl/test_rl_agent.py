# MANTIS-EVOLUTION: RL Agent Tests
"""Tests for MantisRLAgent — all SB3 model calls are mocked (not installed)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.agents.schemas import AgentRole, MarketContext
from src.rl.schemas import RLAction, RLSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_context(**overrides) -> MarketContext:
    """Build a minimal MarketContext for testing."""
    defaults = dict(
        epic="XAUUSD",
        current_price=2000.0,
        atr=5.0,
        features={
            "ema_9": 2000.0,
            "ema_21": 1995.0,
            "rsi_14": 55.0,
            "adx_14": 30.0,
            "macd_histogram": 0.5,
            "bb_upper": 2020.0,
            "bb_lower": 1980.0,
            "bb_middle": 2000.0,
            "volume": 1000.0,
            "volume_sma": 900.0,
            "vwap": 1998.0,
        },
    )
    defaults.update(overrides)
    return MarketContext(**defaults)


def make_trainer_with_model(action_value: int) -> MagicMock:
    """Build a mock MantisAdaptiveTrainer that returns the given action."""
    model = MagicMock()
    model.predict.return_value = (np.array(action_value), None)

    trainer = MagicMock()
    trainer.get_current_model.return_value = model
    trainer.current_model_version = "20260322_120000"
    trainer.config.algorithm = "PPO"
    return trainer


def make_trainer_no_model() -> MagicMock:
    """Build a mock trainer that has no model loaded."""
    trainer = MagicMock()
    trainer.get_current_model.return_value = None
    trainer.current_model_version = ""
    trainer.config.algorithm = "PPO"
    return trainer


# ---------------------------------------------------------------------------
# Imports under test (deferred so we can patch before import if needed)
# ---------------------------------------------------------------------------


from src.rl.rl_agent import MantisRLAgent  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Role attribute
# ---------------------------------------------------------------------------


def test_role_is_rl_adaptive():
    """MantisRLAgent.role must equal AgentRole.RL_ADAPTIVE."""
    assert MantisRLAgent.role == AgentRole.RL_ADAPTIVE


# ---------------------------------------------------------------------------
# 2. No trainer → None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_no_trainer():
    """analyze() with trainer=None must return None immediately."""
    agent = MantisRLAgent(trainer=None)
    result = await agent.analyze(make_context())
    assert result is None


# ---------------------------------------------------------------------------
# 3. Trainer present but no model → None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_no_model():
    """analyze() when trainer has no model yet must return None."""
    trainer = make_trainer_no_model()
    agent = MantisRLAgent(trainer=trainer)
    result = await agent.analyze(make_context())
    assert result is None


# ---------------------------------------------------------------------------
# 4. Predict BUY (LONG_ENTRY = 0)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_predicts_buy():
    """LONG_ENTRY (0) → RLSignal.action == 'BUY'."""
    trainer = make_trainer_with_model(RLAction.LONG_ENTRY)
    agent = MantisRLAgent(trainer=trainer)
    result = await agent.analyze(make_context())

    assert result is not None
    assert isinstance(result, RLSignal)
    assert result.action == "BUY"
    assert result.raw_action == int(RLAction.LONG_ENTRY)


# ---------------------------------------------------------------------------
# 5. Predict SELL (SHORT_ENTRY = 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_predicts_sell():
    """SHORT_ENTRY (2) → RLSignal.action == 'SELL'."""
    trainer = make_trainer_with_model(RLAction.SHORT_ENTRY)
    agent = MantisRLAgent(trainer=trainer)
    result = await agent.analyze(make_context())

    assert result is not None
    assert result.action == "SELL"
    assert result.raw_action == int(RLAction.SHORT_ENTRY)


# ---------------------------------------------------------------------------
# 6. Predict HOLD (NEUTRAL = 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_predicts_hold():
    """NEUTRAL (4) → RLSignal.action == 'HOLD'."""
    trainer = make_trainer_with_model(RLAction.NEUTRAL)
    agent = MantisRLAgent(trainer=trainer)
    result = await agent.analyze(make_context())

    assert result is not None
    assert result.action == "HOLD"


# ---------------------------------------------------------------------------
# 7. EXIT actions also map to HOLD for signal generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_long_exit_maps_to_hold():
    """LONG_EXIT (1) → 'HOLD' for signal generation."""
    trainer = make_trainer_with_model(RLAction.LONG_EXIT)
    agent = MantisRLAgent(trainer=trainer)
    result = await agent.analyze(make_context())
    assert result is not None
    assert result.action == "HOLD"


@pytest.mark.asyncio
async def test_analyze_short_exit_maps_to_hold():
    """SHORT_EXIT (3) → 'HOLD' for signal generation."""
    trainer = make_trainer_with_model(RLAction.SHORT_EXIT)
    agent = MantisRLAgent(trainer=trainer)
    result = await agent.analyze(make_context())
    assert result is not None
    assert result.action == "HOLD"


# ---------------------------------------------------------------------------
# 8. Entry actions have higher confidence than hold/neutral
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confidence_entry_higher():
    """Entry action confidence must exceed neutral confidence."""
    ctx = make_context()

    buy_trainer = make_trainer_with_model(RLAction.LONG_ENTRY)
    buy_agent = MantisRLAgent(trainer=buy_trainer)
    buy_result = await buy_agent.analyze(ctx)

    neutral_trainer = make_trainer_with_model(RLAction.NEUTRAL)
    neutral_agent = MantisRLAgent(trainer=neutral_trainer)
    neutral_result = await neutral_agent.analyze(ctx)

    assert buy_result is not None
    assert neutral_result is not None
    assert buy_result.confidence > neutral_result.confidence


# ---------------------------------------------------------------------------
# 9. model.predict raises → None (no crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_failure_returns_none():
    """If model.predict raises an exception, analyze() must return None."""
    model = MagicMock()
    model.predict.side_effect = RuntimeError("SB3 error")

    trainer = MagicMock()
    trainer.get_current_model.return_value = model
    trainer.current_model_version = "broken"
    trainer.config.algorithm = "PPO"

    agent = MantisRLAgent(trainer=trainer)
    result = await agent.analyze(make_context())
    assert result is None


# ---------------------------------------------------------------------------
# 10. RLSignal fields are populated correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rl_signal_fields_populated():
    """RLSignal must carry model_version and algorithm from the trainer."""
    trainer = make_trainer_with_model(RLAction.LONG_ENTRY)
    trainer.current_model_version = "v1_test"
    trainer.config.algorithm = "SAC"

    agent = MantisRLAgent(trainer=trainer)
    result = await agent.analyze(make_context())

    assert result is not None
    assert result.model_version == "v1_test"
    assert result.algorithm == "SAC"
    assert 0.0 <= result.confidence <= 1.0
