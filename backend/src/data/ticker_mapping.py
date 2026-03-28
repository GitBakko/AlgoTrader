"""Maps Capital.com epic codes to yfinance and CryptoCompare tickers."""

# Capital.com epic -> yfinance ticker
_YFINANCE_MAP: dict[str, str] = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "WTIUSD": "CL=F",
    "NATGAS": "NG=F",
    "COPPER": "HG=F",
    "PLATINUM": "PL=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "SOLUSD": "SOL-USD",
    "BNBUSD": "BNB-USD",
    "DOGUSD": "DOGE-USD",
    "DASHUSD": "DASH-USD",
    "ICPUSD": "ICP-USD",
    "US500": "^GSPC",
    "NAS100": "^NDX",
    "DE40": "^GDAXI",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "NVDA": "NVDA",
    "TSLA": "TSLA",
}

_CRYPTO_MAP: dict[str, tuple[str, str]] = {
    "BTCUSD": ("BTC", "USD"),
    "ETHUSD": ("ETH", "USD"),
    "SOLUSD": ("SOL", "USD"),
    "BNBUSD": ("BNB", "USD"),
    "DOGUSD": ("DOGE", "USD"),
    "DASHUSD": ("DASH", "USD"),
    "ICPUSD": ("ICP", "USD"),
}

_ASSET_CLASS: dict[str, str] = {
    "XAUUSD": "commodity",
    "XAGUSD": "commodity",
    "WTIUSD": "commodity",
    "NATGAS": "commodity",
    "COPPER": "commodity",
    "PLATINUM": "commodity",
    "BTCUSD": "crypto",
    "ETHUSD": "crypto",
    "SOLUSD": "crypto",
    "BNBUSD": "crypto",
    "DOGUSD": "crypto",
    "DASHUSD": "crypto",
    "ICPUSD": "crypto",
    "US500": "index",
    "NAS100": "index",
    "DE40": "index",
    "EURUSD": "forex",
    "GBPUSD": "forex",
    "USDJPY": "forex",
    "NVDA": "stock",
    "TSLA": "stock",
}


class TickerMapper:
    @staticmethod
    def to_yfinance(epic: str) -> str | None:
        return _YFINANCE_MAP.get(epic)

    @staticmethod
    def to_cryptocompare(epic: str) -> tuple[str, str] | None:
        return _CRYPTO_MAP.get(epic)

    @staticmethod
    def asset_class(epic: str) -> str:
        return _ASSET_CLASS.get(epic, "unknown")

    @staticmethod
    def is_crypto(epic: str) -> bool:
        return epic in _CRYPTO_MAP

    @staticmethod
    def all_yfinance_mapped() -> dict[str, str]:
        return dict(_YFINANCE_MAP)
