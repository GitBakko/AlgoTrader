# Signal Intelligence Layer (SIL) — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 5 external data clients, 12 ML features, and an Economic Calendar gate to enrich MANTIS trading signals with macro/sentiment intelligence.

**Architecture:** SIL is an optional layer (`SIL_ENABLED=true`) that fetches data from 5 external sources, computes 12 `sil_*` features injected into the ML pipeline, and gates trades via an Economic Calendar blackout window. All clients degrade gracefully (return defaults on failure).

**Tech Stack:** Python 3.12, httpx (async), Polars, pydantic, pytest, existing MANTIS patterns (RateLimiter, cache TTL, graceful degradation)

---

## Adaptation Notes (vs. Original Prompt Contract)

| Contract Says | Actual Code | Adaptation |
|---------------|-------------|------------|
| `feature_engineer.py` | `builder.py` (FeatureBuilder) | Use `builder.py`, add `sil_data` param |
| `macro_features.py` | Inline in `builder.py` | SIL features added after macro in same file |
| `StockTwitsClient` | StockTwits deprecated | **RedditSentimentClient** + **XSentimentClient** |
| `check_trade()` async gate | `check_trade()` is SYNC | Calendar gate called in `paper_loop._process_epic()` BEFORE `check_trade()` |
| Fear & Greed from alternative.me only | User wants composite | **CompositeF&G**: VIX level + VIX change + put/call ratio + safe haven demand + breadth |
| FRED 4 series | User wants contract 6 + existing 6 | 12 FRED series total |

## Implementation Order (Gradual)

| Phase | Component | Priority | Est. |
|-------|-----------|----------|------|
| **3a** | SIL schemas + base client | HIGH | 20 min |
| **3b** | FearGreedClient (composite) | HIGH | 30 min |
| **3c** | FREDClient (12 series) | HIGH | 30 min |
| **3d** | AlphaVantageClient | MEDIUM | 25 min |
| **3e** | COTClient (API wrapper) | MEDIUM | 25 min |
| **3f** | SocialSentimentClient (Reddit + X) | MEDIUM | 30 min |
| **4** | EconomicCalendarGate | HIGH | 40 min |
| **5** | SIL Features (12 columns) + Builder integration | HIGH | 40 min |
| **6** | Paper Loop integration | HIGH | 30 min |
| **7** | SIL API Router | LOW | 20 min |
| **8** | Final verification | HIGH | 20 min |

---

## Task 3a: SIL Schemas + Base Client

**Files:**
- Create: `backend/src/external/sil_schemas.py`
- Create: `backend/src/external/sil_base_client.py`
- Test: `backend/tests/external/test_sil_schemas.py`

### Schema Design

