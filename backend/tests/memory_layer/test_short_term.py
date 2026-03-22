# MANTIS-EVOLUTION: Short Term Memory Tests
"""Tests for MantisShortTermMemory (TDD — written before implementation)."""
from __future__ import annotations

import math
import pickle
from datetime import datetime, timedelta, timezone

import pytest

from src.memory_layer.schemas import MemoryConfig, MemoryItem, TradeOutcome


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(epic: str = "XAUUSD", pnl_pct: float = 1.0) -> TradeOutcome:
    return TradeOutcome(
        trade_id=f"t-{epic}-{pnl_pct}",
        epic=epic,
        entry_price=1000.0,
        exit_price=1010.0,
        pnl_pct=pnl_pct,
    )


# ---------------------------------------------------------------------------
# Import (will fail until module exists)
# ---------------------------------------------------------------------------


from src.memory_layer.short_term import MantisShortTermMemory


# ---------------------------------------------------------------------------
# 1. Init
# ---------------------------------------------------------------------------


def test_init_defaults():
    """Empty STM has zero signals and trades."""
    stm = MantisShortTermMemory()
    assert stm.signal_count == 0
    assert stm.trade_count == 0


# ---------------------------------------------------------------------------
# 2. add_signal
# ---------------------------------------------------------------------------


def test_add_signal():
    """Adding a signal increments signal_count."""
    stm = MantisShortTermMemory()
    stm.add_signal("XAUUSD", "BUY", 0.75)
    assert stm.signal_count == 1


def test_add_signal_returns_id():
    """add_signal returns a non-empty string id."""
    stm = MantisShortTermMemory()
    item_id = stm.add_signal("BTCUSD", "SELL", 0.60)
    assert isinstance(item_id, str)
    assert len(item_id) > 0


def test_add_signal_with_metadata():
    """Metadata is merged into the stored item's data dict."""
    stm = MantisShortTermMemory()
    stm.add_signal("EURUSD", "BUY", 0.55, metadata={"strategy": "scalp"})
    items = stm.get_recent_signals(n=1)
    assert items[0].data.get("strategy") == "scalp"


# ---------------------------------------------------------------------------
# 3. add_trade_outcome
# ---------------------------------------------------------------------------


def test_add_trade_outcome():
    """Adding a trade outcome increments trade_count."""
    stm = MantisShortTermMemory()
    outcome = _make_outcome()
    stm.add_trade_outcome(outcome)
    assert stm.trade_count == 1


def test_add_trade_outcome_returns_id():
    """add_trade_outcome returns a non-empty string id."""
    stm = MantisShortTermMemory()
    item_id = stm.add_trade_outcome(_make_outcome())
    assert isinstance(item_id, str)
    assert len(item_id) > 0


# ---------------------------------------------------------------------------
# 4. Buffer overflow (circular)
# ---------------------------------------------------------------------------


def test_signal_buffer_overflow():
    """Adding more signals than max_signals drops the oldest."""
    config = MemoryConfig(stm_max_signals=3, stm_max_trades=5)
    stm = MantisShortTermMemory(config=config)
    for i in range(5):
        stm.add_signal("XAUUSD", "BUY", float(i) * 0.1)
    # Should only hold 3
    assert stm.signal_count == 3


def test_trade_buffer_overflow():
    """Adding more trades than max_trades drops the oldest."""
    config = MemoryConfig(stm_max_signals=5, stm_max_trades=2)
    stm = MantisShortTermMemory(config=config)
    for i in range(4):
        stm.add_trade_outcome(_make_outcome(pnl_pct=float(i)))
    assert stm.trade_count == 2


# ---------------------------------------------------------------------------
# 5. Retrieval
# ---------------------------------------------------------------------------


def test_get_recent_signals():
    """get_recent_signals returns at most N items."""
    stm = MantisShortTermMemory()
    for i in range(8):
        stm.add_signal("XAUUSD", "BUY", 0.5)
    result = stm.get_recent_signals(n=5)
    assert len(result) == 5


def test_get_recent_signals_returns_memory_items():
    """get_recent_signals returns MemoryItem instances."""
    stm = MantisShortTermMemory()
    stm.add_signal("XAUUSD", "BUY", 0.75)
    items = stm.get_recent_signals(n=1)
    assert len(items) == 1
    assert isinstance(items[0], MemoryItem)


