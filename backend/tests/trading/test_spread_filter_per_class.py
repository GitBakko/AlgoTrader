"""QW3 (2026-05-15): per-asset-class spread filter."""

import pytest

from src.trading.paper_loop import (
    _CRYPTO_EPICS,
    _PRECIOUS_EPICS,
    get_spread_limit,
)


@pytest.mark.unit
def test_get_spread_limit_crypto_tier():
    """Crypto epics use the wider 15% bucket."""
    limit, cls = get_spread_limit("BTCUSD")
    assert cls == "crypto"
    assert limit == pytest.approx(0.15)
    for e in ["ETHUSD", "BNBUSD", "SOLUSD", "DOGUSD"]:
        assert e in _CRYPTO_EPICS, f"{e} should be in crypto tier"
        l2, c2 = get_spread_limit(e)
        assert c2 == "crypto"
        assert l2 == pytest.approx(0.15)


@pytest.mark.unit
def test_get_spread_limit_precious_tier():
    """Precious metals get the 12% bucket."""
    for e in ["XAUUSD", "XAGUSD", "PLATINUM"]:
        assert e in _PRECIOUS_EPICS
        limit, cls = get_spread_limit(e)
        assert cls == "precious"
        assert limit == pytest.approx(0.12)


@pytest.mark.unit
def test_get_spread_limit_default_tier():
    """All non-crypto / non-precious assets get the tight 8% bucket."""
    for e in ["US500", "META", "TSLA", "NVDA", "DE40", "WTIUSD", "USDJPY", "NATGAS"]:
        assert e not in _CRYPTO_EPICS
        assert e not in _PRECIOUS_EPICS
        limit, cls = get_spread_limit(e)
        assert cls == "default"
        assert limit == pytest.approx(0.08)


@pytest.mark.unit
@pytest.mark.parametrize(
    "epic,spread_ratio,should_block",
    [
        ("BTCUSD", 0.14, False),  # crypto, just under 15% limit
        ("BTCUSD", 0.16, True),  # crypto, just over
        ("XAUUSD", 0.11, False),  # precious, just under 12%
        ("XAUUSD", 0.13, True),  # precious, just over
        ("US500", 0.07, False),  # default, just under 8%
        ("US500", 0.09, True),  # default, just over
        ("META", 0.075, False),  # default boundary case
        ("ETHUSD", 0.149, False),  # crypto right at edge
        ("PLATINUM", 0.121, True),  # precious right over edge
    ],
)
def test_spread_ratio_vs_class_limit(epic, spread_ratio, should_block):
    """Verify the comparison `spread_ratio > limit` matches expected gating."""
    limit, _cls = get_spread_limit(epic)
    blocked = spread_ratio > limit
    assert blocked is should_block, (
        f"{epic} ratio={spread_ratio} vs limit={limit} -> blocked={blocked} "
        f"(expected {should_block})"
    )