```python
# sil_schemas.py
from pydantic import BaseModel, Field
from datetime import datetime

class FearGreedData(BaseModel):
    """Composite Fear & Greed index data."""
    value: float = Field(default=50.0, ge=0, le=100, description="0=extreme fear, 100=extreme greed")
    normalized: float = Field(default=0.5, ge=0, le=1.0)
    classification: str = Field(default="neutral")
    is_extreme_fear: bool = False
    is_extreme_greed: bool = False
    gold_bias: float = Field(default=0.0, ge=-1.0, le=1.0, description="+1=bullish gold (fear), -1=bearish gold (greed)")
    timestamp: datetime | None = None

class FREDData(BaseModel):
    """FRED economic indicators."""
    fed_funds_rate: float | None = None          # DFF
    yield_spread_10y2y: float | None = None      # T10Y2Y
    high_yield_spread: float | None = None       # BAMLH0A0HYM2
    consumer_sentiment: float | None = None      # UMCSENT
    unemployment_rate: float | None = None        # UNRATE
    nonfarm_payrolls: float | None = None         # PAYEMS
    # Existing macro overlap (kept for backward compat)
    real_yield_10y: float | None = None           # DFII10
    breakeven_inflation: float | None = None      # T10YIE
    nominal_yield_10y: float | None = None        # DGS10
    broad_dollar: float | None = None             # DTWEXBGS
    timestamp: datetime | None = None

class AlphaVantageData(BaseModel):
    """Alpha Vantage news sentiment."""
    average_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    bullish_ratio: float = Field(default=0.5, ge=0, le=1.0)
    timestamp: datetime | None = None

class COTData(BaseModel):
    """CFTC Commitment of Traders data."""
    noncomm_long: int = 0
    noncomm_short: int = 0
    net_position: int = 0
    net_position_normalized: float = 0.0   # normalized on 52w history
    is_institutional_bullish: bool = False
    z_score_4w: float = 0.0
    report_date: datetime | None = None

class SocialSentimentData(BaseModel):
    """Reddit + X social sentiment."""
    reddit_bullish_ratio: float = Field(default=0.5, ge=0, le=1.0)
    reddit_post_count: int = 0
    reddit_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    x_bullish_ratio: float = Field(default=0.5, ge=0, le=1.0)
    x_post_count: int = 0
    x_sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    combined_bullish_ratio: float = Field(default=0.5, ge=0, le=1.0)
    timestamp: datetime | None = None

class SILData(BaseModel):
    """Aggregated SIL data passed to feature pipeline."""
    fear_greed: FearGreedData = Field(default_factory=FearGreedData)
    fred: FREDData = Field(default_factory=FREDData)
    alpha_vantage: AlphaVantageData = Field(default_factory=AlphaVantageData)
    cot: COTData = Field(default_factory=COTData)
    social: SocialSentimentData = Field(default_factory=SocialSentimentData)
    fetch_errors: list[str] = Field(default_factory=list)
```

### Base Client Pattern

```python
# sil_base_client.py
import httpx
from datetime import datetime, timezone
from loguru import logger
from src.utils.config import get_settings

class SILBaseClient:
    """Base class for SIL external clients with caching and graceful degradation."""

    def __init__(self, name: str, cache_ttl_minutes: int | None = None):
        self.name = name
        self._settings = get_settings()
        self._cache_ttl = cache_ttl_minutes or self._settings.sil_cache_ttl_minutes
        self._cache: dict[str, tuple[datetime, any]] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        cached_at, _ = self._cache[key]
        age_minutes = (datetime.now(timezone.utc) - cached_at).total_seconds() / 60
        return age_minutes < self._cache_ttl

    def _get_cached(self, key: str):
        if self._is_cache_valid(key):
            return self._cache[key][1]
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = (datetime.now(timezone.utc), data)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
```

### Test

```python
# tests/external/test_sil_schemas.py
from src.external.sil_schemas import SILData, FearGreedData, FREDData

class TestSILSchemas:
    def test_sil_data_defaults(self):
        """SILData with all defaults produces valid object."""
        data = SILData()
        assert data.fear_greed.value == 50.0
        assert data.fred.fed_funds_rate is None
        assert data.social.combined_bullish_ratio == 0.5

    def test_fear_greed_gold_bias(self):
        """Extreme fear = positive gold bias."""
        fg = FearGreedData(value=10, normalized=0.1, is_extreme_fear=True, gold_bias=0.8)
        assert fg.gold_bias > 0

    def test_sil_data_with_errors(self):
        """SILData tracks fetch errors."""
        data = SILData(fetch_errors=["FREDClient: timeout", "COTClient: 503"])
        assert len(data.fetch_errors) == 2
```

**Step 1:** Write test → **Step 2:** Run, verify fail → **Step 3:** Implement schemas + base → **Step 4:** Run, verify pass → **Step 5:** Commit

---

## Task 3b: FearGreedClient (Composite)

**Files:**
- Create: `backend/src/external/fear_greed_client.py`
- Test: `backend/tests/external/test_fear_greed_client.py`

### Design

