"""
Session awareness filter for scalp trading.

Maps assets to their optimal trading sessions (kill zones) and returns
a score multiplier based on current UTC hour. SCALPING-GURU:
"Session awareness is NON-NEGOTIABLE for scalping."

Kill zones (highest probability windows):
  London Open: 07:00-10:00 UTC
  NY Open:     13:00-16:00 UTC
  Asia:        00:00-03:00 UTC (crypto/JPY only)
"""

# Asset → asset class mapping
_ASSET_CLASS: dict[str, str] = {
    # Forex majors
    "EURUSD": "forex_major",
    "GBPUSD": "forex_major",
    "USDJPY": "forex_major",
    # Commodities
    "XAUUSD": "commodity",
    "XAGUSD": "commodity",
    "WTIUSD": "commodity",
    "NATGAS": "commodity",
    "COPPER": "commodity",
    "PLATINUM": "commodity",
    # US indices
    "US500": "index_us",
    "NAS100": "index_us",
    # EU indices
    "DE40": "index_eu",
    # Crypto (24/7)
    "BTCUSD": "crypto",
    "ETHUSD": "crypto",
    "SOLUSD": "crypto",
    "BNBUSD": "crypto",
    "DOGUSD": "crypto",
    "DASHUSD": "crypto",
    "ICPUSD": "crypto",
    # US equities
    "NVDA": "equity",
    "TSLA": "equity",
}


class SessionFilter:
    """
    Determines session-based score multiplier for scalp entries.

    Multiplier values:
      1.0 — kill zone (prime time, highest probability)
      0.7 — active session but outside kill zone
      0.3 — off-peak for crypto (24/7 market, still trades)
      0.0 — off-session for non-crypto (hard block)
    """

    # Kill zones (UTC hours, inclusive start, exclusive end)
    LONDON_KILL = (7, 10)
    NY_KILL = (13, 16)
    ASIA_KILL = (0, 3)

    # Broader session windows (active but not kill zone)
    LONDON_SESSION = (6, 15)
    NY_SESSION = (12, 21)
    ASIA_SESSION = (22, 7)  # wraps midnight

    # Asset class → applicable kill zones
    _KILL_ZONES: dict[str, list[str]] = {
        "forex_major": ["london", "ny"],
        "commodity": ["london", "ny"],
        "index_us": ["ny"],
        "index_eu": ["london"],
        "crypto": ["london", "ny", "asia"],
        "equity": ["ny"],
    }

    @staticmethod
    def classify_asset(epic: str) -> str:
        """Map epic to asset class. Defaults to 'forex_major' for unknown."""
        return _ASSET_CLASS.get(epic, "forex_major")

    @classmethod
    def get_session_multiplier(cls, epic: str, utc_hour: int) -> float:
        """
        Get session-based score multiplier for an asset at given UTC hour.

        Args:
            epic: Asset epic code (e.g. "XAUUSD")
            utc_hour: Current hour in UTC (0-23)

        Returns:
            Multiplier in [0.0, 1.0]
        """
        asset_class = cls.classify_asset(epic)
        kill_zones = cls._KILL_ZONES.get(asset_class, ["london", "ny"])

        # Check kill zones first (highest priority)
        in_kill_zone = False
        if "london" in kill_zones and cls.LONDON_KILL[0] <= utc_hour < cls.LONDON_KILL[1]:
            in_kill_zone = True
        if "ny" in kill_zones and cls.NY_KILL[0] <= utc_hour < cls.NY_KILL[1]:
            in_kill_zone = True
        if "asia" in kill_zones and cls.ASIA_KILL[0] <= utc_hour < cls.ASIA_KILL[1]:
            in_kill_zone = True

        if in_kill_zone:
            return 1.0

        # Check broader session windows (active but not prime)
        in_session = False
        if "london" in kill_zones and cls.LONDON_SESSION[0] <= utc_hour < cls.LONDON_SESSION[1]:
            in_session = True
        if "ny" in kill_zones and cls.NY_SESSION[0] <= utc_hour < cls.NY_SESSION[1]:
            in_session = True
        if "asia" in kill_zones:
            # Asia wraps midnight: 22-24 OR 0-7
            if utc_hour >= cls.ASIA_SESSION[0] or utc_hour < cls.ASIA_SESSION[1]:
                in_session = True

        if in_session:
            return 0.7

        # Off-session
        if asset_class == "crypto":
            return 0.3  # Crypto trades 24/7 but reduced conviction off-peak
        return 0.0  # Hard block for non-crypto outside sessions

    @classmethod
    def is_blocked(cls, epic: str, utc_hour: int) -> bool:
        """Check if trading is completely blocked for this asset at this hour."""
        return cls.get_session_multiplier(epic, utc_hour) == 0.0
