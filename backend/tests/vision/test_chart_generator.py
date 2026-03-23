# MANTIS-EVOLUTION: Tests for Vision AI chart generator
"""
Tests for MantisChartGenerator and Vision schemas.

TDD approach: tests written first, implementation follows.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.vision.schemas import ChartConfig, VisionReport, VisionSignal
from src.vision.chart_generator import MantisChartGenerator


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def make_ohlc(n: int = 50, base: float = 100.0):
    """Generate synthetic OHLC + volume data for testing."""
    np.random.seed(42)
    noise = np.random.randn(n) * 0.5
    closes = base + np.cumsum(noise)
    opens = closes - np.random.rand(n) * 0.3
    highs = np.maximum(opens, closes) + np.random.rand(n) * 0.5
    lows = np.minimum(opens, closes) - np.random.rand(n) * 0.5
    volumes = np.random.randint(1000, 10000, n).astype(float)
    return opens, highs, lows, closes, volumes


def make_indicators(closes: np.ndarray) -> dict:
    """Generate simple indicator arrays from closes."""
    n = len(closes)
    ema_9 = closes.copy()   # simplified
    ema_21 = closes.copy()
    bb_upper = closes + 2.0
    bb_lower = closes - 2.0
    rsi_14 = np.full(n, 50.0)
    return {
        "ema_9": ema_9,
        "ema_21": ema_21,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "rsi_14": rsi_14,
    }


# ---------------------------------------------------------------------------
# MantisChartGenerator tests
# ---------------------------------------------------------------------------

class TestChartGeneratorBasic:
    """Basic chart generation tests."""

    def test_generate_returns_bytes(self):
        """generate() must return bytes with non-zero length."""
        gen = MantisChartGenerator()
        opens, highs, lows, closes, volumes = make_ohlc()
        dates = list(range(len(closes)))
        result = gen.generate(dates, opens, highs, lows, closes)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_generate_valid_png_signature(self):
        """Generated chart must start with the PNG magic bytes."""
        gen = MantisChartGenerator()
        opens, highs, lows, closes, volumes = make_ohlc()
        dates = list(range(len(closes)))
        result = gen.generate(dates, opens, highs, lows, closes)
        assert result[:4] == b"\x89PNG"

    def test_generate_basic_ohlc(self):
        """Basic OHLC with no optional params produces a valid PNG."""
        gen = MantisChartGenerator()
        opens, highs, lows, closes, volumes = make_ohlc(n=30)
        dates = list(range(30))
        result = gen.generate(dates, opens, highs, lows, closes, title="XAUUSD")
        assert result[:4] == b"\x89PNG"
        assert len(result) > 100  # real chart, not minimal stub

    def test_generate_with_indicators(self):
        """Chart with all indicators (EMA, BB, RSI) produces a valid PNG."""
        gen = MantisChartGenerator()
        opens, highs, lows, closes, volumes = make_ohlc()
        dates = list(range(len(closes)))
        indicators = make_indicators(closes)
        result = gen.generate(
            dates, opens, highs, lows, closes,
            volumes=volumes,
            indicators=indicators,
            title="BTC/USD — indicators",
        )
        assert result[:4] == b"\x89PNG"
        assert len(result) > 100

    def test_generate_with_volume(self):
        """Chart with volume subplot produces a valid PNG."""
        gen = MantisChartGenerator()
        opens, highs, lows, closes, volumes = make_ohlc()
        dates = list(range(len(closes)))
        result = gen.generate(dates, opens, highs, lows, closes, volumes=volumes)
        assert result[:4] == b"\x89PNG"
        assert len(result) > 100

    def test_generate_empty_data(self):
        """Empty OHLC arrays must not raise — returns minimal fallback PNG."""
        gen = MantisChartGenerator()
        result = gen.generate([], [], [], [], [])
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_custom_config(self):
        """Custom width/height are accepted without errors."""
        config = ChartConfig(width=800, height=400, show_rsi=False)
        gen = MantisChartGenerator(config=config)
        opens, highs, lows, closes, volumes = make_ohlc(n=20)
        dates = list(range(20))
        result = gen.generate(dates, opens, highs, lows, closes, volumes=volumes)
        assert result[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# Hash tests
# ---------------------------------------------------------------------------

class TestChartHash:
    """Tests for chart hash generation."""

    def test_chart_hash_deterministic(self):
        """Same PNG bytes always produce the same hash."""
        gen = MantisChartGenerator()
        opens, highs, lows, closes, volumes = make_ohlc()
        dates = list(range(len(closes)))
        png1 = gen.generate(dates, opens, highs, lows, closes)
        png2 = gen.generate(dates, opens, highs, lows, closes)
        assert gen.get_chart_hash(png1) == gen.get_chart_hash(png2)

    def test_chart_hash_different_for_different_data(self):
        """Different market data produces a different hash."""
        gen = MantisChartGenerator()
        opens1, highs1, lows1, closes1, _ = make_ohlc(base=100.0)
        opens2, highs2, lows2, closes2, _ = make_ohlc(base=200.0)
        dates = list(range(50))
        png1 = gen.generate(dates, opens1, highs1, lows1, closes1)
        png2 = gen.generate(dates, opens2, highs2, lows2, closes2)
        assert gen.get_chart_hash(png1) != gen.get_chart_hash(png2)

    def test_chart_hash_length(self):
        """Hash is always 16 hex characters (truncated SHA-256)."""
        gen = MantisChartGenerator()
        opens, highs, lows, closes, _ = make_ohlc(n=10)
        dates = list(range(10))
        png = gen.generate(dates, opens, highs, lows, closes)
        h = gen.get_chart_hash(png)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Minimal PNG fallback
# ---------------------------------------------------------------------------

class TestMinimalPng:
    """Tests for the minimal PNG fallback."""

    def test_minimal_png_valid(self):
        """_minimal_png() must return bytes starting with PNG signature."""
        result = MantisChartGenerator._minimal_png()
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_minimal_png_non_empty(self):
        """Fallback PNG must have non-zero length."""
        result = MantisChartGenerator._minimal_png()
        assert len(result) > 8  # at least signature + one chunk


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchemas:
    """Tests for Vision pydantic schemas."""

    def test_schemas_vision_report(self):
        """VisionReport creates with defaults and validates constraints."""
        report = VisionReport()
        assert report.trend_direction == "NEUTRAL"
        assert report.momentum == "NEUTRAL"
        assert 0.0 <= report.visual_confidence <= 1.0
        assert isinstance(report.key_patterns, list)
        assert isinstance(report.support_levels, list)
        assert isinstance(report.resistance_levels, list)

    def test_schemas_vision_report_full(self):
        """VisionReport with explicit values round-trips correctly."""
        report = VisionReport(
            trend_direction="BULLISH",
            key_patterns=["double bottom", "EMA crossover"],
            support_levels=[1900.0, 1850.0],
            resistance_levels=[1950.0, 2000.0],
            volume_analysis="Volume expanding on breakout",
            momentum="BUILDING",
            visual_confidence=0.82,
            actionable_insight="Consider long above 1950",
            chart_hash="abc123def456abcd",
        )
        assert report.trend_direction == "BULLISH"
        assert len(report.key_patterns) == 2
        assert report.visual_confidence == 0.82
        assert report.chart_hash == "abc123def456abcd"

    def test_schemas_vision_report_invalid_confidence(self):
        """visual_confidence outside [0, 1] raises ValidationError."""
        with pytest.raises(Exception):
            VisionReport(visual_confidence=1.5)

    def test_schemas_chart_config(self):
        """ChartConfig has expected defaults."""
        config = ChartConfig()
        assert config.width == 1200
        assert config.height == 600
        assert config.show_ema is True
        assert config.show_bollinger is True
        assert config.show_volume is True
        assert config.show_rsi is True
        assert config.style == "nightclouds"

    def test_schemas_chart_config_custom(self):
        """ChartConfig accepts custom values."""
        config = ChartConfig(width=800, height=400, show_rsi=False, style="dark")
        assert config.width == 800
        assert config.height == 400
        assert config.show_rsi is False
        assert config.style == "dark"

    def test_schemas_vision_signal(self):
        """VisionSignal creates with defaults."""
        signal = VisionSignal()
        assert signal.vision_report is None
        assert signal.rag_context_summary == ""
        assert 0.0 <= signal.chart_confidence <= 1.0

    def test_schemas_vision_signal_with_report(self):
        """VisionSignal with embedded VisionReport is valid."""
        report = VisionReport(trend_direction="BEARISH", visual_confidence=0.7)
        signal = VisionSignal(
            vision_report=report,
            rag_context_summary="Gold trending down below 200 EMA",
            chart_confidence=0.7,
        )
        assert signal.vision_report is not None
        assert signal.vision_report.trend_direction == "BEARISH"
        assert signal.chart_confidence == 0.7