Composite Fear & Greed from FREE sources:
1. **VIX level** (already in macro_client via yfinance) → fear when VIX > 25
2. **VIX 5-day change** → rapid increase = fear
3. **Safe haven demand** (gold vs S&P 500 relative performance, 20-day) → gold outperformance = fear
4. **Market breadth proxy** (percentage of assets above 20-day SMA from MANTIS watchlist)
5. **Alternative.me crypto F&G** (free API, for crypto-weighted component)

Weights: VIX 30%, VIX change 15%, Safe Haven 25%, Breadth 15%, Crypto F&G 15%

Gold bias: `gold_bias = (100 - composite_value) / 100 * 2 - 1` (fear→positive, greed→negative)

```python
class FearGreedClient(SILBaseClient):
    ALTERNATIVE_ME_URL = "https://api.alternative.me/fng/"

    async def fetch(self, vix: float | None = None, vix_change_5d: float | None = None,
                    gold_vs_sp500_20d: float | None = None,
                    breadth_pct: float | None = None) -> FearGreedData:
        """Compute composite Fear & Greed. Pass available data; missing = neutral (50)."""
        cached = self._get_cached("fear_greed")
        if cached is not None:
            return cached

        components = []
        weights = []

        # 1. VIX level (30%)
        if vix is not None:
            vix_score = max(0, min(100, 100 - (vix - 12) * (100 / 28)))  # 12=greed, 40=fear
            components.append(100 - vix_score)  # Invert: high VIX = low F&G
            weights.append(0.30)

        # 2. VIX momentum (15%)
        if vix_change_5d is not None:
            mom_score = max(0, min(100, 50 - vix_change_5d * 500))
            components.append(mom_score)
            weights.append(0.15)

        # 3. Safe haven demand (25%)
        if gold_vs_sp500_20d is not None:
            sh_score = max(0, min(100, 50 - gold_vs_sp500_20d * 200))
            components.append(sh_score)
            weights.append(0.25)

        # 4. Market breadth (15%)
        if breadth_pct is not None:
            components.append(breadth_pct)  # Already 0-100
            weights.append(0.15)

        # 5. Crypto F&G (15%) — free API
        crypto_fg = await self._fetch_alternative_me()
        if crypto_fg is not None:
            components.append(crypto_fg)
            weights.append(0.15)

        # Weighted average (re-normalize weights)
        if components:
            total_weight = sum(weights)
            composite = sum(c * w for c, w in zip(components, weights)) / total_weight
        else:
            composite = 50.0

        result = FearGreedData(
            value=round(composite, 1),
            normalized=round(composite / 100, 3),
            classification=self._classify(composite),
            is_extreme_fear=composite <= 20,
            is_extreme_greed=composite >= 80,
            gold_bias=round((100 - composite) / 100 * 2 - 1, 3),
            timestamp=datetime.now(timezone.utc),
        )
        self._set_cache("fear_greed", result)
        return result
```

### Test (key cases)

```python
class TestFearGreedClient:
    @pytest.mark.asyncio
    async def test_extreme_fear_from_high_vix(self):
        client = FearGreedClient()
        result = await client.fetch(vix=40.0, vix_change_5d=0.15)
        assert result.value < 30
        assert result.gold_bias > 0.3

    @pytest.mark.asyncio
    async def test_all_none_returns_neutral(self):
        client = FearGreedClient()
        result = await client.fetch()
        assert result.value == 50.0
        assert result.classification == "neutral"

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        client = FearGreedClient()
        await client.fetch(vix=25.0)
        # Second call should use cache
        result = await client.fetch(vix=10.0)  # Different VIX
        assert result == client._get_cached("fear_greed")  # Same as first
```

---

## Task 3c: FREDClient (12 Series)

**Files:**
- Create: `backend/src/external/fred_client.py`
- Test: `backend/tests/external/test_fred_client.py`

### Design

12 FRED series (6 new from contract + 6 existing macro overlap):