def test_get_recent_trades():
    """get_recent_trades returns at most N items."""
    stm = MantisShortTermMemory()
    for i in range(6):
        stm.add_trade_outcome(_make_outcome())
    result = stm.get_recent_trades(n=3)
    assert len(result) == 3


def test_get_recent_context_mixed():
    """get_recent_context combines signals and trades, sorted by weight."""
    stm = MantisShortTermMemory()
    stm.add_signal("XAUUSD", "BUY", 0.8)
    stm.add_signal("BTCUSD", "SELL", 0.6)
    stm.add_trade_outcome(_make_outcome("XAUUSD", 1.5))
    result = stm.get_recent_context(n=10)
    # Should contain all 3 items (2 signals + 1 trade)
    assert len(result) == 3


def test_get_recent_context_respects_n():
    """get_recent_context returns at most N items."""
    stm = MantisShortTermMemory()
    for _ in range(5):
        stm.add_signal("XAUUSD", "BUY", 0.7)
    for _ in range(5):
        stm.add_trade_outcome(_make_outcome())
    result = stm.get_recent_context(n=4)
    assert len(result) == 4


# ---------------------------------------------------------------------------
# 6. Win rate
# ---------------------------------------------------------------------------


def test_win_rate_all_wins():
    """All profitable trades → win rate = 1.0."""
    stm = MantisShortTermMemory()
    for _ in range(5):
        stm.add_trade_outcome(_make_outcome(pnl_pct=1.0))
    assert stm.get_win_rate_recent(window_hours=24) == pytest.approx(1.0)


def test_win_rate_all_losses():
    """All losing trades → win rate = 0.0."""
    stm = MantisShortTermMemory()
    for _ in range(5):
        stm.add_trade_outcome(_make_outcome(pnl_pct=-1.0))
    assert stm.get_win_rate_recent(window_hours=24) == pytest.approx(0.0)


def test_win_rate_mixed():
    """6 wins + 4 losses → win rate ≈ 0.6."""
    stm = MantisShortTermMemory()
    for _ in range(6):
        stm.add_trade_outcome(_make_outcome(pnl_pct=2.0))
    for _ in range(4):
        stm.add_trade_outcome(_make_outcome(pnl_pct=-1.0))
    rate = stm.get_win_rate_recent(window_hours=24)
    assert rate == pytest.approx(0.6)


def test_win_rate_no_trades():
    """No trades → default 0.5."""
    stm = MantisShortTermMemory()
    assert stm.get_win_rate_recent() == pytest.approx(0.5)


def test_win_rate_window_excludes_old_trades():
    """Trades outside the window_hours are excluded from win rate."""
    stm = MantisShortTermMemory()
    # One old winning trade (2 hours ago — inside 3h window)
    outcome_recent = _make_outcome(pnl_pct=2.0)
    item_id = stm.add_trade_outcome(outcome_recent)
    # One very old winning trade (48h ago — outside 3h window)
    outcome_old = _make_outcome(pnl_pct=-5.0)
    stm.add_trade_outcome(outcome_old)
    # Manually backdate the old trade
    for item in stm._trades:
        if item.data.get("pnl_pct") == -5.0:
            item.timestamp = datetime.now(timezone.utc) - timedelta(hours=48)

    rate = stm.get_win_rate_recent(window_hours=3)
    # Only recent (1 win / 1 total) should count
    assert rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 7. Decay
# ---------------------------------------------------------------------------


def test_decay_reduces_weight():
    """Items added hours ago have lower weight than brand-new items."""
    stm = MantisShortTermMemory()
    stm.add_signal("XAUUSD", "BUY", 0.7)
    # Backdate the single item to 10 hours ago
    for item in stm._signals:
        item.timestamp = datetime.now(timezone.utc) - timedelta(hours=10)

    stm.add_signal("BTCUSD", "SELL", 0.8)  # brand new

    stm._apply_decay()
    weights = [item.weight for item in stm._signals]
    # New item should have higher weight than the old one
    assert max(weights) > min(weights)


