"""Tests for EconomicCalendarGate."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.external.sil_schemas import CalendarEvent
from src.risk.economic_calendar_gate import (
    EPIC_CURRENCIES,
    EconomicCalendarGate,
)


@pytest.fixture
def gate():
    with patch("src.risk.economic_calendar_gate.get_settings") as mock_settings:
        mock_settings.return_value.sil_calendar_gate_enabled = True
        mock_settings.return_value.sil_calendar_minutes_before = 30
        mock_settings.return_value.sil_calendar_minutes_after = 15
        mock_settings.return_value.finnhub_api_key = "test_key"
        g = EconomicCalendarGate()
    return g


@pytest.fixture
def gate_disabled():
    with patch("src.risk.economic_calendar_gate.get_settings") as mock_settings:
        mock_settings.return_value.sil_calendar_gate_enabled = False
        g = EconomicCalendarGate()
    return g


def _nfp_event(hour: int = 13, minute: int = 30) -> CalendarEvent:
    """Create a NFP event at given time today."""
    now = datetime.now(timezone.utc)
    event_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return CalendarEvent(
        event="US Non-Farm Payrolls",
        country="US",
        currency="USD",
        impact="high",
        event_time=event_time,
    )


def _ecb_event(hour: int = 12, minute: int = 45) -> CalendarEvent:
    """Create an ECB Rate Decision event."""
    now = datetime.now(timezone.utc)
    event_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return CalendarEvent(
        event="ECB Interest Rate Decision",
        country="EU",
        currency="EUR",
        impact="high",
        event_time=event_time,
    )


def _low_impact_event() -> CalendarEvent:
    now = datetime.now(timezone.utc)
    return CalendarEvent(
        event="US Redbook Index",
        country="US",
        currency="USD",
        impact="low",
        event_time=now.replace(hour=14, minute=0),
    )


class TestEconomicCalendarGateBlackout:
    @pytest.mark.asyncio
    async def test_disabled_gate_never_blocks(self, gate_disabled):
        """Gate disabled → always returns (False, '')."""
        result = await gate_disabled.is_blackout("XAUUSD")
        assert result == (False, "")

    @pytest.mark.asyncio
    async def test_blackout_during_nfp_window(self, gate):
        """30 min before NFP → blackout for gold."""
        nfp = _nfp_event(hour=13, minute=30)
        gate._events_cache = [nfp]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 15 minutes before event → in blackout
        now = nfp.event_time - timedelta(minutes=15)
        is_blackout, reason = await gate.is_blackout("XAUUSD", now=now)
        assert is_blackout is True
        assert "Non-Farm Payrolls" in reason

    @pytest.mark.asyncio
    async def test_no_blackout_after_window(self, gate):
        """20 minutes after NFP → no blackout (window is +15min)."""
        nfp = _nfp_event(hour=13, minute=30)
        gate._events_cache = [nfp]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        now = nfp.event_time + timedelta(minutes=20)
        is_blackout, _ = await gate.is_blackout("XAUUSD", now=now)
        assert is_blackout is False

    @pytest.mark.asyncio
    async def test_no_blackout_well_before_window(self, gate):
        """2 hours before NFP → no blackout (window is -30min)."""
        nfp = _nfp_event(hour=13, minute=30)
        gate._events_cache = [nfp]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        now = nfp.event_time - timedelta(hours=2)
        is_blackout, _ = await gate.is_blackout("XAUUSD", now=now)
        assert is_blackout is False

    @pytest.mark.asyncio
    async def test_ecb_blocks_eurusd(self, gate):
        """ECB event blocks EURUSD."""
        ecb = _ecb_event(hour=12, minute=45)
        gate._events_cache = [ecb]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        now = ecb.event_time - timedelta(minutes=10)
        is_blackout, reason = await gate.is_blackout("EURUSD", now=now)
        assert is_blackout is True
        assert "ECB" in reason

    @pytest.mark.asyncio
    async def test_ecb_blocks_de40(self, gate):
        """ECB event blocks DE40 (EUR sensitivity)."""
        ecb = _ecb_event(hour=12, minute=45)
        gate._events_cache = [ecb]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        now = ecb.event_time - timedelta(minutes=10)
        is_blackout, _ = await gate.is_blackout("DE40", now=now)
        assert is_blackout is True

    @pytest.mark.asyncio
    async def test_ecb_does_not_block_xauusd(self, gate):
        """ECB event does NOT block gold (USD only)."""
        ecb = _ecb_event(hour=12, minute=45)
        gate._events_cache = [ecb]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        now = ecb.event_time - timedelta(minutes=10)
        is_blackout, _ = await gate.is_blackout("XAUUSD", now=now)
        assert is_blackout is False

    @pytest.mark.asyncio
    async def test_crypto_only_blocked_by_major_events(self, gate):
        """BTCUSD only blocked by Fed/CPI, not NFP."""
        nfp = _nfp_event(hour=13, minute=30)
        gate._events_cache = [nfp]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        now = nfp.event_time - timedelta(minutes=10)
        is_blackout, _ = await gate.is_blackout("BTCUSD", now=now)
        # NFP is NOT in USD_MAJOR set → no blackout for crypto
        assert is_blackout is False

    @pytest.mark.asyncio
    async def test_crypto_blocked_by_fomc(self, gate):
        """BTCUSD IS blocked by FOMC (in USD_MAJOR set)."""
        now_utc = datetime.now(timezone.utc)
        fomc = CalendarEvent(
            event="Fed Rate Decision",
            country="US",
            currency="USD",
            impact="high",
            event_time=now_utc.replace(hour=18, minute=0, second=0),
        )
        gate._events_cache = [fomc]
        gate._cache_date = now_utc.strftime("%Y-%m-%d")

        now = fomc.event_time - timedelta(minutes=10)
        is_blackout, reason = await gate.is_blackout("BTCUSD", now=now)
        assert is_blackout is True
        assert "Fed Rate Decision" in reason

    @pytest.mark.asyncio
    async def test_low_impact_event_no_blackout(self, gate):
        """Low-impact event → no blackout."""
        event = _low_impact_event()
        gate._events_cache = [event]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        now = event.event_time - timedelta(minutes=5)
        is_blackout, _ = await gate.is_blackout("XAUUSD", now=now)
        assert is_blackout is False

    @pytest.mark.asyncio
    async def test_no_events_no_blackout(self, gate):
        """Empty calendar → no blackout."""
        gate._events_cache = []
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        is_blackout, _ = await gate.is_blackout("XAUUSD")
        assert is_blackout is False

    @pytest.mark.asyncio
    async def test_unknown_epic_no_blackout(self, gate):
        """Unknown epic → no blackout."""
        nfp = _nfp_event()
        gate._events_cache = [nfp]
        gate._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        now = nfp.event_time - timedelta(minutes=10)
        is_blackout, _ = await gate.is_blackout("UNKNOWN_EPIC", now=now)
        assert is_blackout is False


class TestHighImpactDetection:
    def test_nfp_is_high_impact(self):
        assert EconomicCalendarGate._is_high_impact("US Non-Farm Payrolls")

    def test_cpi_is_high_impact(self):
        assert EconomicCalendarGate._is_high_impact("US Core CPI m/m")

    def test_fomc_is_high_impact(self):
        assert EconomicCalendarGate._is_high_impact("FOMC Meeting Minutes")

    def test_gdp_is_high_impact(self):
        assert EconomicCalendarGate._is_high_impact("US GDP q/q")

    def test_redbook_is_not_high_impact(self):
        assert not EconomicCalendarGate._is_high_impact("US Redbook Index")

    def test_empty_string(self):
        assert not EconomicCalendarGate._is_high_impact("")


class TestEpicCurrencyMapping:
    def test_all_21_epics_mapped(self):
        """All 21 MANTIS assets have currency sensitivity."""
        assets = [
            "XAUUSD", "BTCUSD", "US500", "WTIUSD", "EURUSD",
            "NVDA", "TSLA", "XAGUSD", "DE40", "SOLUSD",
            "ETHUSD", "BNBUSD", "DOGUSD", "DASHUSD", "ICPUSD",
            "NATGAS", "COPPER", "PLATINUM", "GBPUSD", "USDJPY", "NAS100",
        ]
        for epic in assets:
            assert epic in EPIC_CURRENCIES, f"Missing: {epic}"

    def test_crypto_uses_usd_major(self):
        for epic in ["BTCUSD", "ETHUSD", "SOLUSD"]:
            assert "USD_MAJOR" in EPIC_CURRENCIES[epic]
