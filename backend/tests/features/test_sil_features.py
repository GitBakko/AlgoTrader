"""Tests for SIL feature computation."""

import polars as pl
import pytest

from src.external.sil_schemas import (
    AlphaVantageData,
    COTData,
    FREDData,
    FearGreedData,
    SILData,
    SocialSentimentData,
)
from src.features.sil_features import (
    SIL_FEATURE_COLS,
    _compute_composite,
    compute_sil_features,
)


@pytest.fixture
def sample_df():
    """Minimal OHLCV DataFrame."""
    return pl.DataFrame({
        "timestamp": pl.Series(["2026-03-07", "2026-03-08", "2026-03-09"]).str.to_datetime(),
        "close": [2900.0, 2910.0, 2920.0],
    })


@pytest.fixture
def full_sil_data():
    """Complete SILData with realistic values."""
    return SILData(
        fear_greed=FearGreedData(
            value=25.0, normalized=0.25,
            is_extreme_fear=False, gold_bias=0.5,
        ),
        fred=FREDData(
            real_yield_10y=-1.5,
            breakeven_inflation=2.3,
            fed_funds_rate=5.25,
        ),
        alpha_vantage=AlphaVantageData(
            average_sentiment_score=0.3,
            bullish_ratio=0.7,
        ),
        cot=COTData(
            noncomm_long=250000, noncomm_short=150000,
            net_position=100000, net_position_normalized=0.6,
            is_institutional_bullish=True, z_score_4w=1.2,
        ),
        social=SocialSentimentData(
            combined_bullish_ratio=0.65,
        ),
    )


class TestComputeSILFeatures:
    def test_none_sil_data_adds_zero_columns(self, sample_df):
        """None SILData → 12 columns all zeros."""
        result = compute_sil_features(sample_df, None)
        assert len(result) == 3
        for col in SIL_FEATURE_COLS:
            assert col in result.columns
            assert result[col].to_list() == [0.0, 0.0, 0.0]

    def test_full_sil_data_adds_12_columns(self, sample_df, full_sil_data):
        """Full SILData → 12 columns with correct values."""
        result = compute_sil_features(sample_df, full_sil_data)
        assert len(result) == 3
        for col in SIL_FEATURE_COLS:
            assert col in result.columns

        # Check specific values
        assert result["sil_fear_greed_value"][0] == 0.25
        assert result["sil_fear_greed_gold_bias"][0] == 0.5
        assert result["sil_real_yield_10y"][0] == -1.5
        assert result["sil_breakeven_inflation"][0] == 2.3
        assert result["sil_gold_bullish_yield"][0] == 1.0  # yield < -1.0
        assert result["sil_alpha_sentiment_score"][0] == 0.3
        assert result["sil_alpha_bullish_ratio"][0] == 0.7
        assert result["sil_cot_net_position_norm"][0] == 0.6
        assert result["sil_cot_z_score"][0] == 1.2
        assert result["sil_cot_institutional_bull"][0] == 1.0
        assert result["sil_social_bullish_ratio"][0] == 0.65

    def test_gold_bullish_yield_negative(self, sample_df):
        """Positive real yield → gold_bullish_yield = 0."""
        data = SILData(fred=FREDData(real_yield_10y=2.0))
        result = compute_sil_features(sample_df, data)
        assert result["sil_gold_bullish_yield"][0] == 0.0

    def test_gold_bullish_yield_very_negative(self, sample_df):
        """Very negative yield → gold_bullish_yield = 1."""
        data = SILData(fred=FREDData(real_yield_10y=-2.0))
        result = compute_sil_features(sample_df, data)
        assert result["sil_gold_bullish_yield"][0] == 1.0

    def test_cot_bearish(self, sample_df):
        """Bearish COT → institutional_bull = 0."""
        data = SILData(cot=COTData(is_institutional_bullish=False))
        result = compute_sil_features(sample_df, data)
        assert result["sil_cot_institutional_bull"][0] == 0.0

    def test_none_fred_values_default_to_zero(self, sample_df):
        """None FRED values → 0.0 in features."""
        data = SILData(fred=FREDData())  # All None
        result = compute_sil_features(sample_df, data)
        assert result["sil_real_yield_10y"][0] == 0.0
        assert result["sil_breakeven_inflation"][0] == 0.0

    def test_preserves_existing_columns(self, sample_df):
        """Original columns are preserved."""
        result = compute_sil_features(sample_df, None)
        assert "timestamp" in result.columns
        assert "close" in result.columns
        assert len(result.columns) == 2 + 12


class TestCompositeScore:
    def test_all_bullish(self):
        """All signals bullish → composite near 1.0."""
        score = _compute_composite(
            fear_greed_value=1.0,
            gold_bullish_yield=1.0,
            alpha_bullish=1.0,
            cot_net_norm=1.0,
            social_bullish=1.0,
        )
        assert score == 1.0

    def test_all_bearish(self):
        """All signals bearish → composite near 0.0."""
        score = _compute_composite(
            fear_greed_value=0.0,
            gold_bullish_yield=0.0,
            alpha_bullish=0.0,
            cot_net_norm=-1.0,
            social_bullish=0.0,
        )
        assert score == 0.0

    def test_neutral(self):
        """All signals neutral → composite near 0.5."""
        score = _compute_composite(
            fear_greed_value=0.5,
            gold_bullish_yield=0.0,
            alpha_bullish=0.5,
            cot_net_norm=0.0,
            social_bullish=0.5,
        )
        assert 0.3 <= score <= 0.7

    def test_cot_normalization(self):
        """COT net_norm -1 to +1 is correctly mapped to 0-1."""
        bearish = _compute_composite(0.5, 0.0, 0.5, -1.0, 0.5)
        bullish = _compute_composite(0.5, 0.0, 0.5, 1.0, 0.5)
        assert bullish > bearish

    def test_bounded_0_1(self):
        """Composite is always between 0 and 1."""
        for fg in [0, 0.5, 1]:
            for yield_ in [0, 1]:
                for cot in [-1, 0, 1]:
                    score = _compute_composite(fg, yield_, 0.5, cot, 0.5)
                    assert 0 <= score <= 1


class TestSILFeatureCols:
    def test_12_features(self):
        assert len(SIL_FEATURE_COLS) == 12

    def test_all_prefixed(self):
        for col in SIL_FEATURE_COLS:
            assert col.startswith("sil_"), f"Missing prefix: {col}"
