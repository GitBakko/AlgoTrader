"""Tests for COTClient (Commitment of Traders)."""

from unittest.mock import MagicMock, patch

import pytest

from src.external.cot_client import COTClient, EPIC_TO_CONTRACT


@pytest.fixture
def client():
    with patch("src.external.sil_base_client.get_settings") as mock_settings:
        mock_settings.return_value.sil_cache_ttl_minutes = 60
        c = COTClient(cache_ttl_minutes=10080)
    return c


def _mock_cot_response(rows: list[list]) -> dict:
    return {"dataset": {"data": rows}}


def _setup_mock_client(client, response_json: dict):
    mock_http = MagicMock()
    mock_http.is_closed = False

    async def mock_get(url, params=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = response_json
        return resp

    mock_http.get = mock_get
    client._client = mock_http


class TestCOTClientFetch:
    @pytest.mark.asyncio
    async def test_unsupported_epic_returns_default(self, client):
        """Epic without COT mapping → default COTData."""
        result = await client.fetch("SOLUSD")
        assert result.net_position == 0
        assert result.is_institutional_bullish is False

    @pytest.mark.asyncio
    async def test_bullish_positioning(self, client):
        """More longs than shorts → bullish."""
        rows = [
            ["2026-03-04", 250000, 150000],
            ["2026-02-25", 240000, 155000],
            ["2026-02-18", 230000, 160000],
            ["2026-02-11", 220000, 165000],
        ]
        _setup_mock_client(client, _mock_cot_response(rows))
        result = await client.fetch("XAUUSD")
        assert result.noncomm_long == 250000
        assert result.noncomm_short == 150000
        assert result.net_position == 100000
        assert result.is_institutional_bullish is True
        assert result.net_position_normalized > 0

    @pytest.mark.asyncio
    async def test_bearish_positioning(self, client):
        """More shorts than longs → bearish."""
        rows = [
            ["2026-03-04", 100000, 200000],
            ["2026-02-25", 110000, 190000],
        ]
        _setup_mock_client(client, _mock_cot_response(rows))
        result = await client.fetch("EURUSD")
        assert result.net_position < 0
        assert result.is_institutional_bullish is False
        assert result.net_position_normalized < 0

    @pytest.mark.asyncio
    async def test_z_score_positive_when_above_mean(self, client):
        """Current net much higher than recent → positive z-score."""
        rows = [
            ["2026-03-04", 300000, 100000],  # Net = 200k
            ["2026-02-25", 200000, 150000],  # Net = 50k
            ["2026-02-18", 180000, 160000],  # Net = 20k
            ["2026-02-11", 170000, 165000],  # Net = 5k
        ]
        _setup_mock_client(client, _mock_cot_response(rows))
        result = await client.fetch("XAUUSD")
        assert result.z_score_4w > 1.0

    @pytest.mark.asyncio
    async def test_empty_data_returns_default(self, client):
        """No data rows → default COTData."""
        _setup_mock_client(client, _mock_cot_response([]))
        result = await client.fetch("WTIUSD")
        assert result.net_position == 0

    @pytest.mark.asyncio
    async def test_cache_hit(self, client):
        rows = [["2026-03-04", 200000, 150000]]
        _setup_mock_client(client, _mock_cot_response(rows))
        first = await client.fetch("XAUUSD")
        # Change mock
        _setup_mock_client(client, _mock_cot_response([["2026-03-04", 100, 200]]))
        second = await client.fetch("XAUUSD")
        assert second.net_position == first.net_position

    @pytest.mark.asyncio
    async def test_report_date_parsed(self, client):
        rows = [["2026-03-04", 200000, 150000]]
        _setup_mock_client(client, _mock_cot_response(rows))
        result = await client.fetch("GBPUSD")
        assert result.report_date is not None
        assert result.report_date.year == 2026


class TestCOTClientZScore:
    def test_z_score_single_value(self):
        assert COTClient._compute_z_score([100]) == 0.0

    def test_z_score_identical_values(self):
        assert COTClient._compute_z_score([50, 50, 50]) == 0.0

    def test_z_score_positive(self):
        z = COTClient._compute_z_score([100, 50, 50, 50])
        assert z > 0

    def test_z_score_negative(self):
        z = COTClient._compute_z_score([0, 50, 50, 50])
        assert z < 0


class TestCOTClientEpicMap:
    def test_gold_mapped(self):
        assert "XAUUSD" in EPIC_TO_CONTRACT

    def test_bitcoin_mapped(self):
        assert "BTCUSD" in EPIC_TO_CONTRACT

    def test_supported_epics(self):
        epics = COTClient.supported_epics()
        assert "XAUUSD" in epics
        assert len(epics) == 11

    def test_crypto_not_all_mapped(self):
        """Not all crypto has COT (only BTC on CME)."""
        assert "SOLUSD" not in EPIC_TO_CONTRACT
        assert "ETHUSD" not in EPIC_TO_CONTRACT
