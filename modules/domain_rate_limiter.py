"""
Per-Domain Rate Limiter - Sprint 3.1

Implements intelligent per-domain rate limiting to allow parallel requests
to different domains while respecting each domain's rate limits.

Benefits:
- Parallel requests to different domains (no global delay)
- Exponential backoff on 429/503 responses
- Adaptive delays (2s default, increases on errors)
- Thread-safe for async operations

Author: Claude Code
Date: 2025-12-28
Sprint: 3.1
"""

import time
import asyncio
from typing import Dict, Optional
from urllib.parse import urlparse
from collections import defaultdict
from threading import Lock
from modules.utils import setup_logger

logger = setup_logger("domain_rate_limiter")


class DomainRateLimiter:
    """
    Per-domain rate limiter with exponential backoff.

    Tracks last request time per domain and enforces minimum delay between
    requests to the same domain. Allows parallel requests to different domains.
    """

    def __init__(self, default_delay: float = 2.0, min_delay: float = 1.0, max_delay: float = 10.0):
        """
        Initialize domain rate limiter.

        Args:
            default_delay: Default delay between requests to same domain (seconds)
            min_delay: Minimum delay after successful requests (seconds)
            max_delay: Maximum delay after errors (seconds)
        """
        self.default_delay = default_delay
        self.min_delay = min_delay
        self.max_delay = max_delay

        # Track last request time per domain
        self.last_request_time: Dict[str, float] = {}

        # Track current delay per domain (adaptive)
        self.current_delay: Dict[str, float] = defaultdict(lambda: default_delay)

        # Track consecutive errors per domain
        self.error_count: Dict[str, int] = defaultdict(int)

        # Thread lock for concurrent access
        self.lock = Lock()

        # Statistics
        self.total_requests = 0
        self.total_delays = 0
        self.domains_accessed = set()

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return url.lower()

    def _get_wait_time(self, domain: str) -> float:
        """
        Calculate how long to wait before making request to domain.

        Args:
            domain: Domain name

        Returns:
            Seconds to wait (0 if can proceed immediately)
        """
        if domain not in self.last_request_time:
            return 0.0

        elapsed = time.time() - self.last_request_time[domain]
        delay_needed = self.current_delay[domain]

        wait_time = max(0, delay_needed - elapsed)
        return wait_time

    def wait_if_needed(self, url: str) -> float:
        """
        Wait if necessary before making request (synchronous version).

        Args:
            url: URL to request

        Returns:
            Seconds waited
        """
        domain = self._extract_domain(url)

        with self.lock:
            wait_time = self._get_wait_time(domain)

            if wait_time > 0:
                logger.debug(f"Rate limiting {domain}: waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                self.total_delays += wait_time

            # Update last request time
            self.last_request_time[domain] = time.time()
            self.total_requests += 1
            self.domains_accessed.add(domain)

            return wait_time

    async def wait_if_needed_async(self, url: str) -> float:
        """
        Wait if necessary before making request (async version).

        Args:
            url: URL to request

        Returns:
            Seconds waited
        """
        domain = self._extract_domain(url)

        # Calculate wait time in critical section
        with self.lock:
            wait_time = self._get_wait_time(domain)

            if wait_time > 0:
                logger.debug(f"Rate limiting {domain}: waiting {wait_time:.1f}s")
                self.total_delays += wait_time

        # Sleep outside lock (async)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        # Update timestamp in critical section
        with self.lock:
            self.last_request_time[domain] = time.time()
            self.total_requests += 1
            self.domains_accessed.add(domain)

        return wait_time

    def record_success(self, url: str):
        """
        Record successful request - reduce delay for this domain.

        Args:
            url: URL that succeeded
        """
        domain = self._extract_domain(url)

        with self.lock:
            # Reset error count
            self.error_count[domain] = 0

            # Gradually reduce delay towards minimum (fast sites)
            current = self.current_delay[domain]
            if current > self.min_delay:
                # Reduce by 10% each success
                self.current_delay[domain] = max(self.min_delay, current * 0.9)
                logger.debug(f"Reduced delay for {domain}: {self.current_delay[domain]:.1f}s")

    def record_error(self, url: str, status_code: Optional[int] = None):
        """
        Record failed request - increase delay for this domain (exponential backoff).

        Args:
            url: URL that failed
            status_code: HTTP status code (429, 503, etc.) or None
        """
        domain = self._extract_domain(url)

        with self.lock:
            # Increment error count
            self.error_count[domain] += 1

            # Apply exponential backoff
            if status_code in (429, 503):  # Rate limit or service unavailable
                # Aggressive backoff for explicit rate limiting
                self.current_delay[domain] = min(
                    self.max_delay,
                    self.current_delay[domain] * 2.0
                )
                logger.warning(f"Rate limit hit for {domain} (status {status_code}): "
                             f"increased delay to {self.current_delay[domain]:.1f}s")
            else:
                # Moderate backoff for other errors
                self.current_delay[domain] = min(
                    self.max_delay,
                    self.current_delay[domain] * 1.5
                )
                logger.info(f"Error for {domain}: increased delay to {self.current_delay[domain]:.1f}s")

    def get_stats(self) -> dict:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with stats
        """
        with self.lock:
            return {
                'total_requests': self.total_requests,
                'total_delays': round(self.total_delays, 1),
                'avg_delay_per_request': round(self.total_delays / max(1, self.total_requests), 2),
                'domains_accessed': len(self.domains_accessed),
                'domains_with_errors': sum(1 for count in self.error_count.values() if count > 0),
            }

    def reset(self):
        """Reset all rate limiting state."""
        with self.lock:
            self.last_request_time.clear()
            self.current_delay.clear()
            self.error_count.clear()
            self.total_requests = 0
            self.total_delays = 0
            self.domains_accessed.clear()


# ============================================================================
# Global rate limiter instance (singleton pattern)
# ============================================================================

_global_limiter: Optional[DomainRateLimiter] = None


def get_domain_rate_limiter(default_delay: float = 2.0) -> DomainRateLimiter:
    """
    Get or create the global domain rate limiter instance.

    Args:
        default_delay: Default delay between requests (only used on first call)

    Returns:
        DomainRateLimiter instance
    """
    global _global_limiter

    if _global_limiter is None:
        _global_limiter = DomainRateLimiter(default_delay=default_delay)
        logger.info(f"Initialized domain rate limiter (default delay: {default_delay}s)")

    return _global_limiter


# ============================================================================
# Testing
# ============================================================================

def test_domain_rate_limiter():
    """Test domain rate limiter functionality."""
    logger.info("=" * 80)
    logger.info("TESTING DOMAIN RATE LIMITER")
    logger.info("=" * 80)

    limiter = DomainRateLimiter(default_delay=1.0, min_delay=0.5, max_delay=5.0)

    # Test 1: Same domain requests (should be delayed)
    print("\nTest 1: Same domain requests (should wait)")
    start = time.time()
    limiter.wait_if_needed("https://example.com/page1")
    limiter.wait_if_needed("https://example.com/page2")
    elapsed = time.time() - start
    print(f"  Elapsed: {elapsed:.2f}s (expected ~1.0s)")

    # Test 2: Different domain requests (should be parallel)
    print("\nTest 2: Different domain requests (no wait)")
    start = time.time()
    limiter.wait_if_needed("https://domain1.com/page")
    limiter.wait_if_needed("https://domain2.com/page")
    limiter.wait_if_needed("https://domain3.com/page")
    elapsed = time.time() - start
    print(f"  Elapsed: {elapsed:.2f}s (expected ~0.0s)")

    # Test 3: Success reduces delay
    print("\nTest 3: Success reduces delay")
    limiter.record_success("https://example.com/page1")
    print(f"  Delay after success: {limiter.current_delay['example.com']:.2f}s")

    # Test 4: Error increases delay
    print("\nTest 4: Error increases delay (429)")
    limiter.record_error("https://example.com/page1", status_code=429)
    print(f"  Delay after 429: {limiter.current_delay['example.com']:.2f}s")

    # Test 5: Statistics
    print("\nTest 5: Statistics")
    stats = limiter.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 80)
    print("DOMAIN RATE LIMITER TEST COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    test_domain_rate_limiter()
