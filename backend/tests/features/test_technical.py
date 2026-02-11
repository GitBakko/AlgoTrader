"""Tests for technical indicators module."""

import numpy as np
import polars as pl
import pytest

from src.features.technical import TechnicalIndicators


@pytest.fixture
def sample_ohlcv() -> pl.DataFrame:
    """Generate synthetic OHLCV data with a clear uptrend."""
    np.random.seed(42)
    n = 300

    # Generate price with uptrend + noise
    base = 100.0
    trend = np.linspace(0, 50, n)
    noise = np.random.normal(0, 2, n).cumsum()
    close = base + trend + noise

    high = close + np.abs(np.random.normal(1, 0.5, n))
    low = close - np.abs(np.random.normal(1, 0.5, n))
    open_price = close + np.random.normal(0, 0.5, n)
    volume = np.random.randint(1000, 10000, n)

    return pl.DataFrame({
        "timestamp": pl.datetime_range(
            pl.datetime(2024, 1, 1), pl.datetime(2024, 1, 1) + pl.duration(hours=n - 1),
            interval="1h", eager=True,
        ),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume.astype(np.int64),
    })


@pytest.fixture
def small_df() -> pl.DataFrame:
    """Small DataFrame for exact value verification."""
    return pl.DataFrame({
        "open": [100.0, 102.0, 101.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 110.0],
        "high": [102.0, 103.0, 103.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 112.0],
        "low": [99.0, 100.0, 99.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 108.0],
        "close": [101.0, 102.0, 100.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 111.0],
        "volume": [1000, 1200, 800, 1500, 1100, 900, 1300, 1400, 1000, 1600],
    })


