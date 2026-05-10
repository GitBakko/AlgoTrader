"""
Feature builder orchestrator.
Coordinates the full feature engineering pipeline:
OHLC data -> technical indicators -> normalization -> regime detection -> FeatureMatrix

Sentiment data flow (Step 8):
- Async fetch: call `fetch_sentiment_data(epic, ...)` from an async context
- Sync apply: pass the result dict to `build_features(sentiment_data=...)` or `_apply_sentiment_features()`
"""

from datetime import UTC, datetime, timedelta  # noqa: F401

import polars as pl
from loguru import logger

from src.data.data_access import DataAccessLayer
from src.features.alignment import TimeframeAligner
from src.features.asset_config import DEFAULT_TECHNICAL_PARAMS, get_asset_config
from src.features.keltner import KeltnerChannel
from src.features.market_structure import MarketStructureDetector
from src.features.normalizer import FeatureNormalizer
from src.features.regime import RegimeDetector
from src.features.schemas import AssetFeatureConfig, FeatureMatrix
from src.features.sentiment import SentimentFeatures
from src.features.technical import TechnicalIndicators
from src.features.vwap_bands import VWAPBands
from src.utils.config import get_settings


async def fetch_sentiment_data(
    epic: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """
    Async-safe function to fetch sentiment data from external APIs.

    Call this from async contexts (FastAPI, paper_loop, etc.), then pass
    the result to build_features(sentiment_data=...).

    Tier 1 (NVDA, TSLA): fetches insider, analyst, price_target, earnings, news
    Tier 2 (all others): fetches news only

    Returns:
        Dict with keys: insider, analyst, price_target, earnings, news
        (None/empty for unavailable data)
    """
    import asyncio
    from datetime import timedelta

    from src.external.finnhub_client import FinnhubClient
    from src.external.marketaux_client import MarketauxClient
    from src.external.ticker_mapping import get_news_query, supports_equity_features

    result: dict = {
        "insider": None,
        "analyst": None,
        "price_target": None,
        "earnings": [],
        "news": [],
    }

    # H4 fix: tz-aware datetime so comparisons inside provider clients
    # (Finnhub/Marketaux) don't TypeError. Naive datetime was silently
    # caught upstream and replaced sentiment data with 0.0 placeholders.
    now = datetime.now(UTC)
    _end = end_date or now
    _start = start_date or (now - timedelta(days=180))

    try:
        news_query = get_news_query(epic)

        if supports_equity_features(epic):
            # Tier 1: stocks (NVDA, TSLA) — all 5 features
            finnhub = FinnhubClient()
            marketaux = MarketauxClient()

            insider_start = _start - timedelta(days=180)

            insider, analyst, price_target, earnings, news = await asyncio.gather(
                finnhub.get_insider_sentiment(epic, insider_start, _end),
                finnhub.get_analyst_recommendations(epic),
                finnhub.get_price_target(epic),
                finnhub.get_earnings_calendar(epic, _end, _end + timedelta(days=30)),
                marketaux.get_news_sentiment(news_query or epic, limit=100, days=30),
                return_exceptions=True,
            )

            result["insider"] = insider if not isinstance(insider, Exception) else None
            result["analyst"] = analyst if not isinstance(analyst, Exception) else None
            result["price_target"] = (
                price_target if not isinstance(price_target, Exception) else None
            )
            result["earnings"] = earnings if isinstance(earnings, list) else []
            result["news"] = news if isinstance(news, list) else []

            await finnhub.close()
            await marketaux.close()

        elif news_query:
            # Tier 2: non-equity assets — news sentiment only
            marketaux = MarketauxClient()
            try:
                news = await marketaux.get_news_sentiment(news_query, limit=50, days=30)
                result["news"] = news if isinstance(news, list) else []
            except Exception:
                pass
            await marketaux.close()

    except Exception as e:
        logger.warning(f"Sentiment data fetch failed for {epic}: {e}")

    return result


class FeatureBuilder:
    """
    Orchestrates the full feature engineering pipeline.

    Pipeline:
    1. Load OHLC data via DataAccessLayer
    2. Compute technical indicators
    3. Normalize features (rolling z-score)
    4. Optionally align multi-timeframe features
    5. Detect market regime
    6. Return FeatureMatrix ready for ML
    """

    def __init__(
        self,
        data_access: DataAccessLayer | None = None,
        normalizer_window: int = 252,
    ):
        """
        Args:
            data_access: DataAccessLayer instance (creates one if None)
            normalizer_window: Rolling window for z-score normalization
        """
        self.data_access = data_access or DataAccessLayer()
        self.normalizer_window = normalizer_window

    def build_features(
        self,
        epic: str,
        timeframe: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        config: AssetFeatureConfig | None = None,
        include_regime: bool = True,
        normalize: bool = True,
        multi_timeframe: bool = False,
        include_sentiment: bool = False,
        sentiment_data: dict | None = None,
        include_macro: bool = False,
        macro_df: pl.DataFrame | None = None,
        sil_data: "SILData | None" = None,
        cross_asset: bool = False,
    ) -> tuple[pl.DataFrame, FeatureMatrix]:
        """
        Build complete feature matrix for an asset.

        Args:
            epic: Asset epic (XAUUSD, BTCUSD, US500)
            timeframe: Primary timeframe (1h, 4h, 1d)
            start_date: Start date for data
            end_date: End date for data
            config: Asset feature config (auto-detected if None)
            include_regime: Include regime detection
            normalize: Apply feature normalization
            multi_timeframe: Include higher-timeframe features
            include_sentiment: Include sentiment features
            sentiment_data: Pre-fetched sentiment data from fetch_sentiment_data().
                If include_sentiment=True and this is None, placeholder columns are added.
            include_macro: Include macro features (VIX, DXY, 10Y yield)
            macro_df: Pre-fetched macro DataFrame from MacroDataClient.get_macro_data().
                If include_macro=True and this is None, fetches automatically.

        Returns:
            Tuple of (DataFrame with all features, FeatureMatrix metadata)
        """
        if config is None:
            config = get_asset_config(epic)

        params = config.technical_params or DEFAULT_TECHNICAL_PARAMS

        # Step 1: Load OHLC data
        logger.info(f"Loading data for {epic}/{timeframe}...")
        df = self.data_access.get_candles(
            epic=epic,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        if df.is_empty():
            logger.warning(f"No data found for {epic}/{timeframe}")
            return df, FeatureMatrix(
                epic=epic,
                timeframe=timeframe,
                feature_names=[],
                num_rows=0,
                num_features=0,
            )

        initial_cols = set(df.columns)
        logger.info(f"Loaded {len(df)} bars for {epic}/{timeframe}")

        # Step 2: Compute technical indicators
        df = self._add_technical_indicators(df, params)

        # Step 3: Sentiment features (sync, uses pre-fetched data)
        if include_sentiment:
            df = self._apply_sentiment_features(df, epic, sentiment_data)

        # Step 4: Macro features (VIX, DXY, 10Y yield)
        if include_macro:
            df = self._add_macro_features(df, macro_df)

        # Step 5: SIL features (Signal Intelligence Layer)
        from src.features.sil_features import compute_sil_features

        df = compute_sil_features(df, sil_data)

        # Step 5.5: Cross-asset correlation features
        cross_asset_cols: list[str] = []
        if cross_asset and get_settings().cross_asset_enabled:
            try:
                from src.features.cross_asset import CrossAssetEngine
                from src.utils.constants import ASSET_CLUSTERS

                related_epics = ASSET_CLUSTERS.get(epic, [])
                if related_epics:
                    engine = CrossAssetEngine()
                    related_dfs = {}
                    for rel_epic in related_epics:
                        try:
                            rel_df = self.data_access.get_candles(
                                epic=rel_epic,
                                timeframe=timeframe,
                                start_date=start_date,
                                end_date=end_date,
                            )
                            if rel_df is not None and len(rel_df) >= 50:
                                related_dfs[rel_epic] = rel_df
                        except Exception as e:
                            logger.debug(f"[{epic}] Failed to load {rel_epic}: {e}")

                    if related_dfs:
                        cols_before = set(df.columns)
                        df = engine.build_cross_asset_features(
                            main_df=df, epic=epic, related_dfs=related_dfs
                        )
                        cross_asset_cols = [c for c in df.columns if c not in cols_before]
                        logger.info(f"[{epic}] Added {len(cross_asset_cols)} cross-asset features")
            except Exception as e:
                logger.warning(f"[{epic}] Cross-asset features failed: {e}")

        # Step 6: Multi-timeframe alignment (optional)
        if multi_timeframe and config.additional_timeframes:
            df = self._add_multi_timeframe_features(
                df, epic, config.additional_timeframes, params, start_date, end_date
            )

        # Step 7: Regime detection + one-hot encoding for ML
        if include_regime:
            detector = RegimeDetector()
            if "adx" in df.columns and f"ema_{detector.ema_period}" in df.columns:
                df = detector.detect(df)
                df = self._add_regime_features(df)

        # Step 8: Normalize features
        feature_cols = [c for c in df.columns if c not in initial_cols and c != "regime"]

        if normalize and feature_cols:
            # Log transform volume-based features
            volume_cols = [c for c in feature_cols if "volume" in c or c == "obv"]
            df = FeatureNormalizer.normalize_features(
                df,
                feature_columns=feature_cols,
                window=self.normalizer_window,
                log_columns=volume_cols if volume_cols else None,
            )

        # Collect final feature names (all non-OHLCV, non-metadata columns)
        metadata_cols = {
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "epic",
            "timeframe",
            "source",
        }
        all_feature_names = [c for c in df.columns if c not in metadata_cols]

        # Build metadata
        matrix_meta = FeatureMatrix(
            epic=epic,
            timeframe=timeframe,
            feature_names=all_feature_names,
            target_column=None,
            num_rows=len(df),
            num_features=len(all_feature_names),
            start_date=df["timestamp"].min(),
            end_date=df["timestamp"].max(),
            regime_column="regime" if "regime" in df.columns else None,
            cross_asset_features=cross_asset_cols,
        )

        logger.info(
            f"Feature matrix built: {matrix_meta.num_rows} rows x "
            f"{matrix_meta.num_features} features for {epic}/{timeframe}"
        )

        return df, matrix_meta

    def build_features_from_df(
        self,
        df: pl.DataFrame,
        epic: str,
        timeframe: str,
        config: AssetFeatureConfig | None = None,
        include_regime: bool = True,
        normalize: bool = True,
        sil_data: "SILData | None" = None,  # NEW: sentiment/macro from Signal Intelligence Layer
    ) -> tuple[pl.DataFrame, FeatureMatrix]:
        """
        Build features from an existing DataFrame (no data loading).
        Useful for testing and when data is already loaded.

        Args:
            df: DataFrame with OHLCV columns
            epic: Asset epic
            timeframe: Timeframe
            config: Asset feature config
            include_regime: Include regime detection
            normalize: Apply normalization

        Returns:
            Tuple of (DataFrame with features, FeatureMatrix metadata)
        """
        if config is None:
            config = get_asset_config(epic)

        params = config.technical_params or DEFAULT_TECHNICAL_PARAMS
        initial_cols = set(df.columns)

        # Technical indicators
        df = self._add_technical_indicators(df, params)

        # Regime + one-hot encoding for ML
        if include_regime:
            detector = RegimeDetector()
            if "adx" in df.columns and f"ema_{detector.ema_period}" in df.columns:
                df = detector.detect(df)
                df = self._add_regime_features(df)

        # SIL features (sentiment/macro from Signal Intelligence Layer)
        from src.features.sil_features import compute_sil_features

        df = compute_sil_features(df, sil_data)

        # Normalize
        feature_cols = [c for c in df.columns if c not in initial_cols and c != "regime"]

        if normalize and feature_cols:
            volume_cols = [c for c in feature_cols if "volume" in c or c == "obv"]
            df = FeatureNormalizer.normalize_features(
                df,
                feature_columns=feature_cols,
                window=self.normalizer_window,
                log_columns=volume_cols if volume_cols else None,
            )

        metadata_cols = {
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "epic",
            "timeframe",
            "source",
        }
        all_feature_names = [c for c in df.columns if c not in metadata_cols]

        matrix_meta = FeatureMatrix(
            epic=epic,
            timeframe=timeframe,
            feature_names=all_feature_names,
            num_rows=len(df),
            num_features=len(all_feature_names),
            start_date=df["timestamp"].min() if "timestamp" in df.columns else None,
            end_date=df["timestamp"].max() if "timestamp" in df.columns else None,
            regime_column="regime" if "regime" in df.columns else None,
        )

        return df, matrix_meta

    def _add_technical_indicators(self, df: pl.DataFrame, params: dict) -> pl.DataFrame:
        """Add all technical indicators based on params."""
        ti = TechnicalIndicators

        df = ti.add_ema(df, periods=params.get("ema_periods", [8, 21, 50, 200]))
        df = ti.add_ema_crossovers(df)
        df = ti.add_macd(
            df,
            fast_period=params.get("macd_fast", 12),
            slow_period=params.get("macd_slow", 26),
            signal_period=params.get("macd_signal", 9),
        )
        df = ti.add_adx(df, period=params.get("adx_period", 14))
        rsi_period = params.get("rsi_period", 14)
        bb_period = params.get("bb_period", 20)

        df = ti.add_rsi(df, period=rsi_period)
        df = ti.add_bollinger_bands(
            df,
            period=bb_period,
            num_std=params.get("bb_std", 2.0),
        )

        # Advanced mean reversion
        df = ti.add_stochastic_rsi(df, rsi_period=rsi_period)
        df = ti.add_bollinger_squeeze(df, bb_period=bb_period)
        df = ti.add_rsi_divergence(df, rsi_period=rsi_period)

        df = ti.add_atr(df, period=params.get("atr_period", 14))
        df = ti.add_historical_volatility(df, period=params.get("hvol_period", 20))

        # Volume indicators (only if volume column has data)
        if "volume" in df.columns:
            has_volume = df["volume"].null_count() < len(df) and df["volume"].sum() > 0
            if has_volume:
                df = ti.add_obv(df)
                df = ti.add_volume_sma_ratio(df)
                df = ti.add_vwap(df)

        df = ti.add_returns(df, periods=params.get("return_periods", [1, 5, 20]))
        df = ti.add_price_action(df)

        # Session features
        df = ti.add_session_features(df)

        # NOTE: Candlestick (8) and Fibonacci (7) features removed in Phase 2.1
        # to reduce overfitting (15 features with low predictive value)
        # Methods kept in technical.py for potential future use

        # Keltner Channel + True Squeeze detection
        df = KeltnerChannel.add_keltner(
            df,
            ema_period=params.get("kc_ema_period", 20),
            atr_period=params.get("atr_period", 14),
            multiplier=params.get("kc_multiplier", 1.5),
        )
        df = KeltnerChannel.add_true_squeeze(df)

        # VWAP SD bands (requires volume)
        if "volume" in df.columns:
            has_volume = df["volume"].null_count() < len(df) and df["volume"].sum() > 0
            if has_volume:
                df = VWAPBands.add_vwap_bands(df)

        # Market structure (BOS/CHoCH)
        if "high" in df.columns and "low" in df.columns and "close" in df.columns:
            detector = MarketStructureDetector(
                pivot_lookback=params.get("structure_pivot_lookback", 5),
            )
            df = detector.add_all(df)

        return df

    @staticmethod
    def _add_regime_features(df: pl.DataFrame) -> pl.DataFrame:
        """One-hot encode regime column for XGBoost consumption.

        Creates 3 binary features: regime_trending_up, regime_trending_down, regime_ranging.
        These allow XGBoost to learn regime-specific splits without separate models.
        """
        if "regime" not in df.columns:
            return df

        df = df.with_columns(
            [
                (pl.col("regime") == "trending_up").cast(pl.Int32).alias("regime_trending_up"),
                (pl.col("regime") == "trending_down").cast(pl.Int32).alias("regime_trending_down"),
                (pl.col("regime") == "ranging").cast(pl.Int32).alias("regime_ranging"),
            ]
        )
        return df

    def _add_multi_timeframe_features(
        self,
        base_df: pl.DataFrame,
        epic: str,
        additional_timeframes: list[str],
        params: dict,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> pl.DataFrame:
        """Load and align higher-timeframe features."""
        higher_tf_dfs = {}

        for tf in additional_timeframes:
            tf_df = self.data_access.get_candles(
                epic=epic,
                timeframe=tf,
                start_date=start_date,
                end_date=end_date,
            )

            if tf_df.is_empty():
                logger.warning(f"No data for {epic}/{tf}, skipping")
                continue

            # Add technical indicators to higher TF
            tf_df = self._add_technical_indicators(tf_df, params)
            higher_tf_dfs[tf] = tf_df

        if higher_tf_dfs:
            base_df = TimeframeAligner.align(
                base_df, higher_tf_dfs, base_timeframe=params.get("primary_timeframe", "1h")
            )

        return base_df

    def _apply_sentiment_features(
        self,
        df: pl.DataFrame,
        epic: str,
        sentiment_data: dict | None = None,
    ) -> pl.DataFrame:
        """
        Apply sentiment features to DataFrame (sync, no I/O).

        Tier 1 (NVDA, TSLA): all 5 features from pre-fetched data
        Tier 2 (all others): news_sentiment_avg only, 4 placeholders

        Args:
            df: DataFrame with OHLC data
            epic: Asset epic
            sentiment_data: Pre-fetched dict from fetch_sentiment_data().
                If None, adds placeholder columns for all 5 features.

        Returns:
            DataFrame with 5 sentiment feature columns
        """
        from src.external.ticker_mapping import supports_equity_features

        if sentiment_data is None:
            # No data fetched: add 5 placeholder columns
            return df.with_columns(
                [
                    pl.lit(None).alias("insider_mspr").cast(pl.Float64),
                    pl.lit(0).alias("analyst_consensus"),
                    pl.lit(0.0).alias("price_target_upside"),
                    pl.lit(0).alias("earnings_flag"),
                    pl.lit(0.0).alias("news_sentiment_avg"),
                ]
            )

        try:
            news = sentiment_data.get("news", [])

            if supports_equity_features(epic):
                # Tier 1: stocks → all 5 features
                insider = sentiment_data.get("insider")
                analyst = sentiment_data.get("analyst")
                price_target = sentiment_data.get("price_target")
                earnings = sentiment_data.get("earnings", [])

                df = SentimentFeatures.add_insider_mspr(df, [insider] if insider else [])
                df = SentimentFeatures.add_analyst_consensus(df, analyst)
                df = SentimentFeatures.add_price_target_upside(df, price_target)
                df = SentimentFeatures.add_earnings_flag(df, earnings)
                df = SentimentFeatures.add_news_sentiment(df, news, window_days=7)
                logger.info(f"Added 5 sentiment features for {epic} (Tier 1)")
            else:
                # Tier 2: non-equity → news_sentiment_avg only, 4 placeholders
                df = df.with_columns(
                    [
                        pl.lit(None).alias("insider_mspr").cast(pl.Float64),
                        pl.lit(0).alias("analyst_consensus"),
                        pl.lit(0.0).alias("price_target_upside"),
                        pl.lit(0).alias("earnings_flag"),
                    ]
                )
                df = SentimentFeatures.add_news_sentiment(df, news, window_days=7)
                logger.info(f"Added news sentiment for {epic} (Tier 2)")

            return df

        except Exception as e:
            logger.warning(f"Sentiment feature apply failed for {epic}: {e}")
            return df.with_columns(
                [
                    pl.lit(None).alias("insider_mspr").cast(pl.Float64),
                    pl.lit(0).alias("analyst_consensus"),
                    pl.lit(0.0).alias("price_target_upside"),
                    pl.lit(0).alias("earnings_flag"),
                    pl.lit(0.0).alias("news_sentiment_avg"),
                ]
            )

    _MACRO_FEATURE_COLS = [
        "vix_close",
        "vix_change_5d",
        "dxy_close",
        "dxy_change_5d",
        "yield_10y_close",
        "yield_10y_change_5d",
    ]

    def _add_macro_features(
        self,
        df: pl.DataFrame,
        macro_df: pl.DataFrame | None = None,
    ) -> pl.DataFrame:
        """
        Add macro features (VIX, DXY, 10Y yield) via asof join.

        Daily macro data is aligned to hourly bars using backward strategy:
        each bar gets the most recent macro observation <= its date.

        Args:
            df: OHLCV DataFrame with "timestamp" column
            macro_df: Pre-fetched macro data. If None, fetches automatically.

        Returns:
            DataFrame with 6 additional macro feature columns.
        """
        if macro_df is None:
            try:
                from src.external.macro_client import MacroDataClient

                client = MacroDataClient()
                macro_df = client.get_macro_data()
            except Exception as e:
                logger.warning(f"Macro data fetch failed: {e}")

        if macro_df is None or macro_df.is_empty():
            logger.info("No macro data available, adding placeholder columns")
            return df.with_columns([pl.lit(0.0).alias(c) for c in self._MACRO_FEATURE_COLS])

        try:
            # Extract date from timestamp for the asof join
            df = df.with_columns(pl.col("timestamp").cast(pl.Date).alias("_macro_date"))

            # Ensure macro_df is sorted by date
            macro_df = macro_df.sort("date")

            # Keep only the columns we need from macro_df
            macro_cols = ["date"] + [c for c in self._MACRO_FEATURE_COLS if c in macro_df.columns]
            macro_subset = macro_df.select(macro_cols)

            # Asof join: each bar gets the most recent macro row <= its date
            df = df.join_asof(
                macro_subset,
                left_on="_macro_date",
                right_on="date",
                strategy="backward",
            )

            # Drop temporary join columns
            drop_cols = ["_macro_date"]
            if "date" in df.columns:
                drop_cols.append("date")
            df = df.drop(drop_cols)

            # Fill any missing macro columns with 0.0
            for col in self._MACRO_FEATURE_COLS:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(0.0).alias(col))
                else:
                    df = df.with_columns(pl.col(col).fill_null(0.0).fill_nan(0.0))

            n_macro = sum(1 for c in self._MACRO_FEATURE_COLS if c in df.columns)
            logger.info(f"Added {n_macro} macro features via asof join")
            return df

        except Exception as e:
            logger.warning(f"Macro feature join failed: {e}")
            return df.with_columns([pl.lit(0.0).alias(c) for c in self._MACRO_FEATURE_COLS])