| Series | Name | Category |
|--------|------|----------|
| DFF | Fed Funds Rate | Rates |
| T10Y2Y | 10Y-2Y Spread | Yield Curve |
| BAMLH0A0HYM2 | High Yield Spread | Credit |
| UMCSENT | Consumer Sentiment | Sentiment |
| UNRATE | Unemployment Rate | Labor |
| PAYEMS | Nonfarm Payrolls | Labor |
| DFII10 | Real Yield 10Y | Rates |
| T10YIE | Breakeven Inflation | Inflation |
| DGS10 | Nominal Yield 10Y | Rates |
| DTWEXBGS | Broad Dollar Index | FX |
| VIXCLS | VIX Close | Volatility |
| DCOILWTICO | WTI Crude | Commodities |

TTL: 24 hours. Free API, no strict rate limit (but polite — max 1 req/series/day).

```python
class FREDClient(SILBaseClient):
    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
    SERIES = ["DFF", "T10Y2Y", "BAMLH0A0HYM2", "UMCSENT", "UNRATE", "PAYEMS",
              "DFII10", "T10YIE", "DGS10", "DTWEXBGS", "VIXCLS", "DCOILWTICO"]

    async def fetch(self) -> FREDData:
        """Fetch latest value for all FRED series."""
        cached = self._get_cached("fred")
        if cached is not None:
            return cached

        api_key = self._settings.fred_api_key
        if not api_key:
            return FREDData()

        results = {}
        client = await self._get_client()
        for series_id in self.SERIES:
            try:
                resp = await client.get(self.BASE_URL, params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 1,
                })
                resp.raise_for_status()
                obs = resp.json().get("observations", [])
                if obs and obs[0]["value"] != ".":
                    results[series_id] = float(obs[0]["value"])
            except Exception as e:
                logger.debug(f"FRED {series_id} fetch failed: {e}")

        data = FREDData(
            fed_funds_rate=results.get("DFF"),
            yield_spread_10y2y=results.get("T10Y2Y"),
            high_yield_spread=results.get("BAMLH0A0HYM2"),
            consumer_sentiment=results.get("UMCSENT"),
            unemployment_rate=results.get("UNRATE"),
            nonfarm_payrolls=results.get("PAYEMS"),
            real_yield_10y=results.get("DFII10"),
            breakeven_inflation=results.get("T10YIE"),
            nominal_yield_10y=results.get("DGS10"),
            broad_dollar=results.get("DTWEXBGS"),
            timestamp=datetime.now(timezone.utc),
        )
        self._set_cache("fred", data)
        return data
```

---

## Task 3d: AlphaVantageClient

**Files:**
- Create: `backend/src/external/alpha_vantage_client.py`
- Test: `backend/tests/external/test_alpha_vantage_client.py`

### Design

- NEWS_SENTIMENT function with topic filter per asset class
- 25 req/day limit → TTL 23 hours, single daily call
- Asset topic mapping: gold→"gold", crypto→"cryptocurrency", forex→"forex", indices→"financial_markets"

```python
class AlphaVantageClient(SILBaseClient):
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self):
        super().__init__("alpha_vantage", cache_ttl_minutes=23 * 60)  # 23 hours

    async def fetch(self, topic: str = "gold") -> AlphaVantageData:
        cached = self._get_cached(f"av_{topic}")
        if cached is not None:
            return cached

        api_key = self._settings.alpha_vantage_api_key
        if not api_key:
            return AlphaVantageData()

        client = await self._get_client()
        resp = await client.get(self.BASE_URL, params={
            "function": "NEWS_SENTIMENT",
            "topics": topic,
            "apikey": api_key,
            "limit": 50,
        })
        resp.raise_for_status()
        feed = resp.json().get("feed", [])

        bullish = sum(1 for a in feed if float(a.get("overall_sentiment_score", 0)) > 0.15)
        bearish = sum(1 for a in feed if float(a.get("overall_sentiment_score", 0)) < -0.15)
        neutral = len(feed) - bullish - bearish
        avg_score = sum(float(a.get("overall_sentiment_score", 0)) for a in feed) / max(len(feed), 1)

        result = AlphaVantageData(
            average_sentiment_score=round(avg_score, 4),
            bullish_count=bullish, bearish_count=bearish, neutral_count=neutral,
            bullish_ratio=round(bullish / max(bullish + bearish, 1), 3),
            timestamp=datetime.now(timezone.utc),
        )
        self._set_cache(f"av_{topic}", result)
        return result
```

