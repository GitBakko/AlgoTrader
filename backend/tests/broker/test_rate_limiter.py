"""
Unit tests for token bucket rate limiter.
"""

import asyncio
import time

import pytest

from src.broker.rate_limiter import RateLimiter, TokenBucket


@pytest.mark.unit
@pytest.mark.broker
class TestTokenBucket:
    """Test TokenBucket rate limiter implementation."""

    def test_initialization(self):
        """Test TokenBucket initialization."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        assert bucket.rate == 10.0
        assert bucket.capacity == 20
        assert bucket.tokens == 20.0  # Starts full
        assert bucket.last_update > 0

    def test_get_available_tokens_initial(self):
        """Test getting available tokens at initialization."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        available = bucket.get_available_tokens()
        assert available == 20.0

    async def test_acquire_single_token(self):
        """Test acquiring a single token."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        result = await bucket.acquire(tokens=1)
        assert result is True
        assert bucket.tokens == 19.0

    async def test_acquire_multiple_tokens(self):
        """Test acquiring multiple tokens at once."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        result = await bucket.acquire(tokens=5)
        assert result is True
        assert bucket.tokens == 15.0

    async def test_acquire_all_tokens(self):
        """Test acquiring all available tokens."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        result = await bucket.acquire(tokens=20)
        assert result is True
        assert bucket.tokens == 0.0

    async def test_acquire_exceeds_capacity_raises_error(self):
        """Test that requesting more tokens than capacity raises ValueError."""
        bucket = TokenBucket(rate=10.0, capacity=20)
        with pytest.raises(ValueError, match="exceeds capacity"):
            await bucket.acquire(tokens=25)

    async def test_acquire_blocks_when_insufficient_tokens(self):
        """Test that acquire blocks when insufficient tokens available."""
        bucket = TokenBucket(rate=10.0, capacity=20)

        # Drain the bucket
        await bucket.acquire(tokens=20)
        assert bucket.tokens == 0.0

        # Try to acquire with short timeout
        start_time = time.monotonic()
        result = await bucket.acquire(tokens=1, timeout=0.2)
        elapsed = time.monotonic() - start_time

        # Should timeout after ~0.2s
        assert result is True  # Should succeed after refill
        assert elapsed >= 0.09  # At least 100ms wait (1 token at 10/sec)

    async def test_acquire_timeout(self):
        """Test acquire timeout when tokens not available in time."""
        bucket = TokenBucket(rate=1.0, capacity=5)  # Slow refill rate

        # Drain the bucket
        await bucket.acquire(tokens=5)

        # Try to acquire 5 tokens with 0.1s timeout (not enough time to refill)
        start_time = time.monotonic()
        result = await bucket.acquire(tokens=5, timeout=0.1)
        elapsed = time.monotonic() - start_time

        # Should timeout
        assert result is False
        assert elapsed >= 0.1
        assert elapsed < 0.3

    async def test_token_refill_over_time(self):
        """Test that tokens refill over time."""
        bucket = TokenBucket(rate=10.0, capacity=20)

        # Drain half the bucket
        await bucket.acquire(tokens=10)
        assert bucket.tokens == 10.0

        # Wait for tokens to refill (100ms = 1 token at 10/sec)
        await asyncio.sleep(0.15)

        # Check tokens increased
        available = bucket.get_available_tokens()
        assert available > 10.0  # Should have refilled
        assert available < 12.0  # But not fully

    async def test_token_refill_caps_at_capacity(self):
        """Test that token refill doesn't exceed capacity."""
        bucket = TokenBucket(rate=100.0, capacity=10)

        # Acquire 1 token
        await bucket.acquire(tokens=1)
        assert bucket.tokens == 9.0

        # Wait for refill (should cap at capacity)
        await asyncio.sleep(0.2)

        available = bucket.get_available_tokens()
        assert available == 10.0  # Capped at capacity

    async def test_concurrent_acquire(self):
        """Test multiple concurrent acquire calls."""
        bucket = TokenBucket(rate=10.0, capacity=10)

        # Launch 5 concurrent acquire calls
        tasks = [bucket.acquire(tokens=2) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All should succeed eventually
        assert all(results)
        assert bucket.tokens == 0.0  # All 10 tokens consumed

    async def test_acquire_with_none_timeout(self):
        """Test acquire with None timeout waits indefinitely."""
        bucket = TokenBucket(rate=10.0, capacity=20)

        # Drain bucket
        await bucket.acquire(tokens=20)

        # Acquire with None timeout (should wait for refill)
        start_time = time.monotonic()
        result = await bucket.acquire(tokens=1, timeout=None)
        elapsed = time.monotonic() - start_time

        assert result is True
        assert elapsed >= 0.09  # At least 100ms for 1 token refill


@pytest.mark.unit
@pytest.mark.broker
class TestRateLimiter:
    """Test RateLimiter wrapper."""

    def test_initialization_default(self):
        """Test RateLimiter initialization with defaults."""
        limiter = RateLimiter()
        assert limiter.bucket.rate == 10.0
        assert limiter.bucket.capacity == 20

    def test_initialization_custom(self):
        """Test RateLimiter initialization with custom values."""
        limiter = RateLimiter(requests_per_second=5, burst_capacity=15)
        assert limiter.bucket.rate == 5.0
        assert limiter.bucket.capacity == 15

    async def test_acquire_success(self):
        """Test successful request acquisition."""
        limiter = RateLimiter(requests_per_second=10, burst_capacity=20)
        result = await limiter.acquire()
        assert result is True

    async def test_acquire_timeout(self):
        """Test acquire with timeout."""
        limiter = RateLimiter(requests_per_second=1, burst_capacity=1)

        # Drain the limiter
        await limiter.acquire()

        # Should timeout
        result = await limiter.acquire(timeout=0.1)
        assert result is False

    async def test_available_requests(self):
        """Test getting number of available requests."""
        limiter = RateLimiter(requests_per_second=10, burst_capacity=20)

        # Initially full
        available = limiter.available_requests()
        assert available == 20.0

        # After one request
        await limiter.acquire()
        available = limiter.available_requests()
        assert available == 19.0

    async def test_multiple_sequential_requests(self):
        """Test multiple sequential request acquisitions."""
        limiter = RateLimiter(requests_per_second=10, burst_capacity=20)

        # Make 10 requests
        for i in range(10):
            result = await limiter.acquire()
            assert result is True
            assert limiter.available_requests() == 20 - (i + 1)

    async def test_burst_capacity_allows_burst(self):
        """Test that burst capacity allows quick succession of requests."""
        limiter = RateLimiter(requests_per_second=10, burst_capacity=20)

        start_time = time.monotonic()

        # Make 20 requests rapidly (should all succeed immediately)
        results = []
        for _ in range(20):
            result = await limiter.acquire(timeout=0.1)
            results.append(result)

        elapsed = time.monotonic() - start_time

        # All should succeed quickly (within 0.5s)
        assert all(results)
        assert elapsed < 0.5

    async def test_rate_limiting_enforced(self):
        """Test that rate limiting is enforced after burst."""
        limiter = RateLimiter(requests_per_second=10, burst_capacity=10)

        # Drain burst capacity
        for _ in range(10):
            await limiter.acquire()

        # Next request should wait
        start_time = time.monotonic()
        result = await limiter.acquire(timeout=0.3)
        elapsed = time.monotonic() - start_time

        assert result is True
        assert elapsed >= 0.09  # At least 100ms wait for token refill
