"""
Signal Intelligence Layer — FRED Client.

Fetches 12 economic indicator series from the Federal Reserve
Economic Data (FRED) API. Free tier, no strict rate limit.
TTL: 24 hours (economic data updates daily at most).
"""

from datetime import UTC, datetime

from loguru import logger

from src.external.sil_base_client import SILBaseClient
from src.external.sil_schemas import FREDData

# FRED series IDs → FREDData field mapping
SERIES_FIELD_MAP: dict[str, str] = {
    "DFF": "fed_funds_rate",
    "T10Y2Y": "yield_spread_10y2y",
    "BAMLH0A0HYM2": "high_yield_spread",
    "UMCSENT": "consumer_sentiment",
    "UNRATE": "unemployment_rate",
    "PAYEMS": "nonfarm_payrolls",
    "DFII10": "real_yield_10y",
    "T10YIE": "breakeven_inflation",
    "DGS10": "nominal_yield_10y",
    "DTWEXBGS": "broad_dollar",
    "VIXCLS": "vix_close",
    "DCOILWTICO": "wti_crude",
}

SERIES_IDS = list(SERIES_FIELD_MAP.keys())


class FREDClient(SILBaseClient):
    """FRED API client for 12 economic indicator series."""

    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, cache_ttl_minutes: int | None = None):
        super().__init__(
            "fred",
            cache_ttl_minutes=cache_ttl_minutes or 24 * 60,  # 24h default
        )

    async def fetch(self) -> FREDData:
        """
        Fetch latest value for all 12 FRED series.

        Returns:
            FREDData with available values (None for failed fetches).
        """
        cached = self._get_cached("fred")
        if cached is not None:
            return cached

        api_key = self._settings.fred_api_key
        if not api_key:
            logger.debug("[FREDClient] No FRED_API_KEY configured, returning defaults")
            return FREDData()

        results: dict[str, float] = {}
        client = await self._get_client()

        for series_id in SERIES_IDS:
            try:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "series_id": series_id,
                        "api_key": api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 1,
                    },
                )
                resp.raise_for_status()
                observations = resp.json().get("observations", [])
                if observations and observations[0].get("value", ".") != ".":
                    results[series_id] = float(observations[0]["value"])
            except Exception as e:
                logger.debug(f"[FREDClient] {series_id} fetch failed: {e}")

        # Map series IDs to FREDData fields
        field_values: dict[str, float | None] = {}
        for series_id, field_name in SERIES_FIELD_MAP.items():
            field_values[field_name] = results.get(series_id)

        data = FREDData(
            **field_values,
            timestamp=datetime.now(UTC),
        )
        self._set_cache("fred", data)
        logger.info(f"[FREDClient] Fetched {len(results)}/{len(SERIES_IDS)} series")
        return data

    async def fetch_single(self, series_id: str) -> float | None:
        """Fetch a single FRED series value. No caching."""
        api_key = self._settings.fred_api_key
        if not api_key:
            return None

        try:
            client = await self._get_client()
            resp = await client.get(
                self.BASE_URL,
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 1,
                },
            )
            resp.raise_for_status()
            observations = resp.json().get("observations", [])
            if observations and observations[0].get("value", ".") != ".":
                return float(observations[0]["value"])
        except Exception as e:
            logger.debug(f"[FREDClient] {series_id} single fetch failed: {e}")
        return None
