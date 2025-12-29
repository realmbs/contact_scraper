"""
Intelligent Timeout Manager - Sprint 3.3

Adaptively tunes timeouts based on domain performance history.

Benefits:
- Fast domains get shorter timeouts (saves time on failures)
- Slow domains get longer timeouts (prevents premature failures)
- Exponential backoff on consecutive timeouts
- Per-domain timeout tracking
- Fast-fail on HTTP errors (404, 403, 500)

Author: Claude Code
Date: 2025-12-28
Sprint: 3.3
"""

import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from collections import defaultdict
from threading import Lock
from modules.utils import setup_logger

logger = setup_logger("timeout_manager")


class TimeoutManager:
    """
    Intelligent timeout manager that adapts based on domain performance.

    Tracks page load times per domain and adjusts timeouts to optimize
    for both speed (short timeouts for fast sites) and reliability
    (long timeouts for slow sites).
    """

    def __init__(
        self,
        default_timeout: int = 30000,  # milliseconds
        min_timeout: int = 8000,       # 8s minimum
        max_timeout: int = 45000,      # 45s maximum
        selector_timeout: int = 3000,  # 3s for selectors
    ):
        """
        Initialize timeout manager.

        Args:
            default_timeout: Default page timeout (milliseconds)
            min_timeout: Minimum timeout for fast domains (milliseconds)
            max_timeout: Maximum timeout for slow domains (milliseconds)
            selector_timeout: Timeout for selector waits (milliseconds)
        """
        self.default_timeout = default_timeout
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        self.selector_timeout = selector_timeout

        # Track page load times per domain (for adaptive timeout)
        self.load_times: Dict[str, list] = defaultdict(list)

        # Track current timeout per domain (adaptive)
        self.current_timeout: Dict[str, int] = defaultdict(lambda: default_timeout)

        # Track consecutive timeouts per domain (for backoff)
        self.timeout_count: Dict[str, int] = defaultdict(int)

        # Thread lock for concurrent access
        self.lock = Lock()

        # Statistics
        self.total_requests = 0
        self.total_timeouts = 0
        self.total_fast_fails = 0

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return url.lower()

    def _calculate_adaptive_timeout(self, domain: str) -> int:
        """
        Calculate adaptive timeout based on historical load times.

        Args:
            domain: Domain name

        Returns:
            Timeout in milliseconds
        """
        if domain not in self.load_times or len(self.load_times[domain]) == 0:
            return self.default_timeout

        # Get average load time for this domain
        avg_load_time = sum(self.load_times[domain]) / len(self.load_times[domain])

        # Set timeout to 2.5x average load time (with buffer for variability)
        adaptive_timeout = int(avg_load_time * 2.5 * 1000)  # Convert to milliseconds

        # Clamp to min/max bounds
        adaptive_timeout = max(self.min_timeout, min(self.max_timeout, adaptive_timeout))

        return adaptive_timeout

    def get_timeout(self, url: str) -> Tuple[int, int]:
        """
        Get appropriate timeout for URL based on domain history.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (page_timeout_ms, selector_timeout_ms)
        """
        domain = self._extract_domain(url)

        with self.lock:
            # Use current adaptive timeout
            page_timeout = self.current_timeout[domain]

            # If domain has consecutive timeouts, apply exponential backoff
            if self.timeout_count[domain] > 0:
                backoff_multiplier = 1.5 ** self.timeout_count[domain]
                page_timeout = int(page_timeout * backoff_multiplier)
                page_timeout = min(self.max_timeout, page_timeout)
                logger.debug(
                    f"Applied timeout backoff for {domain}: "
                    f"{self.current_timeout[domain]}ms → {page_timeout}ms "
                    f"({self.timeout_count[domain]} consecutive timeouts)"
                )

            self.total_requests += 1

            return (page_timeout, self.selector_timeout)

    def record_success(self, url: str, load_time_seconds: float):
        """
        Record successful page load.

        Args:
            url: URL that loaded successfully
            load_time_seconds: Time taken to load (seconds)
        """
        domain = self._extract_domain(url)

        with self.lock:
            # Reset timeout count
            self.timeout_count[domain] = 0

            # Track load time (keep last 10 samples)
            self.load_times[domain].append(load_time_seconds)
            if len(self.load_times[domain]) > 10:
                self.load_times[domain].pop(0)

            # Recalculate adaptive timeout
            new_timeout = self._calculate_adaptive_timeout(domain)
            old_timeout = self.current_timeout[domain]
            self.current_timeout[domain] = new_timeout

            if abs(new_timeout - old_timeout) > 2000:  # Only log significant changes
                logger.info(
                    f"Updated timeout for {domain}: {old_timeout}ms → {new_timeout}ms "
                    f"(avg load time: {load_time_seconds:.1f}s)"
                )

    def record_timeout(self, url: str):
        """
        Record page timeout.

        Args:
            url: URL that timed out
        """
        domain = self._extract_domain(url)

        with self.lock:
            # Increment timeout count for backoff
            self.timeout_count[domain] += 1
            self.total_timeouts += 1

            logger.warning(
                f"Timeout for {domain} ({self.timeout_count[domain]} consecutive)"
            )

    def record_http_error(self, url: str, status_code: int) -> bool:
        """
        Record HTTP error and determine if we should fast-fail.

        Args:
            url: URL that returned error
            status_code: HTTP status code

        Returns:
            True if should fast-fail (don't retry), False otherwise
        """
        domain = self._extract_domain(url)

        # Fast-fail on these status codes (no point retrying)
        fast_fail_codes = {
            403,  # Forbidden
            404,  # Not Found
            410,  # Gone
            451,  # Unavailable For Legal Reasons
            500,  # Internal Server Error
            502,  # Bad Gateway
            503,  # Service Unavailable (when not rate limited)
        }

        if status_code in fast_fail_codes:
            with self.lock:
                self.total_fast_fails += 1
            logger.info(f"Fast-fail for {domain}: HTTP {status_code}")
            return True

        return False

    def get_domain_stats(self, domain: str) -> dict:
        """
        Get timeout statistics for a specific domain.

        Args:
            domain: Domain name

        Returns:
            Dictionary with domain stats
        """
        with self.lock:
            avg_load_time = (
                sum(self.load_times[domain]) / len(self.load_times[domain])
                if domain in self.load_times and len(self.load_times[domain]) > 0
                else 0
            )

            return {
                'domain': domain,
                'current_timeout_ms': self.current_timeout[domain],
                'avg_load_time_s': round(avg_load_time, 2),
                'samples': len(self.load_times[domain]),
                'consecutive_timeouts': self.timeout_count[domain],
            }

    def get_stats(self) -> dict:
        """
        Get overall timeout manager statistics.

        Returns:
            Dictionary with aggregate stats
        """
        with self.lock:
            # Calculate average timeout across all domains
            avg_timeout = (
                sum(self.current_timeout.values()) / len(self.current_timeout)
                if len(self.current_timeout) > 0
                else self.default_timeout
            )

            return {
                'total_requests': self.total_requests,
                'total_timeouts': self.total_timeouts,
                'total_fast_fails': self.total_fast_fails,
                'timeout_rate': (
                    round(self.total_timeouts / max(1, self.total_requests) * 100, 1)
                ),
                'domains_tracked': len(self.load_times),
                'avg_timeout_ms': round(avg_timeout, 0),
                'default_timeout_ms': self.default_timeout,
            }

    def reset(self):
        """Reset all timeout tracking state."""
        with self.lock:
            self.load_times.clear()
            self.current_timeout.clear()
            self.timeout_count.clear()
            self.total_requests = 0
            self.total_timeouts = 0
            self.total_fast_fails = 0


