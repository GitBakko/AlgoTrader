"""Test the 7th sentiment vote group in ScalpScore."""
import pytest
from src.strategy.scalp_score_strategy import ScalpScoreStrategy


class TestSentimentVote:
    def test_bullish_sentiment(self):
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(composite_score=0.7)
        assert vote == 1
        assert details["composite"] == 0.7

    def test_bearish_sentiment(self):
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(composite_score=0.25)
        assert vote == -1

    def test_neutral_sentiment(self):
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(composite_score=0.5)
        assert vote == 0

    def test_zero_composite_neutral(self):
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(composite_score=0.0)
        assert vote == 0

    def test_custom_thresholds(self):
        strategy = ScalpScoreStrategy()
        vote, _ = strategy._vote_sentiment(0.5, bullish_threshold=0.4)
        assert vote == 1
        vote, _ = strategy._vote_sentiment(0.5, bearish_threshold=0.6)
        assert vote == -1

    def test_vote_returns_correct_types(self):
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(0.8)
        assert isinstance(vote, int)
        assert isinstance(details, dict)
        assert "composite" in details

    def test_boundary_bullish_threshold(self):
        """Exactly at bullish threshold should be neutral (not strictly greater)."""
        strategy = ScalpScoreStrategy()
        vote, _ = strategy._vote_sentiment(0.6)
        assert vote == 0

    def test_boundary_bearish_threshold(self):
        """Exactly at bearish threshold should be neutral (not strictly less)."""
        strategy = ScalpScoreStrategy()
        vote, _ = strategy._vote_sentiment(0.35)
        assert vote == 0

    def test_negative_composite_neutral(self):
        """Negative composites treated as no data (neutral)."""
        strategy = ScalpScoreStrategy()
        vote, _ = strategy._vote_sentiment(-0.1)
        assert vote == 0