---

## Task 3e: COTClient (API Wrapper)

**Files:**
- Create: `backend/src/external/cot_client.py`
- Test: `backend/tests/external/test_cot_client.py`

### Design

Use **Quandl/Nasdaq Data Link** API (free tier) for CFTC COT data. Fallback: direct CFTC CSV.

Asset mapping for COT contract codes:
- XAUUSD → "088691" (Gold)
- XAGUSD → "084691" (Silver)
- WTIUSD → "067651" (Crude Oil)
- EURUSD → "099741" (Euro FX)
- GBPUSD → "096742" (British Pound)
- USDJPY → "097741" (Japanese Yen)
- BTCUSD → "133741" (Bitcoin)
- US500 → "13874A" (E-mini S&P 500)
- NAS100 → "209742" (E-mini Nasdaq)
- NATGAS → "023651" (Natural Gas)
- COPPER → "085692" (Copper)

TTL: 7 days (weekly report).

```python
class COTClient(SILBaseClient):
    BASE_URL = "https://data.nasdaq.com/api/v3/datasets/CFTC"

    def __init__(self):
        super().__init__("cot", cache_ttl_minutes=7 * 24 * 60)  # 7 days

    async def fetch(self, epic: str) -> COTData:
        contract = self.EPIC_TO_CONTRACT.get(epic)
        if contract is None:
            return COTData()

        cached = self._get_cached(f"cot_{epic}")
        if cached is not None:
            return cached

        # Fetch from Nasdaq Data Link (ex-Quandl)
        client = await self._get_client()
        resp = await client.get(
            f"{self.BASE_URL}/{contract}_FO_L_ALL.json",
            params={"rows": 5, "order": "desc"},
        )
        resp.raise_for_status()
        dataset = resp.json().get("dataset", {}).get("data", [])
        # Parse noncomm long/short positions, compute net + z-score
        ...
```

---

## Task 3f: SocialSentimentClient (Reddit + X)

**Files:**
- Create: `backend/src/external/social_sentiment_client.py`
- Test: `backend/tests/external/test_social_sentiment_client.py`

### Design

**Reddit**: Use Reddit JSON API (no auth needed for public subreddits, append `.json` to URL).
- Subreddits: r/wallstreetbets, r/investing, r/CryptoCurrency, r/Gold, r/Forex
- Search: epic-specific keywords (XAUUSD→"gold", BTCUSD→"bitcoin", etc.)
- Simple sentiment: count upvotes on bullish/bearish posts, keyword scoring

**X/Twitter**: Use free Nitter instances or X API v2 free tier (1500 tweets/month).
- Search: `$XAUUSD` or `$GOLD` cashtags
- Sentiment: keyword-based (bullish/bearish word lists)

TTL: 15 minutes.

Both wrapped in try/except → default SocialSentimentData on failure.

---

## Task 4: Economic Calendar Gate

**Files:**
- Create: `backend/src/risk/economic_calendar_gate.py`
- Modify: `backend/src/trading/paper_loop.py` (in `_process_epic`, BEFORE risk check)
- Test: `backend/tests/risk/test_economic_calendar_gate.py`

### Design

Uses **Finnhub** `/calendar/economic` (already available in FinnhubClient).

