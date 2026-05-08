"""
Mapping from Capital.com epic codes to external API identifiers.

Provides:
- Finnhub tickers for equity features (insider, analyst, earnings)
- News query strings for Marketaux/Finnhub news sentiment (all 20 assets)
- Helper functions for feature tier classification
"""

from src.utils.constants import TRADABLE_ASSETS

# Finnhub requires stock tickers for equity-specific features
# (insider transactions, analyst recommendations, earnings).
# Only real stocks have these. None = not available on Finnhub equity API.
EPIC_TO_FINNHUB: dict[str, str | None] = {
    # Stocks
    "NVDA": "NVDA",
    "TSLA": "TSLA",
    "AAPL": "AAPL",
    "MSFT": "MSFT",
    "GOOGL": "GOOGL",
    "AMZN": "AMZN",
    "META": "META",
    "AMD": "AMD",
    # Crypto (Finnhub has crypto endpoints but not equity features)
    "BTCUSD": None,
    "ETHUSD": None,
    "SOLUSD": None,
    "BNBUSD": None,
    "DOGUSD": None,
    "DASHUSD": None,
    "ICPUSD": None,
    # Forex
    "EURUSD": None,
    "GBPUSD": None,
    "USDJPY": None,
    "USDCHF": None,
    "USDCAD": None,
    # Commodities
    "XAUUSD": None,
    "XAGUSD": None,
    "WTIUSD": None,
    "NATGAS": None,
    "COPPER": None,
    "PLATINUM": None,
    # Indices
    "US500": None,
    "DE40": None,
    "NAS100": None,
}

# News search queries for Marketaux / Finnhub news API.
# Every tradable asset should have a query string for sentiment analysis.
EPIC_TO_NEWS_QUERY: dict[str, str] = {
    # Stocks
    "NVDA": "NVIDIA NVDA",
    "TSLA": "Tesla TSLA",
    "AAPL": "Apple AAPL stock",
    "MSFT": "Microsoft MSFT stock",
    "GOOGL": "Alphabet Google GOOGL stock",
    "AMZN": "Amazon AMZN stock",
    "META": "Meta Platforms META stock",
    "AMD": "Advanced Micro Devices AMD stock",
    # Crypto
    "BTCUSD": "Bitcoin BTC crypto",
    "ETHUSD": "Ethereum ETH crypto",
    "SOLUSD": "Solana SOL crypto",
    "BNBUSD": "Binance BNB crypto",
    "DOGUSD": "Dogecoin DOGE crypto",
    "DASHUSD": "Dash DASH crypto",
    "ICPUSD": "Internet Computer ICP crypto",
    # Forex
    "EURUSD": "EUR USD euro dollar forex",
    "GBPUSD": "GBP USD pound sterling forex",
    "USDJPY": "USD JPY dollar yen forex",
    "USDCHF": "USD CHF dollar swiss franc forex",
    "USDCAD": "USD CAD dollar canadian forex",
    # Commodities
    "XAUUSD": "gold XAUUSD commodity",
    "XAGUSD": "silver XAGUSD commodity",
    "WTIUSD": "crude oil WTI commodity",
    "NATGAS": "natural gas commodity energy",
    "COPPER": "copper commodity metal",
    "PLATINUM": "platinum commodity metal",
    # Indices
    "US500": "S&P 500 SPX index",
    "DE40": "DAX 40 German index",
    "NAS100": "Nasdaq 100 QQQ index",
}

# Crypto-specific Finnhub symbols for news (different from equity tickers)
EPIC_TO_FINNHUB_CRYPTO: dict[str, str] = {
    "BTCUSD": "BINANCE:BTCUSDT",
    "ETHUSD": "BINANCE:ETHUSDT",
    "SOLUSD": "BINANCE:SOLUSDT",
    "BNBUSD": "BINANCE:BNBUSDT",
    "DOGUSD": "BINANCE:DOGEUSDT",
    "DASHUSD": "BINANCE:DASHUSDT",
    "ICPUSD": "BINANCE:ICPUSDT",
}


def supports_equity_features(epic: str) -> bool:
    """
    Check if an epic supports Finnhub equity features
    (insider transactions, analyst recommendations, earnings).

    Only real stocks (NVDA, TSLA) support this.
    """
    return EPIC_TO_FINNHUB.get(epic) is not None


def get_finnhub_ticker(epic: str) -> str | None:
    """Get the Finnhub equity ticker for an epic (None if not a stock)."""
    return EPIC_TO_FINNHUB.get(epic)


def get_news_query(epic: str) -> str | None:
    """Get the news search query for an epic."""
    return EPIC_TO_NEWS_QUERY.get(epic)


def get_all_news_queries() -> dict[str, str]:
    """Get news queries for all tradable assets."""
    return {
        epic: EPIC_TO_NEWS_QUERY[epic] for epic in TRADABLE_ASSETS if epic in EPIC_TO_NEWS_QUERY
    }
