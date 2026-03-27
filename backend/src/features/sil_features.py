"""
Signal Intelligence Layer — Feature computation.

Adds 12 sil_* columns to the feature DataFrame.
All features are fill_null(0.0) for XGBoost compatibility.
"""

import polars as pl

from src.external.sil_schemas import SILData

SIL_FEATURE_COLS = [
    "sil_fear_greed_value",
    "sil_fear_greed_gold_bias",
    "sil_real_yield_10y",
    "sil_breakeven_inflation",
    "sil_gold_bullish_yield",
    "sil_alpha_sentiment_score",
    "sil_alpha_bullish_ratio",
    "sil_cot_net_position_norm",
    "sil_cot_z_score",
    "sil_cot_institutional_bull",
    "sil_social_bullish_ratio",
    "sil_composite_score",
]

# Composite score weights
_W_FEAR_GREED = 0.30
_W_YIELD = 0.25
_W_SENTIMENT = 0.20
_W_COT = 0.15
_W_SOCIAL = 0.10


def compute_sil_features(
    df: pl.DataFrame,
    sil_data: SILData | None,
) -> pl.DataFrame:
    """
    Add 12 SIL feature columns to DataFrame.

    Args:
        df: Feature DataFrame (one row per candle/bar).
        sil_data: Aggregated SIL data. None → all features = 0.0.

    Returns:
        DataFrame with 12 additional sil_* columns.
    """
    if sil_data is None:
        return _add_zero_columns(df)

    fg = sil_data.fear_greed
    fred = sil_data.fred
    av = sil_data.alpha_vantage
    cot = sil_data.cot
    social = sil_data.social

    # Compute individual features
    fear_greed_value = fg.normalized
    fear_greed_gold_bias = fg.gold_bias
    real_yield = fred.real_yield_10y if fred.real_yield_10y is not None else 0.0
    breakeven = fred.breakeven_inflation if fred.breakeven_inflation is not None else 0.0
    gold_bullish_yield = 1.0 if real_yield < -1.0 else 0.0
    alpha_sentiment = av.average_sentiment_score
    alpha_bullish = av.bullish_ratio
    cot_net_norm = cot.net_position_normalized
    cot_z = cot.z_score_4w
    cot_bull = 1.0 if cot.is_institutional_bullish else 0.0
    social_bullish = social.combined_bullish_ratio

    # Composite score (weighted average of normalized signals)
    composite = _compute_composite(
        fear_greed_value=fear_greed_value,
        gold_bullish_yield=gold_bullish_yield,
        alpha_bullish=alpha_bullish,
        cot_net_norm=cot_net_norm,
        social_bullish=social_bullish,
    )

    df = df.with_columns(
        [
            pl.lit(fear_greed_value).alias("sil_fear_greed_value"),
            pl.lit(fear_greed_gold_bias).alias("sil_fear_greed_gold_bias"),
            pl.lit(real_yield).alias("sil_real_yield_10y"),
            pl.lit(breakeven).alias("sil_breakeven_inflation"),
            pl.lit(gold_bullish_yield).alias("sil_gold_bullish_yield"),
            pl.lit(alpha_sentiment).alias("sil_alpha_sentiment_score"),
            pl.lit(alpha_bullish).alias("sil_alpha_bullish_ratio"),
            pl.lit(cot_net_norm).alias("sil_cot_net_position_norm"),
            pl.lit(cot_z).alias("sil_cot_z_score"),
            pl.lit(cot_bull).alias("sil_cot_institutional_bull"),
            pl.lit(social_bullish).alias("sil_social_bullish_ratio"),
            pl.lit(composite).alias("sil_composite_score"),
        ]
    )

    return df


def _add_zero_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Add all 12 SIL columns with 0.0 values."""
    return df.with_columns([pl.lit(0.0).alias(col) for col in SIL_FEATURE_COLS])


def _compute_composite(
    fear_greed_value: float,
    gold_bullish_yield: float,
    alpha_bullish: float,
    cot_net_norm: float,
    social_bullish: float,
) -> float:
    """
    Compute weighted composite score.

    All inputs are [0, 1] range (or converted).
    Output: [0, 1] where 1 = all signals bullish.

    Weights: F&G 30%, Yield 25%, Sentiment 20%, COT 15%, Social 10%
    """
    # Normalize F&G: value is already [0,1] where 0=fear, 1=greed
    fg_signal = fear_greed_value

    # Yield: gold_bullish_yield is binary (0 or 1)
    yield_signal = gold_bullish_yield

    # Sentiment: alpha_bullish is already [0,1]
    sentiment_signal = alpha_bullish

    # COT: net_norm is [-1, 1], convert to [0, 1]
    cot_signal = (cot_net_norm + 1.0) / 2.0

    # Social: already [0, 1]
    social_signal = social_bullish

    composite = (
        fg_signal * _W_FEAR_GREED
        + yield_signal * _W_YIELD
        + sentiment_signal * _W_SENTIMENT
        + cot_signal * _W_COT
        + social_signal * _W_SOCIAL
    )

    return round(max(0.0, min(1.0, composite)), 4)
