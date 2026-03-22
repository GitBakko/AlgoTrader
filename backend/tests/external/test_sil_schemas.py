"""Tests for SIL schemas and base client."""

from datetime import datetime, timezone

import pytest

from src.external.sil_schemas import (
    AlphaVantageData,
    COTData,
    CalendarEvent,
    FREDData,
    FearGreedData,
    SILData,
    SocialSentimentData,
)


class TestFearGreedData:
    def test_defaults(self):
        fg = FearGreedData()
        assert fg.value == 50.0
        assert fg.normalized == 0.5
        assert fg.classification == "neutral"
        assert fg.is_extreme_fear is False
        assert fg.is_extreme_greed is False
        assert fg.gold_bias == 0.0

    def test_extreme_fear(self):
        fg = FearGreedData(
            value=10, normalized=0.1,
            is_extreme_fear=True, gold_bias=0.8,
        )
        assert fg.is_extreme_fear is True
        assert fg.gold_bias > 0

    def test_extreme_greed(self):
        fg = FearGreedData(
            value=90, normalized=0.9,
            is_extreme_greed=True, gold_bias=-0.8,
        )
        assert fg.is_extreme_greed is True
        assert fg.gold_bias < 0


class TestFREDData:
    def test_defaults_are_none(self):
        fred = FREDData()
        assert fred.fed_funds_rate is None
        assert fred.yield_spread_10y2y is None
        assert fred.real_yield_10y is None
        assert fred.timestamp is None

    def test_partial_data(self):
        fred = FREDData(fed_funds_rate=5.25, real_yield_10y=1.8)
        assert fred.fed_funds_rate == 5.25
        assert fred.real_yield_10y == 1.8
        assert fred.consumer_sentiment is None

    def test_all_12_fields(self):
        fred = FREDData(
            fed_funds_rate=5.25, yield_spread_10y2y=-0.5,
            high_yield_spread=4.2, consumer_sentiment=68.0,
            unemployment_rate=3.7, nonfarm_payrolls=150000,
            real_yield_10y=1.8, breakeven_inflation=2.3,
            nominal_yield_10y=4.1, broad_dollar=120.5,
            vix_close=18.5, wti_crude=72.0,
        )
        assert fred.fed_funds_rate == 5.25
        assert fred.wti_crude == 72.0


class TestAlphaVantageData:
    def test_defaults(self):
        av = AlphaVantageData()
        assert av.average_sentiment_score == 0.0
        assert av.bullish_ratio == 0.5

    def test_bullish_sentiment(self):
        av = AlphaVantageData(
            average_sentiment_score=0.6,
            bullish_count=30, bearish_count=5, neutral_count=15,
            bullish_ratio=0.857,
        )
        assert av.bullish_ratio > 0.8


class TestCOTData:
    def test_defaults(self):
        cot = COTData()
        assert cot.net_position == 0
        assert cot.is_institutional_bullish is False
        assert cot.z_score_4w == 0.0

    def test_bullish_positioning(self):
        cot = COTData(
            noncomm_long=250000, noncomm_short=150000,
            net_position=100000, net_position_normalized=0.75,
            is_institutional_bullish=True, z_score_4w=1.5,
        )
        assert cot.is_institutional_bullish is True
        assert cot.z_score_4w > 1.0


class TestSocialSentimentData:
    def test_defaults(self):
        social = SocialSentimentData()
        assert social.reddit_bullish_ratio == 0.5
        assert social.x_bullish_ratio == 0.5
        assert social.combined_bullish_ratio == 0.5

    def test_reddit_dominant(self):
        social = SocialSentimentData(
            reddit_bullish_ratio=0.8, reddit_post_count=100,
            x_bullish_ratio=0.5, x_post_count=10,
            combined_bullish_ratio=0.77,
        )
        assert social.combined_bullish_ratio > 0.7


class TestCalendarEvent:
    def test_defaults(self):
        event = CalendarEvent()
        assert event.impact == "low"
        assert event.event == ""

    def test_high_impact_event(self):
        event = CalendarEvent(
            event="Non-Farm Payrolls", country="US",
            currency="USD", impact="high",
            event_time=datetime(2026, 3, 7, 13, 30, tzinfo=timezone.utc),
            forecast="200K", previous="180K",
        )
        assert event.impact == "high"
        assert event.currency == "USD"


class TestSILData:
    def test_all_defaults(self):
        data = SILData()
        assert data.fear_greed.value == 50.0
        assert data.fred.fed_funds_rate is None
        assert data.alpha_vantage.bullish_ratio == 0.5
        assert data.cot.net_position == 0
        assert data.social.combined_bullish_ratio == 0.5
        assert data.calendar_events == []
        assert data.fetch_errors == []

    def test_with_errors(self):
        data = SILData(fetch_errors=["FREDClient: timeout", "COTClient: 503"])
        assert len(data.fetch_errors) == 2

    def test_partial_data_graceful(self):
        """SILData works with only some sources populated."""
        data = SILData(
            fear_greed=FearGreedData(value=25, normalized=0.25, is_extreme_fear=True),
            fetch_errors=["FREDClient: no API key"],
        )
        assert data.fear_greed.is_extreme_fear is True
        assert data.fred.fed_funds_rate is None  # Defaults
        assert len(data.fetch_errors) == 1

    def test_serialization_roundtrip(self):
        """SILData can be serialized and deserialized."""
        data = SILData(
            fear_greed=FearGreedData(value=30, normalized=0.3, gold_bias=0.4),
            fred=FREDData(fed_funds_rate=5.25),
        )
        json_str = data.model_dump_json()
        restored = SILData.model_validate_json(json_str)
        assert restored.fear_greed.value == 30
        assert restored.fred.fed_funds_rate == 5.25
