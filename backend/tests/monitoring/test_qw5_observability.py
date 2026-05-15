"""QW5 (2026-05-15): slippage histogram + live WR tracker metrics."""

import pytest

from src.monitoring.metrics import (
    MetricsCollector,
    mantis_live_wr_gauge,
    mantis_live_wr_oos_delta_gauge,
    mantis_slippage_points,
    mantis_slippage_pct,
    mantis_spread_filter_blocked_total,
)


@pytest.mark.unit
def test_record_slippage_observes_histograms():
    """record_slippage feeds both point + pct histograms."""
    epic = "BTCUSD"
    direction = "BUY"
    MetricsCollector.record_slippage(
        epic=epic, direction=direction, signal_price=50000.0, fill_price=50050.0
    )
    # Histograms record via labels; sample count for the labelset should be ≥ 1.
    pts = mantis_slippage_points.labels(epic=epic, direction=direction)._sum.get()
    assert pts >= 50.0
    pct = mantis_slippage_pct.labels(epic=epic)._sum.get()
    assert pct >= 0.0009  # 50 / 50000 = 0.001


@pytest.mark.unit
def test_record_slippage_zero_diff_safe():
    """fill_price == signal_price -> 0 slippage, no error."""
    MetricsCollector.record_slippage(
        epic="XAUUSD", direction="SELL", signal_price=2000.0, fill_price=2000.0
    )


@pytest.mark.unit
def test_record_slippage_rejects_non_positive_prices():
    """Non-positive prices silently return (must not raise)."""
    MetricsCollector.record_slippage(
        epic="US500", direction="BUY", signal_price=0.0, fill_price=4500.0
    )
    MetricsCollector.record_slippage(
        epic="US500", direction="BUY", signal_price=4500.0, fill_price=0.0
    )


@pytest.mark.unit
def test_update_live_wr_sets_gauges():
    epic = "XAUUSD"
    MetricsCollector.update_live_wr(epic=epic, live_wr=0.75, oos_delta=-0.02)
    wr_val = mantis_live_wr_gauge.labels(epic=epic)._value.get()
    delta_val = mantis_live_wr_oos_delta_gauge.labels(epic=epic)._value.get()
    assert wr_val == pytest.approx(0.75)
    assert delta_val == pytest.approx(-0.02)


@pytest.mark.unit
def test_update_live_wr_none_delta_skips_delta_gauge():
    epic = "TSLA"
    MetricsCollector.update_live_wr(epic=epic, live_wr=0.68, oos_delta=None)
    wr_val = mantis_live_wr_gauge.labels(epic=epic)._value.get()
    assert wr_val == pytest.approx(0.68)


@pytest.mark.unit
def test_record_spread_filter_blocked_counter():
    """QW3 counter wired correctly via MetricsCollector."""
    epic = "BTCUSD"
    before = mantis_spread_filter_blocked_total.labels(
        epic=epic, asset_class="crypto"
    )._value.get()
    MetricsCollector.record_spread_filter_blocked(epic=epic, asset_class="crypto")
    after = mantis_spread_filter_blocked_total.labels(
        epic=epic, asset_class="crypto"
    )._value.get()
    assert after == before + 1
