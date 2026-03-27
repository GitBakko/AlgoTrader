"""
Token bucket rate limiter for Capital.com API.
Implements 10 requests/second limit with burst capacity.
"""

import asyncio
import time


class TokenBucket:
    """
    Token bucket rate limiter for API requests.
    Allows burst requests up to bucket capacity while maintaining average rate.
    """

    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket rate limiter.

        Args:
            rate: Tokens added per second (e.g., 10 for 10 req/sec)
            capacity: Maximum bucket capacity (burst limit)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        """
        Acquire tokens from the bucket.
        Blocks until tokens are available or timeout is reached.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum time to wait in seconds (None = wait forever)

        Returns:
            True if tokens acquired, False if timeout

        Raises:
            ValueError: If requested tokens exceed capacity
        """
        if tokens > self.capacity:
            raise ValueError(f"Requested {tokens} tokens exceeds capacity {self.capacity}")

        start_time = time.monotonic()

        while True:
            async with self._lock:
                # Refill bucket based on elapsed time
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                # Check if we have enough tokens
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            # Check timeout
            if timeout is not None:
                elapsed_total = time.monotonic() - start_time
                if elapsed_total >= timeout:
                    return False

            # Calculate sleep time until next token available
            tokens_needed = tokens - self.tokens
            sleep_time = min(tokens_needed / self.rate, 0.1)  # Max 100ms sleep
            await asyncio.sleep(sleep_time)

    def get_available_tokens(self) -> float:
        """Get current number of available tokens (without acquiring)."""
        now = time.monotonic()
        elapsed = now - self.last_update
        return min(self.capacity, self.tokens + elapsed * self.rate)


class RateLimiter:
    """
    Rate limiter manager for Capital.com API.
    Enforces 10 requests/second limit.
    """

    def __init__(self, requests_per_second: int = 10, burst_capacity: int = 20):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second (default: 10)
            burst_capacity: Burst capacity (default: 20)
        """
        self.bucket = TokenBucket(rate=float(requests_per_second), capacity=burst_capacity)

    async def acquire(self, timeout: float | None = 10.0) -> bool:
        """
        Acquire permission to make an API request.

        Args:
            timeout: Maximum wait time in seconds (default: 10s)

        Returns:
            True if acquired, False if timeout
        """
        return await self.bucket.acquire(tokens=1, timeout=timeout)

    def available_requests(self) -> float:
        """Get number of immediately available request slots."""
        return self.bucket.get_available_tokens()