```python
class EconomicCalendarGate:
    HIGH_IMPACT_EVENTS = {"CPI", "NFP", "FOMC", "GDP", "PPI", "Fed Rate Decision",
                          "ECB Rate Decision", "BOE Rate Decision", "Core CPI",
                          "Initial Jobless Claims", "Retail Sales"}

    EPIC_SENSITIVITY = {
        # USD-sensitive: all high-impact US events
        "XAUUSD": ["USD"], "XAGUSD": ["USD"], "EURUSD": ["USD", "EUR"],
        "GBPUSD": ["USD", "GBP"], "USDJPY": ["USD", "JPY"],
        # Crypto: only Fed/CPI
        "BTCUSD": ["USD_MAJOR"], "ETHUSD": ["USD_MAJOR"],
        # Indices: all high-impact
        "US500": ["USD"], "NAS100": ["USD"], "DE40": ["EUR"],
        # Commodities
        "WTIUSD": ["USD"], "NATGAS": ["USD"],
    }

    async def is_blackout(self, epic: str, now: datetime | None = None) -> tuple[bool, str]:
        """Check if epic is in economic event blackout window."""
        settings = get_settings()
        if not settings.sil_calendar_gate_enabled:
            return False, ""

        events = await self._get_todays_events()
        minutes_before = settings.sil_calendar_minutes_before
        minutes_after = settings.sil_calendar_minutes_after

        currencies = self.EPIC_SENSITIVITY.get(epic, [])
        for event in events:
            if event["impact"] != "high":
                continue
            if not self._event_affects_currency(event, currencies):
                continue
            event_time = event["datetime"]
            window_start = event_time - timedelta(minutes=minutes_before)
            window_end = event_time + timedelta(minutes=minutes_after)
            if window_start <= now <= window_end:
                return True, f"Calendar blackout: {event['event']} at {event_time.strftime('%H:%M')} UTC"

        return False, ""
```

### Integration in paper_loop.py

In `_process_epic()`, after market hours check and before strategy/risk:

```python
# Step 0b: Economic Calendar gate (SIL)
if self._calendar_gate is not None:
    is_blackout, blackout_reason = await self._calendar_gate.is_blackout(epic)
    if is_blackout:
        logger.info(f"[{epic}] {blackout_reason}")
        signal_info = {
            "epic": epic, "direction": "HOLD", "confidence": 0.0,
            "status": "calendar_blackout", "rejection_reason": blackout_reason,
            ...
        }
        return
```

---

## Task 5: SIL Features + Builder Integration

**Files:**
- Create: `backend/src/features/sil_features.py`
- Modify: `backend/src/features/builder.py` (add `sil_data` param, call `compute_sil_features`)
- Test: `backend/tests/features/test_sil_features.py`

### 12 SIL Features

```python
def compute_sil_features(df: pl.DataFrame, sil_data: SILData | None) -> pl.DataFrame:
    """Add 12 sil_* columns to DataFrame. All fill_null(0.0) for XGBoost."""
    if sil_data is None:
        # Add all 12 columns as 0.0
        for col in SIL_FEATURE_COLS:
            df = df.with_columns(pl.lit(0.0).alias(col))
        return df

    fg = sil_data.fear_greed
    fred = sil_data.fred
    av = sil_data.alpha_vantage
    cot = sil_data.cot
    social = sil_data.social

    df = df.with_columns([
        pl.lit(fg.normalized).alias("sil_fear_greed_value"),
        pl.lit(fg.gold_bias).alias("sil_fear_greed_gold_bias"),
        pl.lit(fred.real_yield_10y or 0.0).alias("sil_real_yield_10y"),
        pl.lit(fred.breakeven_inflation or 0.0).alias("sil_breakeven_inflation"),
        pl.lit(1.0 if (fred.real_yield_10y or 0) < -1.0 else 0.0).alias("sil_gold_bullish_yield"),
        pl.lit(av.average_sentiment_score).alias("sil_alpha_sentiment_score"),
        pl.lit(av.bullish_ratio).alias("sil_alpha_bullish_ratio"),
        pl.lit(cot.net_position_normalized).alias("sil_cot_net_position_norm"),
        pl.lit(cot.z_score_4w).alias("sil_cot_z_score"),
        pl.lit(1.0 if cot.is_institutional_bullish else 0.0).alias("sil_cot_institutional_bull"),
        pl.lit(social.combined_bullish_ratio).alias("sil_social_bullish_ratio"),
        # Composite gold score: weighted average
        pl.lit(self._compute_composite(fg, fred, av, cot, social)).alias("sil_composite_score"),
    ])
    return df

SIL_FEATURE_COLS = [
    "sil_fear_greed_value", "sil_fear_greed_gold_bias",
    "sil_real_yield_10y", "sil_breakeven_inflation", "sil_gold_bullish_yield",
    "sil_alpha_sentiment_score", "sil_alpha_bullish_ratio",
    "sil_cot_net_position_norm", "sil_cot_z_score", "sil_cot_institutional_bull",
    "sil_social_bullish_ratio", "sil_composite_score",
]
```

