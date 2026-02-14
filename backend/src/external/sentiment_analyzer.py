"""
Local sentiment analysis using FinBERT (primary) with VADER (fallback).

This module provides sentiment scores [-1.0, 1.0] for financial news text:
- FinBERT: 85-90% accuracy, domain-specific (Financial PhraseBank)
- VADER: 65% accuracy, rule-based fallback
- TTL cache: 1h with SHA256 hash keys
- Lazy loading: model loaded on first predict() call
"""

import asyncio
import hashlib
import time
from typing import Any

import torch
from loguru import logger
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


class SentimentAnalyzer:
    """
    Local sentiment analyzer with FinBERT primary + VADER fallback.

    Features:
    - Lazy loading: FinBERT model loaded on first predict() call
    - TTL cache: predictions cached 1h by text hash
    - Batch processing: analyze 10+ articles in single forward pass
    - Graceful degradation: VADER fallback if FinBERT unavailable
    - Thread-safe: asyncio.Lock for model loading
    """

    FINBERT_MODEL = "ProsusAI/finbert"
    CACHE_TTL_SECONDS = 3600  # 1 hour
    MAX_CACHE_SIZE = 1000  # LRU eviction

    def __init__(
        self,
        model_name: str = FINBERT_MODEL,
        device: str | None = None,
        enable_cache: bool = True,
    ):
        """
        Initialize sentiment analyzer with lazy model loading.

        Args:
            model_name: HuggingFace model ID (default: ProsusAI/finbert)
            device: "cpu" or "cuda" (auto-detect if None)
            enable_cache: Enable TTL cache for predictions
        """
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.enable_cache = enable_cache

        # Lazy-loaded components
        self._model: AutoModelForSequenceClassification | None = None
        self._tokenizer: AutoTokenizer | None = None
        self._vader: SentimentIntensityAnalyzer | None = None
        self._load_lock = asyncio.Lock()

        # Cache: {text_hash: (timestamp, sentiment_score)}
        self._cache: dict[str, tuple[float, float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        logger.info(
            f"SentimentAnalyzer initialized (model={model_name}, device={self.device}, "
            f"cache={enable_cache})"
        )

    async def _load_model(self) -> None:
        """
        Load FinBERT model and tokenizer (lazy init, thread-safe).

        Downloads ~200MB model on first call (cached by transformers).
        """
        async with self._load_lock:
            if self._model is not None:
                return  # Already loaded

            try:
                logger.info(f"Loading FinBERT model: {self.model_name}")
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_name
                )
                self._model.to(self.device)
                self._model.eval()  # Inference mode
                logger.success(
                    f"FinBERT model loaded successfully (device={self.device})"
                )
            except Exception as e:
                logger.error(f"Failed to load FinBERT model: {e}")
                self._model = None
                self._tokenizer = None
                raise

    def _get_cache_key(self, text: str) -> str:
        """Generate SHA256 hash for cache key."""
        normalized = text.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _cache_get(self, text: str) -> float | None:
        """Get cached sentiment score if valid."""
        if not self.enable_cache:
            return None

        cache_key = self._get_cache_key(text)
        cached = self._cache.get(cache_key)

        if cached is None:
            self._cache_misses += 1
            return None

        timestamp, score = cached
        age = time.monotonic() - timestamp

        if age > self.CACHE_TTL_SECONDS:
            # Expired
            del self._cache[cache_key]
            self._cache_misses += 1
            return None

        self._cache_hits += 1
        return score

    def _cache_put(self, text: str, score: float) -> None:
        """Store sentiment score in cache."""
        if not self.enable_cache:
            return

        cache_key = self._get_cache_key(text)
        self._cache[cache_key] = (time.monotonic(), score)

        # LRU eviction if cache too large
        if len(self._cache) > self.MAX_CACHE_SIZE:
            # Remove oldest entry
            oldest_key = min(
                self._cache.keys(), key=lambda k: self._cache[k][0]
            )
            del self._cache[oldest_key]
            logger.debug(f"Cache evicted oldest entry (size={len(self._cache)})")

    async def predict(self, text: str | list[str]) -> float | list[float]:
        """
        Predict sentiment using FinBERT.

        Args:
            text: Single text or list (e.g., "title + description")

        Returns:
            Sentiment score(s) in [-1.0, 1.0]:
            - negative → -1.0 (bearish)
            - neutral → 0.0
            - positive → +1.0 (bullish)

        Example:
            >>> analyzer = SentimentAnalyzer()
            >>> score = await analyzer.predict("Tesla stock soars on earnings beat")
            >>> print(score)  # ~0.7 (positive)
        """
        # Handle single text
        is_single = isinstance(text, str)
        texts = [text] if is_single else text

        if not texts:
            return 0.0 if is_single else []

        # Check cache for all texts
        results = []
        uncached_texts = []
        uncached_indices = []

        for i, t in enumerate(texts):
            cached_score = self._cache_get(t)
            if cached_score is not None:
                results.append((i, cached_score))
            else:
                uncached_texts.append(t)
                uncached_indices.append(i)

        # If all cached, return immediately
        if not uncached_texts:
            results.sort(key=lambda x: x[0])
            scores = [r[1] for r in results]
            return scores[0] if is_single else scores

        # Load model if needed
        try:
            await self._load_model()
        except Exception as e:
            logger.warning(f"FinBERT unavailable, using VADER fallback: {e}")
            return self.predict_vader(text)

        # Run FinBERT inference
        try:
            with torch.no_grad():
                # Tokenize
                inputs = self._tokenizer(
                    uncached_texts,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                # Forward pass
                outputs = self._model(**inputs)
                logits = outputs.logits  # (batch, 3) [negative, neutral, positive]

                # Convert to probabilities
                probs = torch.softmax(logits, dim=1)  # (batch, 3)

                # Map to [-1, 1]: positive_prob - negative_prob
                sentiments = probs[:, 2] - probs[:, 0]  # positive - negative
                sentiments = sentiments.cpu().numpy()

            # Cache and collect results
            for i, (text_idx, sentiment) in enumerate(
                zip(uncached_indices, sentiments)
            ):
                score = float(sentiment)
                self._cache_put(uncached_texts[i], score)
                results.append((text_idx, score))

        except Exception as e:
            logger.error(f"FinBERT inference failed: {e}, using VADER fallback")
            vader_scores = self.predict_vader(uncached_texts)
            for i, (text_idx, vader_score) in enumerate(
                zip(uncached_indices, vader_scores)
            ):
                results.append((text_idx, vader_score))

        # Sort results by original index
        results.sort(key=lambda x: x[0])
        scores = [r[1] for r in results]

        return scores[0] if is_single else scores

    def predict_vader(self, text: str | list[str]) -> float | list[float]:
        """
        VADER fallback for sentiment analysis (rule-based, always available).

        Args:
            text: Single text or list

        Returns:
            Sentiment score(s) in [-1.0, 1.0] (compound score)

        Example:
            >>> analyzer = SentimentAnalyzer()
            >>> score = analyzer.predict_vader("Stock plummets on bad earnings")
            >>> print(score)  # ~-0.8 (negative)
        """
        if self._vader is None:
            self._vader = SentimentIntensityAnalyzer()

        is_single = isinstance(text, str)
        texts = [text] if is_single else text

        scores = []
        for t in texts:
            if not t or not t.strip():
                scores.append(0.0)
                continue

            # VADER compound score already in [-1, 1]
            sentiment = self._vader.polarity_scores(t)["compound"]
            scores.append(sentiment)

        return scores[0] if is_single else scores

    def clear_cache(self) -> None:
        """Clear prediction cache."""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info("Sentiment cache cleared")

    @property
    def is_loaded(self) -> bool:
        """Check if FinBERT model is loaded."""
        return self._model is not None

    @property
    def cache_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            {
                "size": int,
                "hits": int,
                "misses": int,
                "hit_rate": float,
                "enabled": bool
            }
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0

        return {
            "size": len(self._cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": hit_rate,
            "enabled": self.enable_cache,
        }
