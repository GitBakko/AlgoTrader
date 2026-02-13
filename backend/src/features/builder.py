"""
Feature builder orchestrator.
Coordinates the full feature engineering pipeline:
OHLC data -> technical indicators -> normalization -> regime detection -> FeatureMatrix
"""

from datetime import datetime

import polars as pl
from loguru import logger

from src.data.data_access import DataAccessLayer
from src.features.alignment import TimeframeAligner
from src.features.asset_config import DEFAULT_TECHNICAL_PARAMS, get_asset_config
from src.features.keltner import KeltnerChannel
from src.features.market_structure import MarketStructureDetector
from src.features.vwap_bands import VWAPBands
from src.features.normalizer import FeatureNormalizer
from src.features.regime import RegimeDetector
from src.features.schemas import AssetFeatureConfig, FeatureMatrix
from src.features.technical import TechnicalIndicators


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

        # Step 3: Multi-timeframe alignment (optional)
        if multi_timeframe and config.additional_timeframes:
            df = self._add_multi_timeframe_features(
                df, epic, config.additional_timeframes, params, start_date, end_date
            )

        # Step 4: Regime detection
        if include_regime:
            detector = RegimeDetector()
            if "adx" in df.columns and f"ema_{detector.ema_period}" in df.columns:
                df = detector.detect(df)

        # Step 5: Normalize features
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
        metadata_cols = {"timestamp", "open", "high", "low", "close", "volume",
                         "epic", "timeframe", "source"}
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

        # Regime
        if include_regime:
            detector = RegimeDetector()
            if "adx" in df.columns and f"ema_{detector.ema_period}" in df.columns:
                df = detector.detect(df)

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

        metadata_cols = {"timestamp", "open", "high", "low", "close", "volume",
                         "epic", "timeframe", "source"}
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

    def _add_technical_indicators(
        self, df: pl.DataFrame, params: dict
    ) -> pl.DataFrame:
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

        # Candlestick patterns (8 binary features)
        df = ti.add_candlestick_patterns(df)

        # Fibonacci cluster zones (7 features)
        df = ti.add_fibonacci_levels(
            df,
            swing_lookback=params.get("fib_swing_lookback", 20),
            atr_period=params.get("atr_period", 14),
        )

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
