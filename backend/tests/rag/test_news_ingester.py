# MANTIS-EVOLUTION: RAG news ingester tests
"""TDD tests for MantisNewsIngester — run before implementation."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from src.rag.news_ingester import MantisNewsIngester
from src.rag.schemas import NewsItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_raw(
    title: str = "Bitcoin surges to record high",
    source: str = "reuters",
    published_offset_hours: float = 0.5,
    full_text: str = "Bitcoin hit a record high today. The crypto market rallied strongly. "
                     "Analysts say further gains are likely.",
    sentiment: float = 0.5,
    url: str = "https://example.com/news/1",
) -> dict:
    """Helper to create a raw news dict as SIL clients would return."""
    pub = datetime.now(timezone.utc) - timedelta(hours=published_offset_hours)
    return {
        "title": title,
        "source": source,
        "url": url,
        "published_at": pub.isoformat(),
        "text": full_text,
        "sentiment": sentiment,
    }


# ---------------------------------------------------------------------------
# 1. test_ingest_basic
# ---------------------------------------------------------------------------

def test_ingest_basic():
    """A list of raw dicts is converted to a list of NewsItem objects."""
    ingester = MantisNewsIngester(lookback_hours=4)
    raw = [make_raw()]
    items = ingester.ingest(raw, symbol="BTCUSD")
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, NewsItem)
    assert "Bitcoin" in item.title
    assert item.source == "reuters"
    assert item.relevance_score > 0.0


# ---------------------------------------------------------------------------
# 2. test_ingest_deduplicates
# ---------------------------------------------------------------------------

def test_ingest_deduplicates():
    """Same title appearing twice results in only one NewsItem."""
    ingester = MantisNewsIngester(lookback_hours=4)
    raw = [make_raw(), make_raw()]  # identical titles
    items = ingester.ingest(raw, symbol="BTCUSD")
    assert len(items) == 1


# ---------------------------------------------------------------------------
# 3. test_ingest_filters_old_news
# ---------------------------------------------------------------------------

def test_ingest_filters_old_news():
    """Items older than lookback_hours are excluded."""
    ingester = MantisNewsIngester(lookback_hours=2)
    raw = [
        make_raw(title="Recent news", published_offset_hours=1.0),
        make_raw(title="Old news article", published_offset_hours=3.0),  # outside window
    ]
    items = ingester.ingest(raw)
    titles = [i.title for i in items]
    assert "Recent news" in titles
    assert "Old news article" not in titles


# ---------------------------------------------------------------------------
# 4. test_ingest_sorted_by_relevance
# ---------------------------------------------------------------------------

def test_ingest_sorted_by_relevance():
    """Results are sorted descending by relevance_score."""
    ingester = MantisNewsIngester(lookback_hours=4)
    raw = [
        make_raw(title="Unrelated local event", source="unknown", sentiment=0.0,
                 full_text="A local council meeting was held.", published_offset_hours=0.1),
        make_raw(title="Bitcoin crashes to record low amid crypto collapse",
                 source="reuters", sentiment=-0.9,
                 full_text="Bitcoin plunged sharply. The crypto market collapsed.", published_offset_hours=0.1),
    ]
    items = ingester.ingest(raw, symbol="BTCUSD")
    assert len(items) == 2
    # High-relevance crypto/high-impact item should rank first
    assert items[0].relevance_score >= items[1].relevance_score


# ---------------------------------------------------------------------------
# 5. test_extract_lead_paragraph_first_sentences
# ---------------------------------------------------------------------------

def test_extract_lead_paragraph_first_sentences():
    """Extracts first 2-3 sentences from text."""
    ingester = MantisNewsIngester()
    text = (
        "Gold prices rose sharply today. "
        "The precious metal gained 2% in early trading. "
        "Analysts cite geopolitical tensions as the main driver. "
        "Investors are watching the Fed closely. "
        "Further details will follow."
    )
    lead = ingester.extract_lead_paragraph(text)
    # Should contain first sentence
    assert "Gold prices rose sharply today" in lead
    # Should NOT contain the 4th+ sentence content
    assert "Investors are watching" not in lead


# ---------------------------------------------------------------------------
# 6. test_extract_lead_paragraph_empty
# ---------------------------------------------------------------------------

def test_extract_lead_paragraph_empty():
    """Empty text returns empty string."""
    ingester = MantisNewsIngester()
    assert ingester.extract_lead_paragraph("") == ""
    assert ingester.extract_lead_paragraph("   ") == ""


# ---------------------------------------------------------------------------
# 7. test_extract_lead_paragraph_truncates
# ---------------------------------------------------------------------------

def test_extract_lead_paragraph_truncates():
    """Very long first sentences are truncated to max ~300 chars."""
    ingester = MantisNewsIngester()
    long_sentence = "A " * 300  # Very long text, one run-on sentence
    lead = ingester.extract_lead_paragraph(long_sentence)
    assert len(lead) <= 303  # 300 + "..." = 303
    assert lead.endswith("...")


# ---------------------------------------------------------------------------
# 8. test_score_relevance_keyword_match
# ---------------------------------------------------------------------------

def test_score_relevance_keyword_match():
    """Items with crypto/forex keywords score higher than unrelated items."""
    ingester = MantisNewsIngester(lookback_hours=4)
    now = datetime.now(timezone.utc)

    crypto_item = NewsItem(
        title="Bitcoin BTC ethereum crypto blockchain surge",
        lead_paragraph="Bitcoin and ethereum are surging. Crypto defi interest rate.",
        published_at=now - timedelta(minutes=30),
        source="reuters",
        sentiment=0.5,
    )
    unrelated_item = NewsItem(
        title="Local football match results",
        lead_paragraph="The home team won by two goals.",
        published_at=now - timedelta(minutes=30),
        source="unknown",
        sentiment=0.0,
    )
    crypto_score = ingester.score_relevance(crypto_item, symbol="BTCUSD")
    unrelated_score = ingester.score_relevance(unrelated_item, symbol="BTCUSD")
    assert crypto_score > unrelated_score


# ---------------------------------------------------------------------------
# 9. test_score_relevance_high_impact
# ---------------------------------------------------------------------------

def test_score_relevance_high_impact():
    """High-impact terms ('crash', 'surge', etc.) boost the score."""
    ingester = MantisNewsIngester(lookback_hours=4)
    now = datetime.now(timezone.utc)

    normal_item = NewsItem(
        title="Gold moves slightly",
        lead_paragraph="Gold edged up in morning trading.",
        published_at=now - timedelta(minutes=30),
        source="unknown",
        sentiment=0.1,
    )
    impact_item = NewsItem(
        title="Gold CRASHES to record low",
        lead_paragraph="Gold collapsed in a sudden crash today.",
        published_at=now - timedelta(minutes=30),
        source="unknown",
        sentiment=-0.8,
    )
    normal_score = ingester.score_relevance(normal_item)
    impact_score = ingester.score_relevance(impact_item)
    assert impact_score > normal_score


# ---------------------------------------------------------------------------
# 10. test_score_relevance_source_credibility
# ---------------------------------------------------------------------------

def test_score_relevance_source_credibility():
    """Reuters (credibility 1.0) should outscore unknown source (0.5)."""
    ingester = MantisNewsIngester(lookback_hours=4)
    now = datetime.now(timezone.utc)
    pub = now - timedelta(minutes=30)

    reuters_item = NewsItem(
        title="Market update",
        lead_paragraph="Markets moved today.",
        published_at=pub,
        source="reuters",
        sentiment=0.0,
    )
    unknown_item = NewsItem(
        title="Market update",  # same title/text but different source
        lead_paragraph="Markets moved today.",
        published_at=pub,
        source="some_blog",
        sentiment=0.0,
    )
    assert ingester.score_relevance(reuters_item) > ingester.score_relevance(unknown_item)


# ---------------------------------------------------------------------------
# 11. test_score_relevance_recency
# ---------------------------------------------------------------------------

def test_score_relevance_recency():
    """A newer article scores higher (recency component) than an older one."""
    ingester = MantisNewsIngester(lookback_hours=4)
    now = datetime.now(timezone.utc)

    new_item = NewsItem(
        title="Breaking news",
        lead_paragraph="Something just happened.",
        published_at=now - timedelta(minutes=10),
        source="unknown",
        sentiment=0.0,
    )
    old_item = NewsItem(
        title="Older breaking news",
        lead_paragraph="Something just happened.",
        published_at=now - timedelta(hours=3),
        source="unknown",
        sentiment=0.0,
    )
    assert ingester.score_relevance(new_item) > ingester.score_relevance(old_item)


# ---------------------------------------------------------------------------
# 12. test_score_relevance_range
# ---------------------------------------------------------------------------

def test_score_relevance_range():
    """score_relevance always returns a value in [0.0, 1.0]."""
    ingester = MantisNewsIngester(lookback_hours=4)
    now = datetime.now(timezone.utc)

    edge_cases = [
        NewsItem(title="", lead_paragraph="", published_at=now, source="", sentiment=0.0),
        NewsItem(title="x" * 500, lead_paragraph="y" * 500,
                 published_at=now - timedelta(hours=100),
                 source="bloomberg", sentiment=1.0),
        NewsItem(
            title="bitcoin crash surge record high rally plunge collapse breakout ethereum defi",
            lead_paragraph="bitcoin btc crash record low surge",
            published_at=now,
            source="reuters",
            sentiment=-1.0,
        ),
    ]
    for item in edge_cases:
        score = ingester.score_relevance(item)
        assert 0.0 <= score <= 1.0, f"Score {score} out of range for {item.title[:30]}"


# ---------------------------------------------------------------------------
# 13. test_clear_seen
# ---------------------------------------------------------------------------

def test_clear_seen():
    """clear_seen() resets the deduplication cache so same title can be ingested again."""
    ingester = MantisNewsIngester(lookback_hours=4)
    raw = [make_raw()]

    first_pass = ingester.ingest(raw)
    assert len(first_pass) == 1

    # Without clearing: duplicate is filtered
    second_pass = ingester.ingest(raw)
    assert len(second_pass) == 0

    # After clearing: item is accepted again
    ingester.clear_seen()
    third_pass = ingester.ingest(raw)
    assert len(third_pass) == 1
