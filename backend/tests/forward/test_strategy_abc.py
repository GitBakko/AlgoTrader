import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from src.broker.models import Direction


def test_forward_strategy_is_abstract():
    from forward.strategy import ForwardStrategy
    with pytest.raises(TypeError):
        ForwardStrategy()  # abstract: cannot instantiate


def test_signal_and_context_construct():
    from forward.strategy import Signal, MarketContext, OpenPosition
    ctx = MarketContext(epic="AAPL", prev_close=100.0, today_open=103.0,
                        current_price=103.0, now=datetime.now(timezone.utc),
                        session_close=datetime.now(timezone.utc))
    assert ctx.gap == pytest.approx(0.03)
    sig = Signal(epic="AAPL", direction=Direction.SELL, stop_level=105.0, rationale="x")
    assert sig.direction == Direction.SELL
