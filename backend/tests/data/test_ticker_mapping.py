"""Tests for epic-to-ticker mapping."""
import pytest
from src.data.ticker_mapping import TickerMapper


class TestTickerMapper:
    def test_gold_yfinance(self):
        assert TickerMapper.to_yfinance("XAUUSD") == "GC=F"

    def test_btc_yfinance(self):
        assert TickerMapper.to_yfinance("BTCUSD") == "BTC-USD"

    def test_sp500_yfinance(self):
        assert TickerMapper.to_yfinance("US500") == "^GSPC"

    def test_tsla_yfinance(self):
        assert TickerMapper.to_yfinance("TSLA") == "TSLA"

    def test_unknown_returns_none(self):
        assert TickerMapper.to_yfinance("UNKNOWN123") is None

    def test_btc_cryptocompare(self):
        assert TickerMapper.to_cryptocompare("BTCUSD") == ("BTC", "USD")

    def test_eth_cryptocompare(self):
        assert TickerMapper.to_cryptocompare("ETHUSD") == ("ETH", "USD")

    def test_gold_not_crypto(self):
        assert TickerMapper.to_cryptocompare("XAUUSD") is None

    def test_all_tradable_have_yfinance(self):
        from src.utils.constants import TRADABLE_ASSETS
        unmapped = [a for a in TRADABLE_ASSETS if TickerMapper.to_yfinance(a) is None]
        assert unmapped == [], f"Unmapped: {unmapped}"

    def test_asset_class(self):
        assert TickerMapper.asset_class("BTCUSD") == "crypto"
        assert TickerMapper.asset_class("XAUUSD") == "commodity"
        assert TickerMapper.asset_class("TSLA") == "stock"
        assert TickerMapper.asset_class("EURUSD") == "forex"
        assert TickerMapper.asset_class("US500") == "index"
