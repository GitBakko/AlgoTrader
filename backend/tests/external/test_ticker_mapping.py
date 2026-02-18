"""Tests for ticker_mapping module."""

import pytest

from src.external.ticker_mapping import (
    EPIC_TO_FINNHUB,
    EPIC_TO_FINNHUB_CRYPTO,
    EPIC_TO_NEWS_QUERY,
    get_all_news_queries,
    get_finnhub_ticker,
    get_news_query,
    supports_equity_features,
)
from src.utils.constants import TRADABLE_ASSETS


class TestTickerMapping:
    """Test epic-to-external-API mappings."""

    def test_all_tradable_assets_have_news_query(self):
        """Every tradable asset must have a news query for sentiment."""
        for epic in TRADABLE_ASSETS:
            assert epic in EPIC_TO_NEWS_QUERY, f"{epic} missing from EPIC_TO_NEWS_QUERY"
            assert len(EPIC_TO_NEWS_QUERY[epic]) > 0

    def test_all_tradable_assets_in_finnhub_map(self):
        """Every tradable asset must be in the Finnhub mapping (even if None)."""
        for epic in TRADABLE_ASSETS:
            assert epic in EPIC_TO_FINNHUB, f"{epic} missing from EPIC_TO_FINNHUB"

    def test_stock_assets_support_equity_features(self):
        """NVDA and TSLA should support equity features."""
        assert supports_equity_features("NVDA") is True
        assert supports_equity_features("TSLA") is True

    def test_non_stocks_dont_support_equity_features(self):
        """Crypto, forex, commodities, indices should NOT support equity features."""
        non_stocks = ["BTCUSD", "ETHUSD", "EURUSD", "XAUUSD", "US500", "NAS100",
                      "SOLUSD", "NATGAS", "COPPER", "GBPUSD"]
        for epic in non_stocks:
            assert supports_equity_features(epic) is False, f"{epic} should not support equity"

    def test_get_finnhub_ticker_stocks(self):
        """Stocks return their ticker symbol."""
        assert get_finnhub_ticker("NVDA") == "NVDA"
        assert get_finnhub_ticker("TSLA") == "TSLA"

    def test_get_finnhub_ticker_non_stocks(self):
        """Non-stocks return None."""
        assert get_finnhub_ticker("BTCUSD") is None
        assert get_finnhub_ticker("XAUUSD") is None
        assert get_finnhub_ticker("US500") is None

    def test_get_finnhub_ticker_unknown(self):
        """Unknown epic returns None."""
        assert get_finnhub_ticker("UNKNOWN") is None

    def test_get_news_query(self):
        """News queries contain relevant keywords."""
        assert "gold" in get_news_query("XAUUSD").lower()
        assert "bitcoin" in get_news_query("BTCUSD").lower()
        assert "nasdaq" in get_news_query("NAS100").lower()

    def test_get_news_query_unknown(self):
        """Unknown epic returns None."""
        assert get_news_query("UNKNOWN") is None

    def test_get_all_news_queries(self):
        """get_all_news_queries returns dict for all tradable assets."""
        queries = get_all_news_queries()
        assert isinstance(queries, dict)
        assert len(queries) == len(TRADABLE_ASSETS)
        for epic in TRADABLE_ASSETS:
            assert epic in queries

    def test_crypto_finnhub_symbols(self):
        """Crypto assets have Binance symbols for crypto news."""
        assert "BINANCE:BTCUSDT" == EPIC_TO_FINNHUB_CRYPTO["BTCUSD"]
        assert "BINANCE:ETHUSDT" == EPIC_TO_FINNHUB_CRYPTO["ETHUSD"]
        assert len(EPIC_TO_FINNHUB_CRYPTO) == 7  # 7 crypto assets
