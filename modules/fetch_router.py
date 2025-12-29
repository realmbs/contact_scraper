"""
Smart Fetch Routing - Sprint 2.3

Intelligently routes page fetches to static (fast) or Playwright (slow) based on:
- URL patterns (directory, staff, faculty indicators)
- Historical success rates per domain
- Adaptive learning from fetch outcomes

This optimization targets 30-40% speedup by using static fetch when possible.

Author: Claude Code
Date: 2025-12-28
Sprint: 2.3
"""

import re
import json
from pathlib import Path
from typing import Optional, Dict, Tuple
from urllib.parse import urlparse
from collections import defaultdict
from modules.utils import setup_logger

logger = setup_logger("fetch_router")

# Cache file for domain statistics
CACHE_FILE = Path("output/cache/domain_fetch_stats.json")
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


class FetchRouter:
    """
    Intelligent router that decides whether to use static or Playwright fetch.

    Tracks success rates per domain and learns optimal fetch strategy.
    """

    def __init__(self):
        """Initialize fetch router with historical data."""
        self.domain_stats = defaultdict(lambda: {
            'static_success': 0,
            'static_total': 0,
            'playwright_success': 0,
            'playwright_total': 0,
            'last_method': None,
        })

        self.load_stats()

    def should_use_playwright(self, url: str, force: bool = False) -> Tuple[bool, str]:
        """
        Determine if URL should use Playwright based on patterns and history.

        Args:
            url: URL to fetch
            force: Force Playwright regardless of prediction

        Returns:
            Tuple of (use_playwright: bool, reason: str)
        """
        if force:
            return True, "forced"

        domain = self._extract_domain(url)
        url_lower = url.lower()

        # 1. URL pattern analysis (high confidence patterns)
        # These patterns strongly suggest JavaScript rendering needed
        playwright_patterns = [
            r'/directory/search',
            r'/people/search',
            r'/staff/ajax',
            r'/faculty/ajax',
            r'\?ajax=',
            r'#/people',
            r'#/staff',
            r'/api/directory',
            r'/directory\?',  # Directory pages with query params often use JS
            r'/faculty-staff/?\?',  # Faculty-staff pages with query params
            r'/expert-directory',  # Expert directories often dynamic
        ]

        for pattern in playwright_patterns:
            if re.search(pattern, url_lower):
                return True, f"pattern_match:{pattern}"

        # 2. Static-friendly patterns (likely work without JavaScript)
        # REDUCED: Many directory pages actually need Playwright
        static_patterns = [
            r'/about/staff',
            r'/about/faculty',
            r'/contact$',
            r'/administration$',
        ]

        static_match = False
        for pattern in static_patterns:
            if re.search(pattern, url_lower):
                static_match = True
                break

        # 3. Domain-based prediction (historical success rate)
        if domain in self.domain_stats:
            stats = self.domain_stats[domain]
            static_rate = self._success_rate(
                stats['static_success'], stats['static_total']
            )
            playwright_rate = self._success_rate(
                stats['playwright_success'], stats['playwright_total']
            )

            # If static has >70% success rate, use it
            if static_rate > 0.7 and stats['static_total'] >= 3:
                return False, f"domain_history:static_rate={static_rate:.1%}"

            # If static has low success but Playwright works, use Playwright
            if static_rate < 0.3 and playwright_rate > 0.7 and stats['playwright_total'] >= 2:
                return True, f"domain_history:playwright_rate={playwright_rate:.1%}"

        # 4. Default strategy based on URL patterns and keywords
        # Check if URL contains directory/faculty/staff keywords
        directory_keywords = ['directory', 'faculty', 'staff', 'people', 'expert']
        has_directory_keyword = any(kw in url_lower for kw in directory_keywords)

        if static_match:
            # URL pattern suggests static might work - try it
            return False, "static_pattern_match"
        elif has_directory_keyword and not static_match:
            # Contains directory keywords but no static pattern - likely needs Playwright
            return True, "directory_keyword_suggests_playwright"
        else:
            # No strong signal - default to static (faster), will fallback if needed
            return False, "default_static_first"

    def record_fetch_result(
        self,
        url: str,
        method: str,
        success: bool,
        found_contacts: int = 0
    ):
        """
        Record fetch result for adaptive learning.

        Args:
            url: URL that was fetched
            method: 'static' or 'playwright'
            success: Whether fetch was successful
            found_contacts: Number of contacts found (0 = failed)
        """
        domain = self._extract_domain(url)
        stats = self.domain_stats[domain]

        if method == 'static':
            stats['static_total'] += 1
            if success and found_contacts > 0:
                stats['static_success'] += 1
        elif method == 'playwright':
            stats['playwright_total'] += 1
            if success and found_contacts > 0:
                stats['playwright_success'] += 1

        stats['last_method'] = method

        # Save stats periodically (every 10 fetches)
        total_fetches = sum(
            s['static_total'] + s['playwright_total']
            for s in self.domain_stats.values()
        )
        if total_fetches % 10 == 0:
            self.save_stats()

    def get_domain_recommendation(self, domain: str) -> str:
        """
        Get recommended fetch method for a domain.

        Args:
            domain: Domain name

        Returns:
            Recommendation string
        """
        if domain not in self.domain_stats:
            return "No history for this domain"

        stats = self.domain_stats[domain]
        static_rate = self._success_rate(
            stats['static_success'], stats['static_total']
        )
        playwright_rate = self._success_rate(
            stats['playwright_success'], stats['playwright_total']
        )

        return (
            f"Static: {stats['static_success']}/{stats['static_total']} ({static_rate:.1%}) | "
            f"Playwright: {stats['playwright_success']}/{stats['playwright_total']} ({playwright_rate:.1%})"
        )

    def get_stats_summary(self) -> Dict:
        """
        Get summary statistics across all domains.

        Returns:
            Dictionary with aggregate stats
        """
        total_static = sum(s['static_total'] for s in self.domain_stats.values())
        total_static_success = sum(s['static_success'] for s in self.domain_stats.values())
        total_playwright = sum(s['playwright_total'] for s in self.domain_stats.values())
        total_playwright_success = sum(s['playwright_success'] for s in self.domain_stats.values())

        return {
            'domains_tracked': len(self.domain_stats),
            'static_total': total_static,
            'static_success': total_static_success,
            'static_rate': self._success_rate(total_static_success, total_static),
            'playwright_total': total_playwright,
            'playwright_success': total_playwright_success,
            'playwright_rate': self._success_rate(total_playwright_success, total_playwright),
            'total_fetches': total_static + total_playwright,
        }

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return url.lower()

    def _success_rate(self, success: int, total: int) -> float:
        """Calculate success rate (0-1)."""
        if total == 0:
            return 0.0
        return success / total

    def save_stats(self):
        """Save domain statistics to disk."""
        try:
            with open(CACHE_FILE, 'w') as f:
                # Convert defaultdict to regular dict for JSON serialization
                stats_dict = {k: dict(v) for k, v in self.domain_stats.items()}
                json.dump(stats_dict, f, indent=2)
            logger.debug(f"Saved fetch stats for {len(self.domain_stats)} domains")
        except Exception as e:
            logger.error(f"Failed to save fetch stats: {e}")

    def load_stats(self):
        """Load domain statistics from disk."""
        if not CACHE_FILE.exists():
            logger.debug("No cached fetch stats found")
            return

        try:
            with open(CACHE_FILE, 'r') as f:
                stats_dict = json.load(f)

            # Restore defaultdict structure
            for domain, stats in stats_dict.items():
                self.domain_stats[domain] = stats

            logger.info(f"Loaded fetch stats for {len(self.domain_stats)} domains")
        except Exception as e:
            logger.error(f"Failed to load fetch stats: {e}")


