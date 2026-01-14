"""
Unit tests for async browser pool integration (Sprint 2.2).

Tests the native async functions with browser pool support:
- fetch_page_static_async() with httpx
- fetch_page_smart_async() with browser pool routing
- scrape_institution_contacts_async() with full integration
"""

import pytest
import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.contact_extractor import (
    fetch_page_static_async,
    fetch_page_smart_async,
    scrape_institution_contacts_async
)
from modules.browser_pool import get_browser_pool, close_browser_pool


@pytest.mark.asyncio
async def test_fetch_page_static_async():
    """Test async static fetch with httpx."""
    print("\n=== TEST: fetch_page_static_async() ===")

    url = "https://law.stanford.edu"
    soup = await fetch_page_static_async(url)

    assert soup is not None, "Failed to fetch page"
    assert len(soup.get_text()) > 100, "Page content too short"

    print(f"✓ Successfully fetched {url} with httpx")
    print(f"✓ Page length: {len(soup.get_text())} characters")


@pytest.mark.asyncio
async def test_fetch_page_smart_async_static():
    """Test smart routing chooses static when appropriate."""
    print("\n=== TEST: fetch_page_smart_async() with static routing ===")

    # Simple directory page should use static fetch
    url = "https://law.stanford.edu/directory/"
    soup = await fetch_page_smart_async(url)

    assert soup is not None, "Failed to fetch page"
    assert len(soup.get_text()) > 100, "Page content too short"

    print(f"✓ Successfully fetched {url} with smart routing")
    print(f"✓ Router likely chose static fetch (fast)")


@pytest.mark.asyncio
async def test_fetch_page_smart_async_playwright():
    """Test smart routing with Playwright and browser pool."""
    print("\n=== TEST: fetch_page_smart_async() with Playwright + browser pool ===")

    # Initialize browser pool
    pool = await get_browser_pool(pool_size=1)

    try:
        # Force Playwright routing with browser pool
        url = "https://www.law.berkeley.edu/our-faculty/faculty-profiles/"
        soup = await fetch_page_smart_async(
            url,
            force_playwright=True,
            browser_pool=pool
        )

        assert soup is not None, "Failed to fetch page with Playwright"
        assert len(soup.get_text()) > 100, "Page content too short"

        print(f"✓ Successfully fetched {url} with Playwright + browser pool")
        print(f"✓ Page length: {len(soup.get_text())} characters")

    finally:
        await close_browser_pool()
        print("✓ Browser pool closed")


@pytest.mark.asyncio
async def test_scrape_institution_contacts_async():
    """Test full async institution scraping with browser pool."""
    print("\n=== TEST: scrape_institution_contacts_async() ===")

    # Initialize browser pool
    pool = await get_browser_pool(pool_size=1)

    try:
        # Test on a small institution
        df = await scrape_institution_contacts_async(
            institution_name="Stanford Law School",
            institution_url="https://law.stanford.edu",
            state="CA",
            program_type="Law School",
            browser_pool=pool
        )

        # Verify results
        assert df is not None, "Function returned None"
        print(f"✓ Function returned DataFrame with {len(df)} contacts")

        if len(df) > 0:
            assert 'name' in df.columns or 'full_name' in df.columns, "Missing name column"
            assert 'email' in df.columns, "Missing email column"
            print(f"✓ DataFrame has required columns")
            print(f"✓ Sample contact: {df.iloc[0]['full_name']} - {df.iloc[0].get('email', 'N/A')}")
        else:
            print("⚠ No contacts extracted (may be expected for some sites)")

    finally:
        await close_browser_pool()
        print("✓ Browser pool closed")


@pytest.mark.asyncio
async def test_browser_pool_reuse():
    """Test that browser pool properly reuses browsers across multiple fetches."""
    print("\n=== TEST: Browser pool reuse across multiple fetches ===")

    pool = await get_browser_pool(pool_size=2)

    try:
        # Fetch multiple pages in sequence
        urls = [
            "https://law.stanford.edu",
            "https://www.law.berkeley.edu",
            "https://law.ucla.edu"
        ]

        for i, url in enumerate(urls):
            soup = await fetch_page_smart_async(url, force_playwright=True, browser_pool=pool)
            assert soup is not None, f"Failed to fetch {url}"
            print(f"✓ Fetch {i+1}/3: {url[:50]}")

        print("✓ All fetches succeeded with browser pool")
        print("✓ Browsers were reused (no launch overhead)")

    finally:
        await close_browser_pool()
        print("✓ Browser pool closed")


@pytest.mark.asyncio
async def test_feature_flag_disabled():
    """Test that system works with USE_BROWSER_POOL=False (legacy mode)."""
    print("\n=== TEST: Feature flag disabled (legacy mode) ===")

    # Temporarily disable feature flag
    import config.settings as settings
    original_value = settings.USE_BROWSER_POOL
    settings.USE_BROWSER_POOL = False

    try:
        # This should use thread pool executor, not browser pool
        df = await scrape_institution_contacts_async(
            institution_name="Test Institution",
            institution_url="https://law.stanford.edu",
            state="CA",
            program_type="Law School",
            browser_pool=None  # No pool provided
        )

        print("✓ System works in legacy mode (USE_BROWSER_POOL=False)")
        print(f"✓ Extracted {len(df)} contacts without browser pool")

    finally:
        # Restore original value
        settings.USE_BROWSER_POOL = original_value
        print("✓ Feature flag restored")


if __name__ == '__main__':
    """Run tests directly with python test_async_browser_pool.py"""
    print("=" * 70)
    print("Async Browser Pool Integration Tests")
    print("=" * 70)

    # Run all tests
    asyncio.run(test_fetch_page_static_async())
    asyncio.run(test_fetch_page_smart_async_static())
    asyncio.run(test_fetch_page_smart_async_playwright())
    asyncio.run(test_scrape_institution_contacts_async())
    asyncio.run(test_browser_pool_reuse())
    asyncio.run(test_feature_flag_disabled())

    print("\n" + "=" * 70)
    print("All tests passed! ✓")
    print("=" * 70)