### Composite Score Weights
- Fear & Greed: 30%
- Yield/Rate: 25%
- News Sentiment: 20%
- COT: 15%
- Social: 10%

### Builder Integration

In `build_features()`, after `_add_macro_features()`:

```python
# SIL features (optional)
if sil_data is not None:
    from src.features.sil_features import compute_sil_features
    df = compute_sil_features(df, sil_data)
else:
    from src.features.sil_features import SIL_FEATURE_COLS
    for col in SIL_FEATURE_COLS:
        df = df.with_columns(pl.lit(0.0).alias(col))
```

---

## Task 6: Paper Loop Integration

**Files:**
- Modify: `backend/src/trading/paper_loop.py`
- Test: `backend/tests/trading/test_paper_loop_sil.py`

### Changes

1. **`__init__`**: Instantiate SIL clients + EconomicCalendarGate (if `SIL_ENABLED`)
2. **`_fetch_sil_data()`**: New async method, `asyncio.gather` all 5 clients, catch per-client errors
3. **`_run_iteration()`**: Call `_fetch_sil_data()` BEFORE epic loop, store as `self._sil_data`
4. **`_process_epic()`**:
   - Call Calendar gate BEFORE strategy/risk
   - Pass `sil_data=self._sil_data` to feature pipeline

### Fetch Frequency Logic
```python
async def _fetch_sil_data(self) -> SILData:
    """Fetch all SIL data with per-client error handling."""
    if not self._settings.sil_enabled:
        return SILData()

    errors = []
    # Fast clients (every iteration): Fear&Greed, Social
    # Slow clients (cached 24h+): FRED, AlphaVantage, COT
    tasks = [
        self._safe_fetch("fear_greed", self._fg_client.fetch, ...),
        self._safe_fetch("fred", self._fred_client.fetch),
        self._safe_fetch("alpha_vantage", self._av_client.fetch),
        self._safe_fetch("cot", self._cot_client.fetch, epic="XAUUSD"),
        self._safe_fetch("social", self._social_client.fetch),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Assemble SILData from results...
```

---

## Task 7: SIL API Router

**Files:**
- Create: `backend/src/api/routers/sil.py`
- Modify: `backend/src/api/dependencies.py` (register router)
- Test: manual via `curl`

### Endpoints

```
GET /api/sil/status     → { enabled, clients: {name: {status, last_fetch, cache_age}}, features_count: 12 }
GET /api/sil/data       → Current SILData snapshot
GET /api/sil/calendar   → Today's high-impact events + blackout windows
```

---

## Task 8: Final Verification

**Steps:**
1. `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x --no-cov -q` → 0 failures
2. Verify all 1308+ existing tests still pass
3. Coverage check on new modules: `pytest tests/external/ tests/features/test_sil_features.py tests/risk/test_economic_calendar_gate.py --cov=src/external --cov=src/features/sil_features --cov=src/risk/economic_calendar_gate -v`
4. Graceful degradation: kill Redis/external APIs → paper loop continues with `SILData()` defaults
5. Commit: `feat(sil): Signal Intelligence Layer — 5 external clients, 12 features, economic calendar gate`