# ============================================================================
# Global router instance (singleton pattern)
# ============================================================================

_global_router: Optional[FetchRouter] = None


def get_fetch_router() -> FetchRouter:
    """
    Get or create the global fetch router instance.

    Returns:
        FetchRouter instance
    """
    global _global_router

    if _global_router is None:
        _global_router = FetchRouter()

    return _global_router


# ============================================================================
# Testing
# ============================================================================

def test_fetch_router():
    """
    Test fetch router functionality.
    """
    logger.info("=" * 80)
    logger.info("TESTING FETCH ROUTER")
    logger.info("=" * 80)

    router = FetchRouter()

    # Test URLs
    test_urls = [
        "https://law.stanford.edu/directory",
        "https://law.stanford.edu/directory/search?ajax=1",
        "https://law.stanford.edu/staff",
        "https://www.ucla.edu/about/staff",
        "https://api.example.edu/api/directory",
    ]

    logger.info("\n1. Testing URL pattern detection:")
    for url in test_urls:
        use_playwright, reason = router.should_use_playwright(url)
        method = "Playwright" if use_playwright else "Static"
        logger.info(f"  {url}")
        logger.info(f"    → {method} ({reason})")

    logger.info("\n2. Recording fetch results:")
    # Simulate fetches
    router.record_fetch_result("https://law.stanford.edu/directory", "static", True, 10)
    router.record_fetch_result("https://law.stanford.edu/directory", "static", True, 8)
    router.record_fetch_result("https://law.stanford.edu/faculty", "static", False, 0)
    router.record_fetch_result("https://law.stanford.edu/faculty", "playwright", True, 5)
    logger.info("  Recorded 4 fetch results")

    logger.info("\n3. Domain recommendations:")
    logger.info(f"  law.stanford.edu: {router.get_domain_recommendation('law.stanford.edu')}")

    logger.info("\n4. Summary statistics:")
    stats = router.get_stats_summary()
    for key, value in stats.items():
        if isinstance(value, float):
            logger.info(f"  {key}: {value:.1%}" if 'rate' in key else f"  {key}: {value:.2f}")
        else:
            logger.info(f"  {key}: {value}")

    logger.info("\n" + "=" * 80)
    logger.info("FETCH ROUTER TEST COMPLETE")
    logger.info("=" * 80)


if __name__ == '__main__':
    test_fetch_router()