def test_decay_formula():
    """weight ≈ e^(-λ * age_hours) for λ=0.1, age=7h → ≈0.4966."""
    config = MemoryConfig(decay_lambda=0.1)
    stm = MantisShortTermMemory(config=config)
    stm.add_signal("XAUUSD", "BUY", 0.7)
    for item in stm._signals:
        item.timestamp = datetime.now(timezone.utc) - timedelta(hours=7)

    stm._apply_decay()
    item = list(stm._signals)[0]
    expected = math.exp(-0.1 * 7)
    assert item.weight == pytest.approx(expected, abs=0.01)


def test_decay_brand_new_item_weight_near_one():
    """A brand-new item should have weight very close to 1.0 after decay."""
    stm = MantisShortTermMemory()
    stm.add_signal("XAUUSD", "BUY", 0.7)
    stm._apply_decay()
    item = list(stm._signals)[0]
    assert item.weight == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# 8. Clear
# ---------------------------------------------------------------------------


def test_clear():
    """clear() empties both signal and trade buffers."""
    stm = MantisShortTermMemory()
    stm.add_signal("XAUUSD", "BUY", 0.8)
    stm.add_trade_outcome(_make_outcome())
    stm.clear()
    assert stm.signal_count == 0
    assert stm.trade_count == 0


# ---------------------------------------------------------------------------
# 9. Persistence
# ---------------------------------------------------------------------------


def test_save_load_snapshot(tmp_path):
    """save_snapshot → load_snapshot preserves data."""
    stm = MantisShortTermMemory()
    stm.add_signal("XAUUSD", "BUY", 0.8)
    stm.add_signal("BTCUSD", "SELL", 0.6)
    stm.add_trade_outcome(_make_outcome("XAUUSD", 2.0))

    snapshot_file = tmp_path / "stm_test.pkl"
    result = stm.save_snapshot(path=snapshot_file)
    assert result is True

    stm2 = MantisShortTermMemory()
    loaded = stm2.load_snapshot(path=snapshot_file)
    assert loaded is True
    assert stm2.signal_count == 2
    assert stm2.trade_count == 1


def test_load_nonexistent_returns_false(tmp_path):
    """Loading from a missing file returns False."""
    stm = MantisShortTermMemory()
    result = stm.load_snapshot(path=tmp_path / "no_such_file.pkl")
    assert result is False


def test_save_snapshot_returns_true(tmp_path):
    """save_snapshot returns True on success."""
    stm = MantisShortTermMemory()
    stm.add_signal("XAUUSD", "BUY", 0.7)
    assert stm.save_snapshot(path=tmp_path / "snap.pkl") is True


def test_save_load_preserves_trade_data(tmp_path):
    """Trade pnl_pct is preserved across save/load."""
    stm = MantisShortTermMemory()
    stm.add_trade_outcome(_make_outcome("XAUUSD", pnl_pct=3.14))
    path = tmp_path / "stm2.pkl"
    stm.save_snapshot(path=path)

    stm2 = MantisShortTermMemory()
    stm2.load_snapshot(path=path)
    item = list(stm2._trades)[0]
    assert item.data.get("pnl_pct") == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# 10. Custom config
# ---------------------------------------------------------------------------


def test_custom_config():
    """Custom max_signals and decay_lambda are respected."""
    config = MemoryConfig(stm_max_signals=5, stm_max_trades=3, decay_lambda=0.5)
    stm = MantisShortTermMemory(config=config)
    assert stm.config.stm_max_signals == 5
    assert stm.config.stm_max_trades == 3
    assert stm.config.decay_lambda == pytest.approx(0.5)
    # Overflow check
    for _ in range(7):
        stm.add_signal("XAUUSD", "BUY", 0.7)
    assert stm.signal_count == 5


def test_custom_decay_lambda_faster_decay():
    """Higher λ produces faster decay (lower weight at same age)."""
    slow_config = MemoryConfig(decay_lambda=0.01)
    fast_config = MemoryConfig(decay_lambda=1.0)

    stm_slow = MantisShortTermMemory(config=slow_config)
    stm_fast = MantisShortTermMemory(config=fast_config)

    for stm in (stm_slow, stm_fast):
        stm.add_signal("XAUUSD", "BUY", 0.7)
        for item in stm._signals:
            item.timestamp = datetime.now(timezone.utc) - timedelta(hours=5)
        stm._apply_decay()

    w_slow = list(stm_slow._signals)[0].weight
    w_fast = list(stm_fast._signals)[0].weight
    assert w_fast < w_slow
