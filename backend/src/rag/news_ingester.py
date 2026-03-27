# MANTIS-EVOLUTION: News RAG Ingester
"""Aggregates and processes news from existing SIL feeds."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from loguru import logger

from src.rag.schemas import NewsItem

# ---------------------------------------------------------------------------
# Relevance keyword sets
# ---------------------------------------------------------------------------

CRYPTO_KEYWORDS = {"bitcoin", "btc", "crypto", "ethereum", "blockchain", "defi", "altcoin"}
FOREX_KEYWORDS = {"forex", "dollar", "euro", "gbp", "yen", "fed", "ecb", "boj", "interest rate"}
MACRO_KEYWORDS = {
    "inflation",
    "cpi",
    "gdp",
    "employment",
    "nonfarm",
    "fomc",
    "rate hike",
    "rate cut",
}
COMMODITY_KEYWORDS = {"gold", "silver", "oil", "crude", "copper", "commodity", "precious metal"}
HIGH_IMPACT = {
    "crash",
    "surge",
    "plunge",
    "rally",
    "breakout",
    "collapse",
    "record high",
    "record low",
}

# Source credibility tiers (0.0–1.0)
SOURCE_CREDIBILITY = {
    "reuters": 1.0,
    "bloomberg": 1.0,
    "wsj": 0.95,
    "cnbc": 0.85,
    "coindesk": 0.8,
    "cointelegraph": 0.75,
    "yahoo": 0.7,
    "marketwatch": 0.8,
    "investing.com": 0.7,
}


class MantisNewsIngester:
    """
    Aggregates and processes news from SIL feeds.

    Does NOT call external APIs — uses data already fetched by SIL clients.
    Handles deduplication, lead-paragraph extraction, and relevance scoring.
    """

    def __init__(self, lookback_hours: int = 4) -> None:
        self.lookback_hours = lookback_hours
        self._seen_hashes: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(self, raw_items: list[dict], symbol: str = "BTCUSD") -> list[NewsItem]:
        """
        Process raw news items from SIL feeds.

        Steps:
        1. Filter items older than *lookback_hours*.
        2. Deduplicate by title MD5 hash.
        3. Extract lead paragraph from full text.
        4. Score relevance for *symbol*.
        5. Return sorted by relevance_score descending.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=self.lookback_hours)

        processed: list[NewsItem] = []
        for raw in raw_items:
            # --- Parse publication timestamp ---
            pub_str = raw.get("published_at") or raw.get("datetime") or raw.get("timestamp", "")
            try:
                pub_dt = datetime.fromisoformat(str(pub_str).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pub_dt = now

            # Ensure timezone-aware for comparison
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=UTC)

            # --- Filter by recency ---
            if pub_dt < cutoff:
                continue

            # --- Deduplicate by title ---
            title = raw.get("title", "") or raw.get("headline", "") or ""
            title_hash = hashlib.md5(title.lower().encode()).hexdigest()
            if title_hash in self._seen_hashes:
                continue
            self._seen_hashes.add(title_hash)

            # --- Extract content ---
            full_text = (
                raw.get("text", "") or raw.get("summary", "") or raw.get("description", "") or ""
            )
            lead = self.extract_lead_paragraph(full_text)

            source = raw.get("source", "") or raw.get("provider", "") or ""

            item = NewsItem(
                title=title,
                source=source,
                url=raw.get("url", "") or "",
                published_at=pub_dt,
                lead_paragraph=lead,
                full_text=full_text,
                sentiment=float(raw.get("sentiment", 0) or 0),
            )
            item.relevance_score = self.score_relevance(item, symbol)
            processed.append(item)

        processed.sort(key=lambda x: x.relevance_score, reverse=True)
        logger.debug(
            "MantisNewsIngester.ingest: {} items processed for symbol={}",
            len(processed),
            symbol,
        )
        return processed

    def extract_lead_paragraph(self, text: str) -> str:
        """
        Extract the lead paragraph using the inverted-pyramid heuristic.

        Takes the first paragraph and limits to the first 3 sentences.
        Truncates to 300 characters maximum.
        """
        if not text or not text.strip():
            return ""

        # Normalise whitespace
        text = re.sub(r"\s+", " ", text.strip())

        # Prefer first double-newline paragraph
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        first = paragraphs[0] if paragraphs else text

        # Split into sentences and take the first 3
        sentences = re.split(r"(?<=[.!?])\s+", first)
        lead = " ".join(sentences[:3])

        # Hard cap at 300 characters
        if len(lead) > 300:
            lead = lead[:297] + "..."

        return lead

    def score_relevance(self, item: NewsItem, symbol: str = "") -> float:
        """
        Score news relevance in [0.0, 1.0].

        Breakdown (max contributions):
        - Keyword density  : 0.40
        - Recency          : 0.30
        - Source credibility: 0.20
        - Sentiment strength: 0.10
        """
        score = 0.0
        text_lower = f"{item.title} {item.lead_paragraph}".lower()

        # 1. Keyword matching (max 0.40) --------------------------------
        all_keywords = CRYPTO_KEYWORDS | FOREX_KEYWORDS | MACRO_KEYWORDS | COMMODITY_KEYWORDS
        matches = sum(1 for kw in all_keywords if kw in text_lower)
        keyword_score = min(matches * 0.1, 0.4)

        # High-impact term boost
        if any(term in text_lower for term in HIGH_IMPACT):
            keyword_score = min(keyword_score + 0.15, 0.4)

        # Symbol-specific boost
        if symbol:
            sym_lower = symbol.lower()
            if sym_lower in text_lower or sym_lower[:3] in text_lower:
                keyword_score = min(keyword_score + 0.1, 0.4)

        score += keyword_score

        # 2. Recency (max 0.30) ----------------------------------------
        now = datetime.now(UTC)
        pub = item.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=UTC)

        age_hours = (now - pub).total_seconds() / 3600
        if age_hours < 0:
            age_hours = 0.0
        recency_score = max(0.0, 0.3 * (1.0 - age_hours / max(self.lookback_hours, 1)))
        score += recency_score

        # 3. Source credibility (max 0.20) -----------------------------
        source_lower = item.source.lower()
        cred = 0.5  # default for unknown sources
        for name, c in SOURCE_CREDIBILITY.items():
            if name in source_lower:
                cred = c
                break
        score += cred * 0.2

        # 4. Sentiment strength (max 0.10) -----------------------------
        score += abs(item.sentiment) * 0.1

        return min(max(score, 0.0), 1.0)

    def clear_seen(self) -> None:
        """Reset deduplication cache so previously-seen titles can be re-ingested."""
        self._seen_hashes.clear()
