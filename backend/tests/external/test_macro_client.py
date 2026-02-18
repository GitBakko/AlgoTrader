"""Tests for MacroDataClient."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from src.external.macro_client import MACRO_TICKERS, MacroDataClient


def _make_mock_macro_df() -> pl.DataFrame:
    """Create a sample macro DataFrame for testing."""
    import numpy as np
    dates = pl.date_range(
        datetime(2025, 1, 1), datetime(2025, 6, 30), "1d", eager=True
    )
    n = len(dates)
    rng = np.random.default_rng(42)
    return pl.DataFrame({
        "date": dates,
        "vix_close": rng.uniform(15, 30, n),
        "vix_change_5d": rng.uniform(-0.1, 0.1, n),
        "dxy_close": rng.uniform(100, 110, n),
        "dxy_change_5d": rng.uniform(-0.02, 0.02, n),
        "yield_10y_close": rng.uniform(3.5, 5.0, n),
        "yield_10y_change_5d": rng.uniform(-0.05, 0.05, n),
    })


class TestMacroDataClient:
    """Test MacroDataClient initialization and caching."""

    def test_init_creates_cache_dir(self, tmp_path):
        """Cache directory is created on init."""
        cache_dir = tmp_path / "macro_cache"
        client = MacroDataClient(cache_dir=cache_dir)
        assert cache_dir.exists()

    def test_empty_macro_df_schema(self, tmp_path):
        """Empty DataFrame has the expected columns."""
        client = MacroDataClient(cache_dir=tmp_path)
        empty = client._empty_macro_df()
        expected_cols = {"date", "vix_close", "vix_change_5d", "dxy_close",
                         "dxy_change_5d", "yield_10y_close", "yield_10y_change_5d"}
        assert set(empty.columns) == expected_cols
        assert len(empty) == 0

    def test_get_macro_data_returns_expected_columns(self, tmp_path):
        """When cache exists, returns DataFrame with correct columns."""
        client = MacroDataClient(cache_dir=tmp_path)
        mock_df = _make_mock_macro_df()
        mock_df.write_parquet(client._cache_file)

        result = client.get_macro_data()
        assert "vix_close" in result.columns
        assert "dxy_close" in result.columns
        assert "yield_10y_close" in result.columns
        assert len(result) > 0

    def test_caching_reads_from_parquet(self, tmp_path):
        """Second call uses cached parquet, not yfinance."""
        client = MacroDataClient(cache_dir=tmp_path)
        mock_df = _make_mock_macro_df()
        mock_df.write_parquet(client._cache_file)

        with patch.object(client, "_download_macro_data") as mock_dl:
            result = client.get_macro_data()
            mock_dl.assert_not_called()

        assert len(result) > 0

    def test_filter_dates(self, tmp_path):
        """Date filtering works correctly."""
        client = MacroDataClient(cache_dir=tmp_path)
        df = _make_mock_macro_df()

        start = datetime(2025, 3, 1)
        end = datetime(2025, 4, 30)
        filtered = client._filter_dates(df, start, end)
        assert len(filtered) < len(df)
        assert filtered["date"].min() >= start.date()
        assert filtered["date"].max() <= end.date()

    def test_graceful_degradation_no_yfinance(self, tmp_path):
        """Returns empty DataFrame if yfinance is not available."""
        client = MacroDataClient(cache_dir=tmp_path)

        with patch.dict("sys.modules", {"yfinance": None}):
            with patch.object(client, "_download_macro_data", return_value=client._empty_macro_df()):
                result = client.get_macro_data(force_refresh=True)
                assert len(result) == 0
                assert "vix_close" in result.columns

    def test_macro_tickers_defined(self):
        """All expected macro tickers are defined."""
        assert "vix" in MACRO_TICKERS
        assert "dxy" in MACRO_TICKERS
        assert "yield_10y" in MACRO_TICKERS