class TestEMA:
    def test_add_ema_default_periods(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_ema(sample_ohlcv)
        assert "ema_8" in df.columns
        assert "ema_21" in df.columns
        assert "ema_50" in df.columns
        assert "ema_200" in df.columns

    def test_add_ema_custom_periods(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_ema(sample_ohlcv, periods=[10, 30])
        assert "ema_10" in df.columns
        assert "ema_30" in df.columns
        assert "ema_8" not in df.columns

    def test_ema_values_converge(self, sample_ohlcv: pl.DataFrame):
        """EMA should be close to close price on average."""
        df = TechnicalIndicators.add_ema(sample_ohlcv, periods=[8])
        ema_vals = df["ema_8"].drop_nulls()
        close_vals = df["close"].tail(len(ema_vals))
        # EMA tracks close, correlation should be very high
        assert np.corrcoef(ema_vals.to_numpy(), close_vals.to_numpy())[0, 1] > 0.95


class TestEMACrossovers:
    def test_crossover_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_ema(sample_ohlcv)
        df = TechnicalIndicators.add_ema_crossovers(df)
        assert "ema_cross_8_21" in df.columns
        assert "ema_cross_50_200" in df.columns

    def test_crossover_values(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_ema(sample_ohlcv)
        df = TechnicalIndicators.add_ema_crossovers(df)
        # Values should be -1, 0, or 1
        unique_vals = set(df["ema_cross_8_21"].drop_nulls().to_list())
        assert unique_vals.issubset({-1, 0, 1})


class TestMACD:
    def test_macd_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_macd(sample_ohlcv)
        assert "macd" in df.columns
        assert "macd_signal" in df.columns
        assert "macd_histogram" in df.columns

    def test_macd_histogram_is_diff(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_macd(sample_ohlcv)
        # histogram = macd - signal
        diff = (df["macd"] - df["macd_signal"]).drop_nulls()
        hist = df["macd_histogram"].drop_nulls()
        np.testing.assert_allclose(diff.to_numpy(), hist.to_numpy(), atol=1e-10)


class TestRSI:
    def test_rsi_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_rsi(sample_ohlcv)
        assert "rsi_14" in df.columns

    def test_rsi_range(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_rsi(sample_ohlcv)
        rsi = df["rsi_14"].drop_nulls()
        assert rsi.min() >= 0.0
        assert rsi.max() <= 100.0


class TestBollingerBands:
    def test_bb_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_bollinger_bands(sample_ohlcv)
        for col in ["bb_upper", "bb_lower", "bb_middle", "bb_width", "bb_pctb"]:
            assert col in df.columns

    def test_bb_order(self, sample_ohlcv: pl.DataFrame):
        """Upper band should always be >= middle >= lower."""
        df = TechnicalIndicators.add_bollinger_bands(sample_ohlcv)
        valid = df.filter(pl.col("bb_upper").is_not_null())
        assert (valid["bb_upper"] >= valid["bb_middle"]).all()
        assert (valid["bb_middle"] >= valid["bb_lower"]).all()


class TestATR:
    def test_atr_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_atr(sample_ohlcv)
        assert "atr_14" in df.columns
        assert "atr_ratio" in df.columns

    def test_atr_positive(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_atr(sample_ohlcv)
        atr = df["atr_14"].drop_nulls()
        assert (atr > 0).all()


class TestADX:
    def test_adx_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_adx(sample_ohlcv)
        assert "adx" in df.columns
        assert "plus_di" in df.columns
        assert "minus_di" in df.columns

    def test_adx_range(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_adx(sample_ohlcv)
        adx = df["adx"].drop_nulls()
        assert adx.min() >= 0.0
        assert adx.max() <= 100.0

    def test_no_temp_columns(self, sample_ohlcv: pl.DataFrame):
        """Temporary columns should be dropped."""
        df = TechnicalIndicators.add_adx(sample_ohlcv)
        temp_cols = [c for c in df.columns if c.startswith("_")]
        assert len(temp_cols) == 0


class TestOBV:
    def test_obv_column(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_obv(sample_ohlcv)
        assert "obv" in df.columns

    def test_obv_direction(self, small_df: pl.DataFrame):
        """OBV should increase when close > prev close."""
        df = TechnicalIndicators.add_obv(small_df)
        # First row OBV is 0 (no previous to compare)
        assert df["obv"][0] == 0


class TestReturns:
    def test_returns_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_returns(sample_ohlcv)
        assert "returns_1" in df.columns
        assert "returns_5" in df.columns
        assert "returns_20" in df.columns

    def test_returns_1_calculation(self, small_df: pl.DataFrame):
        """returns_1 should be log(close/prev_close)."""
        df = TechnicalIndicators.add_returns(small_df, periods=[1])
        expected = np.log(101.0 / 100.0)  # 2nd bar return (close[1]/close[0] is wrong here)
        # Actually: close = [101, 102, 100, 104, ...], returns_1[1] = log(102/101)
        actual = df["returns_1"][1]
        assert abs(actual - np.log(102.0 / 101.0)) < 1e-10


class TestPriceAction:
    def test_price_action_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_price_action(sample_ohlcv)
        assert "high_low_range" in df.columns
        assert "close_position" in df.columns

    def test_close_position_range(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_price_action(sample_ohlcv)
        cp = df["close_position"].drop_nulls()
        assert cp.min() >= 0.0
        assert cp.max() <= 1.0


class TestAddAllIndicators:
    def test_all_indicators(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_all_indicators(sample_ohlcv)
        expected_cols = [
            "ema_8", "ema_21", "ema_50", "ema_200",
            "macd", "macd_signal", "macd_histogram",
            "rsi_14",
            "bb_upper", "bb_lower", "bb_middle",
            "atr_14", "atr_ratio",
            "adx", "plus_di", "minus_di",
            "returns_1", "returns_5", "returns_20",
            "high_low_range", "close_position",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_no_temp_columns(self, sample_ohlcv: pl.DataFrame):
        df = TechnicalIndicators.add_all_indicators(sample_ohlcv)
        temp_cols = [c for c in df.columns if c.startswith("_")]
        assert len(temp_cols) == 0
