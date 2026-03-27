"""
Signal Intelligence Layer — Composite Fear & Greed Client.

Computes a composite Fear & Greed index from multiple free sources:
1. VIX level (30%) — via macro data or yfinance
2. VIX 5-day change (15%) — rapid increase = fear
3. Safe haven demand (25%) — gold vs S&P 500 relative 20d performance
4. Market breadth proxy (15%) — % of assets above 20-day SMA
5. Crypto Fear & Greed (15%) — Alternative.me free API

All components degrade gracefully: missing data → neutral (50).
"""

from datetime import datetime, timezone

from loguru import logger

from src.external.sil_base_client import SILBaseClient
from src.external.sil_schemas import FearGreedData


class FearGreedClient(SILBaseClient):
    """Composite Fear & Greed index from multiple free sources."""

    ALTERNATIVE_ME_URL = "https://api.alternative.me/fng/"

    # VIX → F&G mapping: VIX 12 = max greed (100), VIX 40 = max fear (0)
    VIX_FLOOR = 12.0
    VIX_CEILING = 40.0

    def __init__(self, cache_ttl_minutes: int | None = None):
        super().__init__("fear_greed", cache_ttl_minutes=cache_ttl_minutes)

    async def fetch(
        self,
        vix: float | None = None,
        vix_change_5d: float | None = None,
        gold_vs_sp500_20d: float | None = None,
        breadth_pct: float | None = None,
    ) -> FearGreedData:
        """
        Compute composite Fear & Greed.

        Args:
            vix: Current VIX level
            vix_change_5d: 5-day VIX percentage change (e.g., 0.10 = +10%)
            gold_vs_sp500_20d: Gold 20d return minus S&P 20d return
                               (positive = gold outperforms = fear)
            breadth_pct: Percentage of assets above 20-day SMA (0-100)

        Returns:
            FearGreedData with composite index
        """
        cached = self._get_cached("fear_greed")
        if cached is not None:
            return cached

        components: list[float] = []
        weights: list[float] = []

        # 1. VIX level (30%) — higher VIX = lower F&G (more fear)
        if vix is not None:
            vix_clamped = max(self.VIX_FLOOR, min(self.VIX_CEILING, vix))
            vix_score = (self.VIX_CEILING - vix_clamped) / (self.VIX_CEILING - self.VIX_FLOOR) * 100
            components.append(vix_score)
            weights.append(0.30)

        # 2. VIX momentum (15%) — rapid VIX increase = fear
        if vix_change_5d is not None:
            # +20% VIX change → F&G ~0, -20% → F&G ~100
            mom_score = max(0.0, min(100.0, 50.0 - vix_change_5d * 250.0))
            components.append(mom_score)
            weights.append(0.15)

        # 3. Safe haven demand (25%) — gold outperforming = fear
        if gold_vs_sp500_20d is not None:
            # +5% gold outperformance → F&G ~0, -5% → F&G ~100
            sh_score = max(0.0, min(100.0, 50.0 - gold_vs_sp500_20d * 1000.0))
            components.append(sh_score)
            weights.append(0.25)

        # 4. Market breadth (15%) — % above 20d SMA directly maps to F&G
        if breadth_pct is not None:
            components.append(max(0.0, min(100.0, breadth_pct)))
            weights.append(0.15)

        # 5. Crypto Fear & Greed (15%) — free API
        crypto_fg = await self._fetch_alternative_me()
        if crypto_fg is not None:
            components.append(crypto_fg)
            weights.append(0.15)

        # Weighted average (re-normalize weights for available components)
        if components:
            total_weight = sum(weights)
            composite = sum(c * w for c, w in zip(components, weights)) / total_weight
        else:
            composite = 50.0

        result = FearGreedData(
            value=round(composite, 1),
            normalized=round(composite / 100.0, 3),
            classification=self._classify(composite),
            is_extreme_fear=composite <= 20.0,
            is_extreme_greed=composite >= 80.0,
            gold_bias=round((100.0 - composite) / 100.0 * 2.0 - 1.0, 3),
            timestamp=datetime.now(timezone.utc),
        )
        self._set_cache("fear_greed", result)
        return result

    async def _fetch_alternative_me(self) -> float | None:
        """Fetch crypto Fear & Greed from Alternative.me (free, no auth)."""
        try:
            client = await self._get_client()
            resp = await client.get(self.ALTERNATIVE_ME_URL, params={"limit": 1})
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                return float(data[0]["value"])
        except Exception as e:
            logger.debug(f"[FearGreedClient] Alternative.me fetch failed: {e}")
        return None

    @staticmethod
    def _classify(value: float) -> str:
        """Classify F&G value into human-readable label."""
        if value <= 20:
            return "extreme_fear"
        elif value <= 40:
            return "fear"
        elif value <= 60:
            return "neutral"
        elif value <= 80:
            return "greed"
        return "extreme_greed"
