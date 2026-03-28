"""Tests for ExtendedDataProvider — no external API calls (all mocked)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import polars as pl
import pytest

from src.data.extended_data_provider import ExtendedDataProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_yfinance_df() -> pd.DataFrame:
    """Create a minimal pandas DataFrame that mimics yfinance output."""
    idx = pd.to_datetime(
        ["2024-01-01 08:00:00", "2024-01-01 09:00:00", "2024-01-01 10:00:00"],
        utc=True,
    )
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [105.0, 106.0, 107.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [103.0, 104.0, 105.0],
            "Volume": [1000, 1100, 1200],
        },
        index=idx,
    )
    df.index.name = "Datetime"
    return df


def _make_yfinance_multilevel_df() -> pd.DataFrame:
    """Create a yfinance DataFrame with multi-level columns (as yfinance sometimes returns)."""
    idx = pd.to_datetime(["2024-01-01 08:00:00", "2024-01-01 09:00:00"], utc=True)
    cols = pd.MultiIndex.from_tuples(
        [("Open", "TSLA"), ("High", "TSLA"), ("Low", "TSLA"), ("Close", "TSLA"), ("Volume", "TSLA")]
    )
    df = pd.DataFrame(
        [[100.0, 105.0, 99.0, 103.0, 1000], [101.0, 106.0, 100.0, 104.0, 1100]],
        index=idx,
        columns=cols,
    )
    df.index.name = "Datetime"
    return df


def _make_cryptocompare_response() -> dict:
    """Create a minimal CryptoCompare API JSON response."""
    return {
        "Response": "Success",
        "Data": {
            "Data": [
                {
                    "time": 1704067200,  # 2024-01-01 00:00:00 UTC
                    "open": 42000.0,
                    "high": 43000.0,
                    "low": 41500.0,
                    "close": 42500.0,
                    "volumefrom": 500.0,
                    "volumeto": 21250000.0,
                },
                {
                    "time": 1704070800,  # 2024-01-01 01:00:00 UTC
                    "open": 42500.0,
                    "high": 43500.0,
                    "low": 42000.0,
                    "close": 43000.0,
                    "volumefrom": 600.0,
                    "volumeto": 25800000.0,
                },
            ]
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNormalizeYfinance:
    def test_columns_present(self):
        provider = ExtendedDataProvider()
        df_pd = _make_yfinance_df()
        result = provider._normalize_yfinance(df_pd, "XAUUSD")

        assert isinstance(result, pl.DataFrame)
        for col in ("timestamp", "open", "high", "low", "close", "volume", "epic"):
            assert col in result.columns, f"Missing column: {col}"

    def test_epic_column_value(self):
        provider = ExtendedDataProvider()
        df_pd = _make_yfinance_df()
        result = provider._normalize_yfinance(df_pd, "TSLA")
        assert result["epic"].to_list() == ["TSLA", "TSLA", "TSLA"]

    def test_row_count(self):
        provider = ExtendedDataProvider()
        df_pd = _make_yfinance_df()
        result = provider._normalize_yfinance(df_pd, "XAUUSD")
        assert len(result) == 3

    def test_multilevel_columns_flattened(self):
        provider = ExtendedDataProvider()
        df_pd = _make_yfinance_multilevel_df()
        result = provider._normalize_yfinance(df_pd, "TSLA")
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        assert "open" in result.columns

    def test_timestamp_is_utc(self):
        provider = ExtendedDataProvider()
        df_pd = _make_yfinance_df()
        result = provider._normalize_yfinance(df_pd, "XAUUSD")
        ts_col = result["timestamp"]
        # Polars stores datetime with time_zone info
        assert ts_col.dtype == pl.Datetime("us", "UTC") or "UTC" in str(ts_col.dtype)

    def test_ohlcv_values(self):
        provider = ExtendedDataProvider()
        df_pd = _make_yfinance_df()
        result = provider._normalize_yfinance(df_pd, "XAUUSD")
        row0 = result.row(0, named=True)
        assert row0["open"] == pytest.approx(100.0)
        assert row0["high"] == pytest.approx(105.0)
        assert row0["low"] == pytest.approx(99.0)
        assert row0["close"] == pytest.approx(103.0)
        assert row0["volume"] == pytest.approx(1000.0)


class TestNormalizeCryptoCompare:
    def test_columns_present(self):
        provider = ExtendedDataProvider()
        raw = _make_cryptocompare_response()
        result = provider._normalize_cryptocompare(raw, "BTCUSD")

        assert isinstance(result, pl.DataFrame)
        for col in ("timestamp", "open", "high", "low", "close", "volume", "epic"):
            assert col in result.columns, f"Missing column: {col}"

    def test_epic_column_value(self):
        provider = ExtendedDataProvider()
        raw = _make_cryptocompare_response()
        result = provider._normalize_cryptocompare(raw, "BTCUSD")
        assert result["epic"].to_list() == ["BTCUSD", "BTCUSD"]

    def test_row_count(self):
        provider = ExtendedDataProvider()
        raw = _make_cryptocompare_response()
        result = provider._normalize_cryptocompare(raw, "BTCUSD")
        assert len(result) == 2

    def test_timestamp_is_utc(self):
        provider = ExtendedDataProvider()
        raw = _make_cryptocompare_response()
        result = provider._normalize_cryptocompare(raw, "BTCUSD")
        ts_col = result["timestamp"]
        assert "UTC" in str(ts_col.dtype)

    def test_timestamp_value(self):
        provider = ExtendedDataProvider()
        raw = _make_cryptocompare_response()
        result = provider._normalize_cryptocompare(raw, "BTCUSD")
        expected_ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        first_ts = result["timestamp"][0].replace(tzinfo=timezone.utc)
        assert first_ts == expected_ts

    def test_ohlcv_values(self):
        provider = ExtendedDataProvider()
        raw = _make_cryptocompare_response()
        result = provider._normalize_cryptocompare(raw, "BTCUSD")
        row0 = result.row(0, named=True)
        assert row0["open"] == pytest.approx(42000.0)
        assert row0["high"] == pytest.approx(43000.0)
        assert row0["low"] == pytest.approx(41500.0)
        assert row0["close"] == pytest.approx(42500.0)
        assert row0["volume"] == pytest.approx(500.0)

    def test_empty_data_returns_empty_df(self):
        provider = ExtendedDataProvider()
        raw = {"Response": "Success", "Data": {"Data": []}}
        result = provider._normalize_cryptocompare(raw, "BTCUSD")
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0

    def test_error_response_returns_empty_df(self):
        provider = ExtendedDataProvider()
        raw = {"Response": "Error", "Message": "Not found"}
        result = provider._normalize_cryptocompare(raw, "BTCUSD")
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0


class TestMergeWithExisting:
    def _make_polars_df(self, timestamps: list[str], epic: str = "XAUUSD") -> pl.DataFrame:
        ts_list = [
            datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
            for t in timestamps
        ]
        return pl.DataFrame(
            {
                "timestamp": ts_list,
                "open": [100.0] * len(ts_list),
                "high": [105.0] * len(ts_list),
                "low": [99.0] * len(ts_list),
                "close": [103.0] * len(ts_list),
                "volume": [1000.0] * len(ts_list),
                "epic": [epic] * len(ts_list),
            }
        ).with_columns(pl.col("timestamp").dt.replace_time_zone("UTC"))

    def test_deduplication(self):
        provider = ExtendedDataProvider()
        existing = self._make_polars_df(["2024-01-01T08:00:00", "2024-01-01T09:00:00"])
        extended = self._make_polars_df(["2024-01-01T09:00:00", "2024-01-01T10:00:00"])
        merged = provider.merge_with_existing(existing, extended)
        # Should have 3 unique timestamps, not 4
        assert len(merged) == 3

    def test_sorted_by_timestamp(self):
        provider = ExtendedDataProvider()
        existing = self._make_polars_df(["2024-01-01T10:00:00", "2024-01-01T08:00:00"])
        extended = self._make_polars_df(["2024-01-01T09:00:00"])
        merged = provider.merge_with_existing(existing, extended)
        ts_list = merged["timestamp"].to_list()
        assert ts_list == sorted(ts_list)

    def test_empty_existing(self):
        provider = ExtendedDataProvider()
        schema = {
            "timestamp": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "epic": pl.Utf8,
        }
        existing = pl.DataFrame(schema=schema)
        extended = self._make_polars_df(["2024-01-01T08:00:00", "2024-01-01T09:00:00"])
        merged = provider.merge_with_existing(existing, extended)
        assert len(merged) == 2

    def test_empty_extended(self):
        provider = ExtendedDataProvider()
        existing = self._make_polars_df(["2024-01-01T08:00:00"])
        schema = {
            "timestamp": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "epic": pl.Utf8,
        }
        extended = pl.DataFrame(schema=schema)
        merged = provider.merge_with_existing(existing, extended)
        assert len(merged) == 1

    def test_all_columns_preserved(self):
        provider = ExtendedDataProvider()
        existing = self._make_polars_df(["2024-01-01T08:00:00"])
        extended = self._make_polars_df(["2024-01-01T09:00:00"])
        merged = provider.merge_with_existing(existing, extended)
        for col in ("timestamp", "open", "high", "low", "close", "volume", "epic"):
            assert col in merged.columns


class TestGetBestSource:
    def test_crypto_uses_cryptocompare(self):
        provider = ExtendedDataProvider()
        assert provider.get_best_source("BTCUSD") == "cryptocompare"
        assert provider.get_best_source("ETHUSD") == "cryptocompare"
        assert provider.get_best_source("SOLUSD") == "cryptocompare"
        assert provider.get_best_source("BNBUSD") == "cryptocompare"
        assert provider.get_best_source("DOGUSD") == "cryptocompare"
        assert provider.get_best_source("DASHUSD") == "cryptocompare"
        assert provider.get_best_source("ICPUSD") == "cryptocompare"

    def test_forex_uses_yfinance(self):
        provider = ExtendedDataProvider()
        assert provider.get_best_source("EURUSD") == "yfinance"
        assert provider.get_best_source("GBPUSD") == "yfinance"
        assert provider.get_best_source("USDJPY") == "yfinance"

    def test_commodities_use_yfinance(self):
        provider = ExtendedDataProvider()
        assert provider.get_best_source("XAUUSD") == "yfinance"
        assert provider.get_best_source("XAGUSD") == "yfinance"
        assert provider.get_best_source("WTIUSD") == "yfinance"

    def test_indices_use_yfinance(self):
        provider = ExtendedDataProvider()
        assert provider.get_best_source("US500") == "yfinance"
        assert provider.get_best_source("NAS100") == "yfinance"
        assert provider.get_best_source("DE40") == "yfinance"

    def test_stocks_use_yfinance(self):
        provider = ExtendedDataProvider()
        assert provider.get_best_source("NVDA") == "yfinance"
        assert provider.get_best_source("TSLA") == "yfinance"

    def test_unknown_falls_back_to_yfinance(self):
        provider = ExtendedDataProvider()
        assert provider.get_best_source("UNKNOWN") == "yfinance"


class TestFetchYfinanceAsync:
    @pytest.mark.asyncio
    async def test_fetch_yfinance_calls_ticker(self):
        """fetch_yfinance should call yf.Ticker().history() in a thread."""
        provider = ExtendedDataProvider()
        df_pd = _make_yfinance_df()

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df_pd

        with patch("src.data.extended_data_provider.yf.Ticker", return_value=mock_ticker):
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 1, 2, tzinfo=timezone.utc)
            result = await provider.fetch_yfinance("XAUUSD", start, end)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
        mock_ticker.history.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_yfinance_unknown_epic_returns_empty(self):
        """fetch_yfinance should return an empty DataFrame for unmapped epics."""
        provider = ExtendedDataProvider()
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)
        result = await provider.fetch_yfinance("UNKNOWN_EPIC", start, end)
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0


class TestFetchCryptoCompareAsync:
    @pytest.mark.asyncio
    async def test_fetch_cryptocompare_calls_api(self):
        """fetch_cryptocompare should make an HTTP request to CryptoCompare."""
        provider = ExtendedDataProvider()
        raw = _make_cryptocompare_response()

        mock_response = MagicMock()
        mock_response.json.return_value = raw
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.data.extended_data_provider.httpx.AsyncClient", return_value=mock_client):
            result = await provider.fetch_cryptocompare("BTCUSD", limit=2)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_fetch_cryptocompare_unknown_epic_returns_empty(self):
        """fetch_cryptocompare should return empty df for non-crypto epics."""
        provider = ExtendedDataProvider()
        result = await provider.fetch_cryptocompare("XAUUSD")
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0


class TestFetchExtended:
    @pytest.mark.asyncio
    async def test_fetch_extended_uses_cryptocompare_for_crypto(self):
        provider = ExtendedDataProvider()
        raw = _make_cryptocompare_response()

        mock_response = MagicMock()
        mock_response.json.return_value = raw
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)

        with patch("src.data.extended_data_provider.httpx.AsyncClient", return_value=mock_client):
            result = await provider.fetch_extended("BTCUSD", start, end)

        assert isinstance(result, pl.DataFrame)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_fetch_extended_uses_yfinance_for_non_crypto(self):
        provider = ExtendedDataProvider()
        df_pd = _make_yfinance_df()

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df_pd

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)

        with patch("src.data.extended_data_provider.yf.Ticker", return_value=mock_ticker):
            result = await provider.fetch_extended("XAUUSD", start, end)

        assert isinstance(result, pl.DataFrame)
        assert len(result) == 3