# ============================================================================
# Global timeout manager instance (singleton pattern)
# ============================================================================

_global_manager: Optional[TimeoutManager] = None


def get_timeout_manager(default_timeout: int = 30000) -> TimeoutManager:
    """
    Get or create the global timeout manager instance.

    Args:
        default_timeout: Default timeout (only used on first call)

    Returns:
        TimeoutManager instance
    """
    global _global_manager

    if _global_manager is None:
        _global_manager = TimeoutManager(default_timeout=default_timeout)
        logger.info(f"Initialized timeout manager (default: {default_timeout}ms)")

    return _global_manager


# ============================================================================
# Testing
# ============================================================================

def test_timeout_manager():
    """Test timeout manager functionality."""
    logger.info("=" * 80)
    logger.info("TESTING TIMEOUT MANAGER")
    logger.info("=" * 80)

    manager = TimeoutManager(default_timeout=30000, min_timeout=8000, max_timeout=45000)

    # Test 1: Default timeout
    print("\nTest 1: Default timeout for new domain")
    timeout, selector_timeout = manager.get_timeout("https://example.com/page")
    print(f"  Page timeout: {timeout}ms (expected 30000ms)")
    print(f"  Selector timeout: {selector_timeout}ms (expected 3000ms)")

    # Test 2: Record fast page load
    print("\nTest 2: Record fast page load (2s)")
    manager.record_success("https://example.com/page", 2.0)
    timeout, _ = manager.get_timeout("https://example.com/page")
    print(f"  New timeout: {timeout}ms (expected ~5000ms = 2s × 2.5)")

    # Test 3: Record slow page load
    print("\nTest 3: Record slow page load (15s)")
    manager.record_success("https://slow.com/page", 15.0)
    timeout, _ = manager.get_timeout("https://slow.com/page")
    print(f"  New timeout: {timeout}ms (expected ~37500ms = 15s × 2.5, capped at 45000ms)")

    # Test 4: Timeout with exponential backoff
    print("\nTest 4: Consecutive timeouts trigger backoff")
    manager.record_timeout("https://timeout.com/page")
    timeout1, _ = manager.get_timeout("https://timeout.com/page")
    print(f"  After 1st timeout: {timeout1}ms")

    manager.record_timeout("https://timeout.com/page")
    timeout2, _ = manager.get_timeout("https://timeout.com/page")
    print(f"  After 2nd timeout: {timeout2}ms (should be ~1.5x higher)")

    # Test 5: Fast-fail on HTTP errors
    print("\nTest 5: Fast-fail on HTTP errors")
    should_fail = manager.record_http_error("https://error.com/page", 404)
    print(f"  HTTP 404: fast-fail = {should_fail} (expected True)")

    should_fail = manager.record_http_error("https://error.com/page", 200)
    print(f"  HTTP 200: fast-fail = {should_fail} (expected False)")

    # Test 6: Domain statistics
    print("\nTest 6: Domain statistics")
    stats = manager.get_domain_stats("example.com")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Test 7: Overall statistics
    print("\nTest 7: Overall statistics")
    stats = manager.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 80)
    print("TIMEOUT MANAGER TEST COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    test_timeout_manager()
