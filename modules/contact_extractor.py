"""
Contact Extraction Module for Legal Education Contact Scraper.

Extracts contact information from law school and paralegal program websites.
Uses intelligent directory discovery, fuzzy title matching, and email pattern detection.
"""

import re
import time
import signal
import asyncio
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urljoin, urlparse
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup
from loguru import logger
from fuzzywuzzy import fuzz
from fake_useragent import UserAgent

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import TimeoutError as AsyncPlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightTimeoutError = Exception
    AsyncPlaywrightTimeoutError = Exception
    logger.warning("Playwright not available. Install with: pip install playwright && playwright install")

from config.settings import (
    LAW_SCHOOL_ROLES,
    PARALEGAL_PROGRAM_ROLES,
    ALL_TARGET_ROLES,
    LAW_SCHOOL_ROLES_EXPANDED,
    PARALEGAL_PROGRAM_ROLES_EXPANDED,
    USE_RANDOM_USER_AGENT,
    REQUEST_TIMEOUT,
    RATE_LIMIT_DELAY,
    MIN_CONFIDENCE_SCORE,
    ENABLE_PLAYWRIGHT,
    PLAYWRIGHT_TIMEOUT,
    SAVE_SCREENSHOTS,
    SCREENSHOTS_DIR,
    HEADLESS_BROWSER,
    ENABLE_ASYNC_PROFILE_LINKS,
    PROFILE_LINK_CONCURRENCY,
    ENABLE_ASYNC_DIRECTORIES,
    DIRECTORY_CONCURRENCY,
)
from modules.utils import (
    setup_logger,
    rate_limit,
    validate_url,
    normalize_url,
    clean_text,
    extract_email,
    extract_phone,
    parse_name,
    extract_domain,
    get_timestamp,
)
from modules.title_normalizer import (
    normalize_title,
    should_exclude_title,
    NormalizedTitle,
)
from modules.timeout_manager import get_timeout_manager
from modules.domain_rate_limiter import get_domain_rate_limiter
from modules.page_classifier import get_page_classifier, PageType
from modules.link_extractor import get_link_extractor
from modules.email_deobfuscator import get_email_deobfuscator

# Initialize logger
setup_logger("contact_extractor")

# =============================================================================
# Signal Handling for Graceful Shutdown (Progressive Saves Feature)
# =============================================================================

# Global shutdown flag for Ctrl+C handling
_shutdown_requested = False

def _signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) and SIGTERM gracefully"""
    global _shutdown_requested
    if not _shutdown_requested:  # Only log once
        _shutdown_requested = True
        logger.warning("=" * 70)
        logger.warning("SHUTDOWN REQUESTED - Finishing current institutions...")
        logger.warning("Partial results will be saved. Press Ctrl+C again to force quit.")
        logger.warning("=" * 70)
    else:
        logger.error("Force quit requested. Exiting immediately...")
        raise KeyboardInterrupt

def setup_signal_handlers():
    """Register signal handlers for graceful shutdown"""
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    logger.debug("Signal handlers registered for graceful shutdown")

# Initialize timeout manager (Sprint 3.3)
timeout_manager = get_timeout_manager(default_timeout=PLAYWRIGHT_TIMEOUT)

# Initialize domain rate limiter (Sprint 3.1)
domain_rate_limiter = get_domain_rate_limiter(default_delay=2.0)

# Initialize multi-tier extraction modules (Multi-Tier Phase 1)
page_classifier = get_page_classifier()
link_extractor = get_link_extractor(max_links=30, min_score=35)  # Multi-Tier Phase 5.1: Lowered from 40→35
email_deobfuscator = get_email_deobfuscator()

# User agent for requests
ua = UserAgent() if USE_RANDOM_USER_AGENT else None


def get_user_agent() -> str:
    """Get user agent string."""
    if USE_RANDOM_USER_AGENT and ua:
        return ua.random
    return 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'


# =============================================================================
# Playwright Integration for JavaScript-heavy Sites
# =============================================================================

def fetch_page_with_playwright(url: str) -> Optional[BeautifulSoup]:
    """
    Fetch a web page using Playwright (headless browser with JavaScript support).

    Uses intelligent timeout tuning based on domain performance (Sprint 3.3).

    Args:
        url: URL to fetch

    Returns:
        BeautifulSoup object or None if failed
    """
    if not PLAYWRIGHT_AVAILABLE or not ENABLE_PLAYWRIGHT:
        return None

    # Per-domain rate limiting (Sprint 3.1)
    domain_rate_limiter.wait_if_needed(url)

    # Get adaptive timeout for this domain (Sprint 3.3)
    page_timeout, selector_timeout = timeout_manager.get_timeout(url)
    start_time = time.time()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=HEADLESS_BROWSER)
            context = browser.new_context(
                user_agent=get_user_agent(),
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()

            logger.info(f"Fetching with Playwright: {url} (timeout: {page_timeout}ms)")

            # Navigate to page (use domcontentloaded for better reliability)
            page.goto(url, wait_until='domcontentloaded', timeout=page_timeout)

            # Wait for common content selectors to appear
            common_selectors = [
                '.profile', '.person', '.staff', '.faculty', '.contact',
                '[class*="profile"]', '[class*="person"]', '[class*="staff"]',
                'table', '.directory', '[role="main"]'
            ]

            # Multi-Tier Phase 5.1: Add directory-specific link selectors for JS-rendered content
            if 'directory' in url.lower() or 'people' in url.lower() or 'faculty' in url.lower() or 'staff' in url.lower():
                common_selectors.insert(0, 'a[href*="profile"]')  # High priority for profile links
                common_selectors.insert(0, 'a[href*="/people/"]')
                common_selectors.insert(0, '.person-card')
                common_selectors.insert(0, '.faculty-card')

            for selector in common_selectors:
                try:
                    page.wait_for_selector(selector, timeout=selector_timeout)
                    logger.debug(f"Found selector: {selector}")
                    break
                except PlaywrightTimeoutError:
                    continue

            # Additional wait for dynamic content
            page.wait_for_timeout(2000)

            # Get page content
            content = page.content()

            # Save screenshot if enabled
            if SAVE_SCREENSHOTS:
                screenshot_path = SCREENSHOTS_DIR / f"{extract_domain(url)}_{get_timestamp()}.png"
                page.screenshot(path=str(screenshot_path))
                logger.debug(f"Screenshot saved: {screenshot_path}")

            browser.close()

            # Record success with load time
            load_time = time.time() - start_time
            timeout_manager.record_success(url, load_time)
            domain_rate_limiter.record_success(url)

            soup = BeautifulSoup(content, 'html.parser')
            logger.success(f"Successfully fetched with Playwright: {url} ({load_time:.1f}s)")
            return soup

    except PlaywrightTimeoutError as e:
        timeout_manager.record_timeout(url)
        domain_rate_limiter.record_error(url, status_code=None)
        logger.error(f"Playwright timeout for {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Playwright error for {url}: {e}")
        # Check if it's an HTTP error and record it
        status_code = getattr(e, 'status_code', None)
        if status_code:
            timeout_manager.record_http_error(url, status_code)
            domain_rate_limiter.record_error(url, status_code)
        else:
            domain_rate_limiter.record_error(url, status_code=None)
        return None


async def fetch_page_with_playwright_async(url: str, browser_pool=None) -> Optional[BeautifulSoup]:
    """
    Fetch a web page using Playwright with browser pooling (async version).

    This is the optimized version that uses persistent browsers from a pool,
    eliminating the 2-3s browser launch overhead on every fetch.

    Args:
        url: URL to fetch
        browser_pool: BrowserPool instance (if None, creates one)

    Returns:
        BeautifulSoup object or None if failed
    """
    if not PLAYWRIGHT_AVAILABLE or not ENABLE_PLAYWRIGHT:
        return None

    # Import here to avoid circular dependency
    from modules.browser_pool import get_browser_pool

    try:
        # Get or create browser pool
        if browser_pool is None:
            browser_pool = await get_browser_pool(pool_size=3)

        # Acquire browser from pool
        browser, context, page = await browser_pool.acquire()

        try:
            logger.info(f"Fetching with Playwright: {url}")

            # Navigate to page (use domcontentloaded for better reliability)
            await page.goto(url, wait_until='domcontentloaded', timeout=PLAYWRIGHT_TIMEOUT)

            # Wait for common content selectors to appear
            common_selectors = [
                '.profile', '.person', '.staff', '.faculty', '.contact',
                '[class*="profile"]', '[class*="person"]', '[class*="staff"]',
                'table', '.directory', '[role="main"]'
            ]

            for selector in common_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=3000)
                    logger.debug(f"Found selector: {selector}")
                    break
                except AsyncPlaywrightTimeoutError:
                    continue

            # Additional wait for dynamic content
            await page.wait_for_timeout(2000)

            # Get page content
            content = await page.content()

            # Save screenshot if enabled
            if SAVE_SCREENSHOTS:
                screenshot_path = SCREENSHOTS_DIR / f"{extract_domain(url)}_{get_timestamp()}.png"
                await page.screenshot(path=str(screenshot_path))
                logger.debug(f"Screenshot saved: {screenshot_path}")

            soup = BeautifulSoup(content, 'html.parser')
            logger.success(f"Successfully fetched with Playwright: {url}")

            return soup

        finally:
            # Always release browser back to pool
            await browser_pool.release(browser, context, page)

    except AsyncPlaywrightTimeoutError as e:
        logger.error(f"Playwright timeout for {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Playwright error for {url}: {e}")
        return None


def fetch_page_static(url: str) -> Optional[BeautifulSoup]:
    """
    Fetch a web page using requests (static HTML only).

    Args:
        url: URL to fetch

    Returns:
        BeautifulSoup object or None if failed
    """
    import requests

    headers = {
        'User-Agent': get_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }

    try:
        logger.info(f"Fetching (static): {url}")
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.success(f"Successfully fetched (static): {url}")
        return soup

    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


async def fetch_page_static_async(url: str) -> Optional[BeautifulSoup]:
    """
    Async version of fetch_page_static using httpx (Sprint 2.2).

    Integrates with timeout_manager and domain_rate_limiter for
    adaptive performance tuning.

    Args:
        url: URL to fetch

    Returns:
        BeautifulSoup object or None if failed
    """
    import httpx
    from modules.timeout_manager import get_timeout_manager
    from modules.domain_rate_limiter import get_domain_rate_limiter
    import time

    timeout_manager = get_timeout_manager()
    rate_limiter = get_domain_rate_limiter()

    # Async rate limiting (wait if needed)
    await rate_limiter.wait_if_needed_async(url)

    # Get adaptive timeout for this domain
    timeout = timeout_manager.get_timeout(url)

    headers = {
        'User-Agent': get_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }

    try:
        logger.info(f"Fetching (async static): {url}")
        start_time = time.time()

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            elapsed = time.time() - start_time

            # Record success with load time for adaptive learning
            timeout_manager.record_success(url, elapsed)
            rate_limiter.record_success(url)

            soup = BeautifulSoup(response.text, 'html.parser')
            logger.success(f"Successfully fetched (async static): {url} ({elapsed:.2f}s)")
            return soup

    except httpx.TimeoutException:
        timeout_manager.record_timeout(url)
        logger.warning(f"Timeout fetching {url} ({timeout}s)")
        return None
    except httpx.HTTPStatusError as e:
        # Record HTTP error for fast-fail logic
        status_code = e.response.status_code
        timeout_manager.record_http_error(url, status_code)
        logger.error(f"HTTP {status_code} error fetching {url}")
        return None
    except Exception as e:
        # Generic error - record as HTTP 500
        timeout_manager.record_http_error(url, 500)
        logger.error(f"Error fetching {url}: {e}")
        return None


def fetch_page_smart(url: str, force_playwright: bool = False) -> Optional[BeautifulSoup]:
    """
    Smart page fetching with intelligent routing (Sprint 2.3).

    Routes to static (fast) or Playwright (slow) based on:
    - URL patterns (directory, API endpoints, etc.)
    - Historical success rates per domain
    - Page content analysis

    Args:
        url: URL to fetch
        force_playwright: Skip static fetch and use Playwright directly

    Returns:
        BeautifulSoup object or None if failed
    """
    # Import fetch router (lazy import to avoid circular dependency)
    from modules.fetch_router import get_fetch_router
    router = get_fetch_router()

    # Get routing recommendation
    use_playwright, reason = router.should_use_playwright(url, force=force_playwright)

    if use_playwright and ENABLE_PLAYWRIGHT and PLAYWRIGHT_AVAILABLE:
        logger.info(f"Routing to Playwright: {reason}")
        soup = fetch_page_with_playwright(url)
        router.record_fetch_result(url, 'playwright', soup is not None)
        return soup

    # Router recommended static - try it first
    logger.info(f"Routing to static: {reason}")
    soup = fetch_page_static(url)

    if soup:
        # Check if page has meaningful contact content
        text_content = soup.get_text(strip=True)

        # Count potential contact indicators
        has_emails = len(soup.find_all('a', href=re.compile(r'mailto:', re.I)))
        has_contact_sections = len(soup.find_all(['div', 'section', 'article'], class_=lambda x: x and any(
            keyword in str(x).lower() for keyword in ['profile', 'person', 'staff', 'faculty', 'contact']
        )))

        # Determine if static fetch was successful
        has_content = has_emails > 5 or has_contact_sections > 5
        lacks_content = len(text_content) < 500 or (has_emails == 0 and has_contact_sections == 0)

        # Record result
        if has_content:
            logger.debug(f"Page has contact indicators (emails: {has_emails}, sections: {has_contact_sections})")
            router.record_fetch_result(url, 'static', True, has_emails + has_contact_sections)
            return soup

        # Page lacks contact data - try Playwright as fallback
        if lacks_content:
            logger.info(f"Page lacks contact data (chars: {len(text_content)}, emails: {has_emails}, sections: {has_contact_sections}), trying Playwright...")
            router.record_fetch_result(url, 'static', False, 0)

            if ENABLE_PLAYWRIGHT and PLAYWRIGHT_AVAILABLE:
                playwright_soup = fetch_page_with_playwright(url)
                if playwright_soup:
                    router.record_fetch_result(url, 'playwright', True)
                    return playwright_soup
                else:
                    router.record_fetch_result(url, 'playwright', False, 0)

        # Static worked but no strong indicators - return it anyway
        router.record_fetch_result(url, 'static', True, 1)
        return soup

    # Static fetch failed completely - try Playwright
    logger.info("Static fetch failed, trying Playwright...")
    router.record_fetch_result(url, 'static', False, 0)

    if ENABLE_PLAYWRIGHT and PLAYWRIGHT_AVAILABLE:
        playwright_soup = fetch_page_with_playwright(url)
        success = playwright_soup is not None
        router.record_fetch_result(url, 'playwright', success, 1 if success else 0)
        return playwright_soup

    return None


async def fetch_page_smart_async(
    url: str,
    force_playwright: bool = False,
    browser_pool=None
) -> Optional[BeautifulSoup]:
    """
    Async version of fetch_page_smart with browser pool support (Sprint 2.2).

    Smart routing between static (httpx) and Playwright (browser pool) based on:
    - URL patterns (directory, API endpoints, etc.)
    - Historical success rates per domain
    - Page content analysis

    Args:
        url: URL to fetch
        force_playwright: Skip static fetch and use Playwright directly
        browser_pool: Optional browser pool instance for Playwright fetches

    Returns:
        BeautifulSoup object or None if failed
    """
    from modules.fetch_router import get_fetch_router
    router = get_fetch_router()

    # Get routing recommendation
    use_playwright, reason = router.should_use_playwright(url, force=force_playwright)

    if use_playwright and ENABLE_PLAYWRIGHT and PLAYWRIGHT_AVAILABLE:
        logger.info(f"Routing to Playwright (async): {reason}")
        soup = await fetch_page_with_playwright_async(url, browser_pool=browser_pool)
        router.record_fetch_result(url, 'playwright', soup is not None)
        return soup

    # Router recommended static - try it first
    logger.info(f"Routing to static (async): {reason}")
    soup = await fetch_page_static_async(url)

    if soup:
        # Check if page has meaningful contact content
        text_content = soup.get_text(strip=True)

        # Count potential contact indicators
        has_emails = len(soup.find_all('a', href=re.compile(r'mailto:', re.I)))
        has_contact_sections = len(soup.find_all(['div', 'section', 'article'], class_=lambda x: x and any(
            keyword in str(x).lower() for keyword in ['profile', 'person', 'staff', 'faculty', 'contact']
        )))

        # Determine if static fetch was successful
        has_content = has_emails > 5 or has_contact_sections > 5
        lacks_content = len(text_content) < 500 or (has_emails == 0 and has_contact_sections == 0)

        # Record result
        if has_content:
            logger.debug(f"Page has contact indicators (emails: {has_emails}, sections: {has_contact_sections})")
            router.record_fetch_result(url, 'static', True, has_emails + has_contact_sections)
            return soup

        # Page lacks contact data - try Playwright as fallback
        if lacks_content:
            logger.info(f"Page lacks contact data (chars: {len(text_content)}, emails: {has_emails}, sections: {has_contact_sections}), trying Playwright...")
            router.record_fetch_result(url, 'static', False, 0)

            if ENABLE_PLAYWRIGHT and PLAYWRIGHT_AVAILABLE:
                playwright_soup = await fetch_page_with_playwright_async(url, browser_pool=browser_pool)
                if playwright_soup:
                    router.record_fetch_result(url, 'playwright', True)
                    return playwright_soup
                else:
                    router.record_fetch_result(url, 'playwright', False, 0)

        # Static worked but no strong indicators - return it anyway
        router.record_fetch_result(url, 'static', True, 1)
        return soup

    # Static fetch failed completely - try Playwright
    logger.info("Static fetch failed, trying Playwright...")
    router.record_fetch_result(url, 'static', False, 0)

    if ENABLE_PLAYWRIGHT and PLAYWRIGHT_AVAILABLE:
        playwright_soup = await fetch_page_with_playwright_async(url, browser_pool=browser_pool)
        success = playwright_soup is not None
        router.record_fetch_result(url, 'playwright', success, 1 if success else 0)
        return playwright_soup

    return None


# =============================================================================
# Title Matching with Fuzzy Logic
# =============================================================================

def match_title_to_role(
    title: str,
    target_roles: List[str],
    threshold: int = 70,
    return_all_matches: bool = False
) -> Tuple[Optional[str], int, int, Optional[List[Tuple[str, int]]], Optional[NormalizedTitle]]:
    """
    Match a job title to target roles using intelligent normalization + fuzzy matching.

    NEW FEATURES (Phase 1 - Intelligent Matching):
    - Title normalization (expand abbreviations, extract modifiers)
    - Exclusion filtering (student, emeritus, visiting roles)
    - Granular 5-tier confidence scoring
    - Multi-role extraction (capture all matching roles)
    - Metadata preservation (interim, acting, co-director flags)

    Uses multiple fuzzy matching strategies:
    1. Token sort ratio (handles word order variations)
    2. Partial ratio (handles titles with extra words)
    3. Keyword detection (specific role keywords)

    Args:
        title: Raw job title to match
        target_roles: List of target role names
        threshold: Minimum fuzzy match score (0-100)
        return_all_matches: If True, return all roles above threshold (not just best)

    Returns:
        Tuple of (matched_role, confidence_score, match_score, all_matches, normalized_title)
        - matched_role: Best matching role name or None
        - confidence_score: Confidence points for scoring (0-20)
        - match_score: Fuzzy match score (0-100)
        - all_matches: List of (role, score) tuples for all matches (if return_all_matches=True)
        - normalized_title: NormalizedTitle object with metadata
    """
    if not title or not isinstance(title, str):
        return None, 0, 0, None, None

    # Step 1: Quick exclusion check (fast pre-filter)
    if should_exclude_title(title):
        logger.debug(f"Title excluded: {title}")
        return None, 0, 0, None, None

    # Step 2: Normalize title
    normalized = normalize_title(title)

    # Double-check exclusion after normalization
    if normalized.should_exclude:
        logger.debug(f"Title excluded after normalization: {title} → {normalized.normalized}")
        return None, 0, 0, None, normalized

    # Step 3: Use normalized title for fuzzy matching
    title_clean = clean_text(normalized.normalized).lower()

    if not title_clean:
        return None, 0, 0, None, normalized

    # Step 4: Find all matching roles
    role_matches = []  # List of (role, score) tuples

    for role in target_roles:
        role_clean = clean_text(role).lower()

        # Calculate fuzzy match scores
        token_sort = fuzz.token_sort_ratio(title_clean, role_clean)
        partial = fuzz.partial_ratio(title_clean, role_clean)
        simple = fuzz.ratio(title_clean, role_clean)

        # Use the best score from different methods
        score = max(token_sort, partial, simple)

        # Smarter keyword matching - require role-specific words, not just generic titles
        role_words = set(role_clean.split())
        title_words = set(title_clean.split())
        common_words = role_words.intersection(title_words)

        # Generic role words (don't boost score on these alone)
        generic_role_words = {'director', 'dean', 'coordinator', 'assistant', 'associate',
                             'manager', 'head', 'chair', 'chief', 'officer'}

        # Role-specific context words (these ARE meaningful)
        context_words = {'library', 'librarian', 'it', 'information', 'technology', 'internet',
                        'clinical', 'legal', 'writing', 'academic', 'affairs', 'student',
                        'students', 'experiential', 'learning', 'paralegal', 'services',
                        'reference', 'instructional', 'programs', 'clinic', 'faculty'}

        # Check if we have meaningful matching words (not just generic titles)
        generic_matches = common_words.intersection(generic_role_words)
        context_matches = common_words.intersection(context_words)
        other_matches = common_words - generic_matches - context_matches

        # Only boost if we have role-specific matches (context or other non-generic words)
        meaningful_matches = context_matches.union(other_matches)

        if meaningful_matches:
            # Boost based on meaningful word matches (not just "director" or "dean")
            word_boost = min(10, len(meaningful_matches) * 5)
            score = min(100, score + word_boost)

        # Penalty: Professor titles shouldn't match administrative director roles
        if 'professor' in title_words and 'professor' not in role_words:
            # Strong penalty unless this is a faculty director/dean role
            if not any(word in role_clean for word in ['faculty', 'academic', 'dean']):
                score = max(0, score - 20)  # Heavy penalty for professor → admin mismatch

        # Penalty: Highly specific roles require their context word to match
        # Example: "IT Director" requires "IT" or "technology" in title
        highly_specific_roles = {
            'it': ['it', 'information', 'technology', 'internet'],
            'library': ['library', 'librarian'],
            'clinical': ['clinical', 'clinic'],
            'legal writing': ['legal', 'writing'],
            'experiential': ['experiential', 'learning'],
            'paralegal': ['paralegal'],
        }

        for specific_keyword, required_words in highly_specific_roles.items():
            if specific_keyword in role_clean:
                # Check if ANY of the required words appear in title
                if not any(req_word in title_clean for req_word in required_words):
                    # Title doesn't have the specific context - heavy penalty
                    score = max(0, score - 25)
                    break  # Only apply one penalty

        # Collect all matches above threshold
        if score >= threshold:
            role_matches.append((role, score))

    # Sort by score (best first)
    role_matches.sort(key=lambda x: x[1], reverse=True)

    if not role_matches:
        return None, 0, 0, None, normalized

    # Step 5: Get best match
    best_match, best_score = role_matches[0]

    # Step 6: Calculate confidence points (0-20 for title match) - GRANULAR 5-TIER SYSTEM
    if best_score >= 90:
        base_confidence = 20  # Exact or very close match
    elif best_score >= 85:
        base_confidence = 17  # Near-exact match
    elif best_score >= 80:
        base_confidence = 14  # Strong match
    elif best_score >= 75:
        base_confidence = 11  # Good match
    elif best_score >= 70:
        base_confidence = 8   # Acceptable match
    else:
        base_confidence = 0   # Below threshold (shouldn't happen)

    # Step 7: Apply confidence modifiers from normalization
    confidence_score = base_confidence + normalized.confidence_modifier
    confidence_score = max(0, min(20, confidence_score))  # Clamp to 0-20

    # Step 8: Return results
    all_matches = role_matches if return_all_matches else None

    return best_match, confidence_score, best_score, all_matches, normalized


def calculate_contact_confidence(
    has_email: bool,
    email_on_site: bool,
    email_validated: bool,
    email_is_catchall: bool,
    title_match_score: int,
    has_phone: bool,
    linkedin_verified: bool = False
) -> int:
    """
    Calculate confidence score for a contact (0-100).

    Scoring breakdown:
    +40: Email found on official website
    +30: Email validated as deliverable
    +20: Title exactly matches target role (90+ match)
    +10: Title good match (70-89 match)
    +10: Phone number found
    +10: LinkedIn profile confirms employment
    -20: Email is catch-all domain
    -30: Email constructed from pattern (not verified)

    Args:
        has_email: Contact has an email address
        email_on_site: Email found on institution website
        email_validated: Email validated via API
        email_is_catchall: Email is from catch-all domain
        title_match_score: Fuzzy match score for title (0-100)
        has_phone: Contact has phone number
        linkedin_verified: LinkedIn confirms current employment

    Returns:
        Confidence score (0-100)
    """
    score = 0

    # Email scoring
    if has_email:
        if email_on_site:
            score += 40
        else:
            score -= 30  # Constructed email

        if email_validated:
            score += 30

        if email_is_catchall:
            score -= 20

    # Title scoring
    if title_match_score >= 90:
        score += 20
    elif title_match_score >= 70:
        score += 10

    # Additional data points
    if has_phone:
        score += 10

    if linkedin_verified:
        score += 10

    # Ensure score is in valid range
    score = max(0, min(100, score))

    return score


# =============================================================================
# Directory Page Discovery
# =============================================================================

def find_directory_pages(
    base_url: str,
    soup: BeautifulSoup,
    program_type: str = 'law'
) -> List[str]:
    """
    Find directory/staff pages on institution website with intelligent prioritization.

    Scores URLs based on likelihood of containing target contacts:
    - High priority (score 100): /profiles, /directory, /personnel, /staff-directory
    - Medium priority (score 50): /faculty, /staff, /administration
    - Low priority (score 25): /about/people, /team
    - Excluded (score 0): /admissions, /scholarship, /news, /contact-us

    Args:
        base_url: Institution's base URL
        soup: BeautifulSoup object of homepage
        program_type: 'law' or 'paralegal' for context-specific searching

    Returns:
        List of directory page URLs sorted by priority (best first)
    """
    directory_urls = {}  # URL -> priority score

    # HIGH PRIORITY patterns (score: 100) - most likely to have contacts
    high_priority_patterns = [
        r'profile',      # /faculty/profiles, /staff-profiles
        r'directory',    # /directory, /staff-directory, /people-directory
        r'personnel',    # /personnel, /staff-personnel
        r'bio',          # /bios, /faculty-bios
        r'roster',       # /staff-roster, /faculty-roster
        r'listing',      # /faculty-listing
    ]

    # MEDIUM PRIORITY patterns (score: 50)
    medium_priority_patterns = [
        r'faculty(?!.*scholarship)(?!.*workshop)',  # /faculty but NOT /faculty/scholarship
        r'staff(?!.*portal)',                        # /staff but NOT /staff-portal
        r'people(?!.*\babout\b)',                    # /people but NOT /about/people
        r'administration',
        r'leadership',
        r'team',
    ]

    # LOW PRIORITY patterns (score: 25) - less likely but still worth checking
    low_priority_patterns = [
        r'about.*people',
        r'about.*staff',
        r'about.*faculty',
        r'contact.*directory',  # /contact-directory OK
    ]

    # Program-specific patterns
    if program_type == 'law':
        high_priority_patterns.extend([
            r'library.*staff',      # /library/staff
            r'faculty.*profiles',   # /faculty/profiles
        ])
        medium_priority_patterns.extend([
            r'clinical.*faculty',
            r'academic.*affairs',
        ])
    elif program_type == 'paralegal':
        high_priority_patterns.extend([
            r'paralegal.*faculty',
            r'legal.*studies.*faculty',
        ])
        medium_priority_patterns.extend([
            r'department.*staff',
        ])

    # EXCLUSION patterns - skip these URLs entirely (Multi-Tier Phase 3: Enhanced)
    exclusion_patterns = [
        r'admissions?(?!.*staff)',   # /admissions, /admission (unless /admissions-staff)
        r'scholarship',               # /faculty/scholarship
        r'workshop',                  # /faculty/workshops
        r'apply',                     # /apply, /how-to-apply
        r'contact-us',                # /contact-us forms
        r'contact\b(?!.*directory)',  # /contact (unless /contact-directory)
        r'news',                      # /news
        r'events?',                   # /events
        r'calendar',                  # /calendar
        r'student.*portal',           # /student-portal
        r'student.*directory',        # /student-directory (Multi-Tier Phase 3)
        r'student.*profiles?',        # /student-profiles (Multi-Tier Phase 3)
        r'student.*roster',           # /student-roster
        r'grades?\b',                 # /grades (Multi-Tier Phase 3)
        r'portal\b',                  # /portal (Multi-Tier Phase 3)
        r'alumni',                    # /alumni
        r'donate',                    # /donate
        r'giving',                    # /giving
        r'instagram\.com',            # Social media (Multi-Tier Phase 3)
        r'twitter\.com',              # Social media
        r'facebook\.com',             # Social media
        r'linkedin\.com',             # Social media
        r'youtube\.com',              # Social media
        r'bluesky\.',                 # Social media
        r'outlook\.office',           # Office 365 portal (Multi-Tier Phase 3)
    ]

    # Find all links on homepage
    for link in soup.find_all('a', href=True):
        href = link['href'].lower()
        text = clean_text(link.get_text()).lower()

        # Construct absolute URL
        full_url = urljoin(base_url, link['href'])

        # Validate URL
        if not validate_url(full_url):
            continue

        # Normalize URL
        normalized_url = normalize_url(full_url)

        # Check exclusions first
        excluded = False
        for pattern in exclusion_patterns:
            if re.search(pattern, href) or re.search(pattern, text):
                excluded = True
                logger.debug(f"Excluded URL (matches {pattern}): {normalized_url}")
                break

        if excluded:
            continue

        # Calculate priority score
        score = 0
        matched_pattern = None

        # Check high priority
        for pattern in high_priority_patterns:
            if re.search(pattern, href) or re.search(pattern, text):
                score = 100
                matched_pattern = pattern
                break

        # Check medium priority if not high
        if score == 0:
            for pattern in medium_priority_patterns:
                if re.search(pattern, href) or re.search(pattern, text):
                    score = 50
                    matched_pattern = pattern
                    break

        # Check low priority if still not matched
        if score == 0:
            for pattern in low_priority_patterns:
                if re.search(pattern, href) or re.search(pattern, text):
                    score = 25
                    matched_pattern = pattern
                    break

        # Add to results if matched
        if score > 0:
            # If URL already exists, keep higher score
            if normalized_url in directory_urls:
                directory_urls[normalized_url] = max(directory_urls[normalized_url], score)
            else:
                directory_urls[normalized_url] = score

            logger.debug(f"Found directory page (score {score}, pattern: {matched_pattern}): {normalized_url}")

    # Sort by score (highest first) and return URLs
    sorted_urls = sorted(directory_urls.items(), key=lambda x: x[1], reverse=True)
    result = [url for url, score in sorted_urls]

    logger.info(f"Found {len(result)} directory pages (scores: {[s for _, s in sorted_urls[:5]]}...)")

    return result


# =============================================================================
# Email Pattern Detection
# =============================================================================

def detect_email_pattern(emails: List[str], domain: str) -> Optional[str]:
    """
    Detect email pattern from a list of emails.

    Common patterns:
    - firstname.lastname@domain.com
    - firstinitial.lastname@domain.com
    - firstname_lastname@domain.com
    - flastname@domain.com

    Args:
        emails: List of email addresses from same domain
        domain: Domain to analyze

    Returns:
        Pattern string (e.g., 'firstname.lastname') or None
    """
    if len(emails) < 3:
        # Need at least 3 examples to detect reliable pattern
        return None

    patterns = []

    for email in emails:
        local_part = email.split('@')[0].lower()

        # Detect separators
        if '.' in local_part:
            patterns.append('.')
        elif '_' in local_part:
            patterns.append('_')
        else:
            patterns.append('none')

    # Find most common pattern
    pattern_counts = Counter(patterns)
    most_common = pattern_counts.most_common(1)[0]

    # Need at least 60% consistency
    if most_common[1] / len(patterns) >= 0.6:
        return most_common[0]

    return None


def construct_email(
    first_name: str,
    last_name: str,
    domain: str,
    pattern: str = '.'
) -> str:
    """
    Construct email address using detected pattern.

    Args:
        first_name: First name
        last_name: Last name
        domain: Email domain
        pattern: Separator pattern ('.' or '_' or 'none')

    Returns:
        Constructed email address
    """
    first = first_name.lower().strip()
    last = last_name.lower().strip()

    if not first or not last:
        return ''

    if pattern == '.':
        local = f"{first}.{last}"
    elif pattern == '_':
        local = f"{first}_{last}"
    elif pattern == 'none':
        local = f"{first}{last}"
    else:
        # Default to dot
        local = f"{first}.{last}"

    email = f"{local}@{domain}"
    return email


# =============================================================================
# Contact Extraction from HTML
# =============================================================================

def extract_contacts_from_page(
    url: str,
    soup: BeautifulSoup,
    target_roles: List[str],
    institution_name: str,
    institution_url: str,
    state: str,
    program_type: str
) -> List[Dict]:
    """
    Extract contacts from a directory/staff page.

    Args:
        url: URL of the page being scraped
        soup: BeautifulSoup object of the page
        target_roles: List of roles to match against
        institution_name: Name of institution
        institution_url: Base URL of institution
        state: State abbreviation
        program_type: 'Law School' or 'Paralegal Program'

    Returns:
        List of contact dictionaries
    """
    contacts = []

    logger.info(f"Extracting contacts from {url}")

    # Strategy 1: Look for common HTML structures
    # - Individual profile cards/sections
    # - Table rows
    # - List items

    # Try finding profile cards/sections
    potential_sections = []

    # Look for divs/sections with class names suggesting profiles
    for tag in soup.find_all(['div', 'section', 'article', 'li']):
        classes = ' '.join(tag.get('class', [])).lower()

        # Multi-Tier Phase 5.4: Expanded CSS class keywords for broader site support
        if any(keyword in classes for keyword in [
            'profile', 'person', 'staff', 'faculty', 'contact',
            'member', 'bio', 'card', 'directory',
            'employee', 'team', 'user', 'individual', 'personnel',  # NEW: broader patterns
            'listing', 'item', 'entry', 'record'  # NEW: CMS-common classes
        ]):
            potential_sections.append(tag)

    # If no structured profiles found, try table rows
    if not potential_sections:
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            potential_sections.extend(rows)

    # Multi-Tier Phase 5.4: Semantic markup fallback for schema.org-compliant sites
    if not potential_sections:
        # Search for elements with itemprop="name" or itemprop="email" (structured person data)
        semantic_elements = soup.find_all(attrs={'itemprop': re.compile(r'(name|email|jobTitle)', re.I)})
        if semantic_elements:
            # Group semantic elements by parent container
            parents = set()
            for elem in semantic_elements:
                parent = elem.find_parent(['div', 'section', 'article', 'li', 'tr'])
                if parent and parent not in parents:
                    potential_sections.append(parent)
                    parents.add(parent)
            if potential_sections:
                logger.debug(f"Found {len(potential_sections)} sections via semantic markup fallback")

    # Parse each potential contact section
    for section in potential_sections:
        contact = extract_contact_from_section(
            section,
            target_roles,
            institution_name,
            institution_url,
            state,
            program_type
        )

        if contact:
            contacts.append(contact)

    # Remove duplicates based on email or name
    contacts = deduplicate_contacts(contacts)

    logger.info(f"Extracted {len(contacts)} contacts from {url}")

    return contacts


def extract_contact_from_section(
    section: BeautifulSoup,
    target_roles: List[str],
    institution_name: str,
    institution_url: str,
    state: str,
    program_type: str
) -> Optional[Dict]:
    """
    Extract a single contact from an HTML section.

    Args:
        section: BeautifulSoup element containing contact info
        target_roles: List of roles to match against
        institution_name: Name of institution
        institution_url: Base URL of institution
        state: State abbreviation
        program_type: 'Law School' or 'Paralegal Program'

    Returns:
        Contact dictionary or None if no relevant contact found
    """
    # Extract all text from section
    text = section.get_text(separator=' ')

    # Try to find name
    name = None
    title = None
    email = None
    phone = None

    # Strategy 1: Look for semantic HTML (schema.org) attributes
    name_tag = section.find(attrs={'itemprop': 'name'})
    if name_tag:
        name = clean_text(name_tag.get_text())

    # Look for job title with semantic markup
    title_tags = section.find_all(attrs={'itemprop': 'jobTitle'})
    if title_tags:
        # Collect all titles (people may have multiple)
        titles = [clean_text(t.get_text()) for t in title_tags]
        title = ' | '.join(titles) if titles else None

    # Strategy 2: Look for name in common heading tags or class names
    name_element = None  # Track which element was used for name
    if not name:
        for tag in section.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'b', 'span', 'div']):
            classes = ' '.join(tag.get('class', [])).lower()
            tag_text = clean_text(tag.get_text())

            if any(keyword in classes for keyword in ['name', 'title', 'heading']):
                if not name and len(tag_text) > 3 and len(tag_text.split()) >= 2:
                    # Likely a name
                    name = tag_text
                    name_element = tag  # Remember this element

            # BUG FIX: Don't extract title from same element as name
            # Also require more specific job-related class names (not just "title")
            if (not title and tag != name_element and
                any(keyword in classes for keyword in ['position', 'role', 'job', 'jobtitle'])):
                if tag_text and len(tag_text) > 5:
                    title = tag_text

    # If no structured name found, try heuristics
    if not name:
        # Look for capitalized words that might be names
        lines = text.split('\n')
        for line in lines[:5]:  # Check first few lines
            line = clean_text(line)
            if line and len(line.split()) >= 2 and len(line) < 50:
                # Check if it looks like a name (capitalized words)
                if line[0].isupper() and ' ' in line:
                    words = line.split()
                    if all(w[0].isupper() for w in words if w):
                        name = line
                        break

    # Extract email (try semantic markup first)
    email_tag = section.find('a', attrs={'itemprop': 'email'})
    if not email_tag:
        email_tag = section.find('a', href=re.compile(r'mailto:', re.I))

    if email_tag:
        href = email_tag.get('href', '').strip()
        # Multi-Tier Phase 5.2: Only extract from mailto: links, validate format
        if href.startswith('mailto:'):
            email = href.replace('mailto:', '').strip()
            # Validate email format before accepting
            if email and not re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$', email):
                logger.debug(f"Invalid email format from mailto: {email[:50]}")
                email = None  # Discard invalid email
        else:
            # href is not mailto:, try to extract email from anchor text instead
            email = extract_email(email_tag.get_text())
    else:
        # Try extracting from text
        email = extract_email(text)

    # Multi-Tier Phase 2: If still no email, try de-obfuscation
    if not email:
        section_html = str(section)
        deobfuscated_emails = email_deobfuscator.deobfuscate_all(section_html)
        if deobfuscated_emails:
            email = list(deobfuscated_emails)[0]  # Use first de-obfuscated email
            logger.debug(f"De-obfuscated email: {email}")

    # Extract phone (try semantic markup first)
    phone_tag = section.find('a', attrs={'itemprop': 'telephone'})
    if not phone_tag:
        phone_tag = section.find('a', href=re.compile(r'tel:', re.I))

    if phone_tag:
        phone_text = phone_tag.get('href', '').replace('tel:', '').strip()
        if not phone_text:
            phone_text = clean_text(phone_tag.get_text())
        phone = phone_text
    else:
        phone = extract_phone(text)

    # Look for title if not found
    if not title:
        # BUG FIX: Define title keywords at the top (not inside loop)
        title_keywords = ['director', 'dean', 'professor', 'librarian', 'coordinator',
                        'chair', 'head', 'assistant', 'associate', 'chief', 'manager',
                        'registrar', 'administrator', 'counsel', 'officer']

        # BUG FIX: First try to find title in <li> or <p> elements (common pattern)
        # Look for list items or paragraphs containing job title keywords
        for tag in section.find_all(['li', 'p', 'div']):
            tag_text = clean_text(tag.get_text())
            tag_text_lower = tag_text.lower()

            # Skip if this looks like a name or email
            if '@' in tag_text or tag_text == name:
                continue

            # Check if contains job title keywords
            if any(keyword in tag_text_lower for keyword in title_keywords):
                if 5 < len(tag_text) < 150:  # Reasonable title length
                    title = tag_text
                    break

        # Fallback: Search text for title keywords (original logic)
        if not title:
            for line in text.split('\n'):
                line_clean = clean_text(line).lower()
                if any(keyword in line_clean for keyword in title_keywords):
                    if len(line_clean) > 5 and len(line_clean) < 100:
                        title = clean_text(line)
                        break

    # Multi-Tier Phase 5.4: More lenient validation - allow name OR email (title optional)
    # Many faculty pages don't have easily parsable titles
    if not name and not email:
        # Need at least a name or email to be useful
        logger.debug(f"Skipping: no name or email found (title: {title[:50] if title else 'None'})")
        return None

    # If we have title but no name, try to extract name from nearby text
    if not name and title:
        # Some pages only list title, try harder to find associated name
        pass  # Will use title as fallback in final contact dict

    # Match title to target roles (with intelligent normalization)
    matched_role = None
    title_confidence = 0
    title_match_score = 0
    all_matches = None
    normalized_title_obj = None

    if title:
        matched_role, title_confidence, title_match_score, all_matches, normalized_title_obj = match_title_to_role(
            title,
            target_roles,
            return_all_matches=True  # Capture all matching roles for quality data
        )

    # DISABLED: Don't strictly filter by title - many valid roles won't match target list
    # Instead, use title matching for confidence scoring only
    # if title and not matched_role:
    #     logger.debug(f"Skipping contact: title '{title}' doesn't match target roles")
    #     return None

    # Calculate confidence score
    confidence = calculate_contact_confidence(
        has_email=bool(email),
        email_on_site=bool(email),
        email_validated=False,  # Will validate later
        email_is_catchall=False,  # Will check later
        title_match_score=title_match_score,
        has_phone=bool(phone),
        linkedin_verified=False
    )

    # Skip low confidence contacts unless they have a very strong title match
    # Allow contacts without email if they have excellent title match (90+)
    if confidence < MIN_CONFIDENCE_SCORE and not email and title_match_score < 90:
        logger.debug(f"Skipping low confidence contact: {name} (score: {confidence})")
        return None

    # Parse name
    name_parts = parse_name(name) if name else {'first_name': '', 'last_name': ''}

    # Extract title metadata from normalization (if available)
    title_normalized = normalized_title_obj.normalized if normalized_title_obj else title
    title_modifiers = ','.join(normalized_title_obj.modifiers) if normalized_title_obj and normalized_title_obj.modifiers else ''
    is_temporary = normalized_title_obj.is_temporary if normalized_title_obj else False
    is_shared_role = normalized_title_obj.is_shared_role if normalized_title_obj else False

    # Format all matched roles (for data quality analysis)
    all_matched_roles_str = ''
    if all_matches and len(all_matches) > 1:
        # Only include secondary matches (exclude the primary match)
        secondary_matches = [role for role, score in all_matches[1:]]
        if secondary_matches:
            all_matched_roles_str = ','.join(secondary_matches)

    # Build contact record (with intelligent title matching metadata)
    contact = {
        'institution_name': institution_name,
        'institution_url': institution_url,
        'state': state,
        'program_type': program_type,
        'first_name': name_parts['first_name'],
        'last_name': name_parts['last_name'],
        'full_name': name or '',
        'title': title or '',
        'title_normalized': title_normalized or '',
        'title_modifiers': title_modifiers,
        'is_temporary': is_temporary,
        'is_shared_role': is_shared_role,
        'matched_role': matched_role or '',
        'all_matched_roles': all_matched_roles_str,
        'email': email or '',
        'phone': phone or '',
        'confidence_score': confidence,
        'title_match_score': title_match_score,
        'extraction_method': 'website_scrape',
        'source_url': institution_url,
        'extracted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    return contact


def deduplicate_contacts(contacts: List[Dict]) -> List[Dict]:
    """
    Remove duplicate contacts from list.

    Deduplication based on:
    1. Same email address
    2. Same name + title

    Args:
        contacts: List of contact dictionaries

    Returns:
        Deduplicated list
    """
    seen = set()
    unique_contacts = []

    for contact in contacts:
        # Create unique key
        email_key = contact.get('email', '').lower().strip()
        name_key = f"{contact.get('full_name', '')}_{contact.get('title', '')}".lower()

        key = email_key if email_key else name_key

        if key and key not in seen:
            seen.add(key)
            unique_contacts.append(contact)

    return unique_contacts


def scrape_with_link_following(
    dir_url: str,
    dir_soup: BeautifulSoup,
    target_roles: List[str],
    institution_name: str,
    institution_url: str,
    state: str,
    program_type: str,
    max_profile_pages: int = 20
) -> List[Dict]:
    """
    Multi-tier extraction with intelligent link following.

    Strategy:
    1. Classify directory page type
    2. Extract contacts directly from directory page
    3. If it's a directory listing, extract profile links
    4. Follow top-scored profile links (up to max_profile_pages)
    5. Extract contacts from individual profile pages
    6. Combine and return all contacts

    Args:
        dir_url: URL of directory page
        dir_soup: Parsed HTML of directory page
        target_roles: List of target role titles
        institution_name: Institution name
        institution_url: Institution homepage URL
        state: State abbreviation
        program_type: Program type
        max_profile_pages: Max individual profiles to scrape per directory

    Returns:
        List of contact dictionaries
    """
    all_contacts = []

    # Step 1: Classify page type
    html_str = str(dir_soup)
    h1 = dir_soup.find('h1')
    heading = h1.get_text() if h1 else ''

    page_type, confidence = page_classifier.classify_page(dir_url, html_str, heading)

    logger.debug(f"Page classified as: {page_type} (confidence: {confidence})")

    # Step 2: Check if we should exclude this page
    if page_classifier.should_exclude(dir_url, html_str):
        logger.warning(f"Excluding page (type: {page_type}): {dir_url[:80]}")
        return []

    # Step 3: Extract contacts directly from this page
    direct_contacts = extract_contacts_from_page(
        dir_url,
        dir_soup,
        target_roles,
        institution_name,
        institution_url,
        state,
        program_type
    )
    all_contacts.extend(direct_contacts)

    logger.info(f"Direct extraction: {len(direct_contacts)} contacts from {dir_url[:60]}")

    # Step 4: If this is a directory listing, follow profile links
    if page_classifier.is_directory_listing(dir_url, html_str):
        logger.info(f"Directory listing detected, extracting profile links...")

        # Extract profile links
        profile_links = link_extractor.extract_profile_links(dir_url, html_str)

        if profile_links:
            logger.info(f"Found {len(profile_links)} profile links, visiting top {min(len(profile_links), max_profile_pages)}")

            # Visit top-scored profile pages
            for i, profile_link in enumerate(profile_links[:max_profile_pages], 1):
                try:
                    logger.debug(f"  [{i}/{len(profile_links[:max_profile_pages])}] Visiting: {profile_link.url[:70]} (score: {profile_link.score})")

                    # Rate limiting
                    time.sleep(RATE_LIMIT_DELAY)

                    # Fetch profile page
                    profile_soup = fetch_page_smart(profile_link.url)

                    if not profile_soup:
                        logger.debug(f"    Failed to fetch profile page")
                        continue

                    # Extract contacts from profile page
                    profile_contacts = extract_contacts_from_page(
                        profile_link.url,
                        profile_soup,
                        target_roles,
                        institution_name,
                        institution_url,
                        state,
                        program_type
                    )

                    if profile_contacts:
                        logger.debug(f"    Extracted {len(profile_contacts)} contact(s)")
                        all_contacts.extend(profile_contacts)

                except Exception as e:
                    logger.debug(f"    Error scraping profile {profile_link.url[:60]}: {e}")
                    continue

            logger.success(f"Link following: {len(all_contacts) - len(direct_contacts)} additional contacts from {i} profile pages")
        else:
            logger.debug("No profile links found on directory listing")

    return all_contacts


# =============================================================================
# Async Multi-Tier Extraction (Performance Optimization - Phase 6.1)
# =============================================================================

async def scrape_with_link_following_async(
    dir_url: str,
    dir_soup: BeautifulSoup,
    target_roles: List[str],
    institution_name: str,
    institution_url: str,
    state: str,
    program_type: str,
    max_profile_pages: int = 20,
    concurrency: int = 3,
    browser_pool=None
) -> List[Dict]:
    """
    Multi-tier extraction with parallel profile link visiting (ASYNC).

    Performance Optimization - Phase 6.1:
    - Visits profile links in parallel using asyncio.Semaphore
    - Uses per-domain rate limiting instead of global 5s delay
    - Expected savings: 10 minutes per institution (50% time reduction)

    Strategy:
    1. Classify directory page type
    2. Extract contacts directly from directory page
    3. If it's a directory listing, extract profile links
    4. Follow top-scored profile links IN PARALLEL (up to max_profile_pages)
    5. Extract contacts from individual profile pages
    6. Combine and return all contacts

    Args:
        dir_url: URL of directory page
        dir_soup: Parsed HTML of directory page
        target_roles: List of target role titles
        institution_name: Institution name
        institution_url: Institution homepage URL
        state: State abbreviation
        program_type: Program type
        max_profile_pages: Max individual profiles to scrape per directory
        concurrency: Number of concurrent profile fetches (default: 3)

    Returns:
        List of contact dictionaries
    """
    all_contacts = []

    # Step 1: Classify page type
    html_str = str(dir_soup)
    h1 = dir_soup.find('h1')
    heading = h1.get_text() if h1 else ''

    page_type, confidence = page_classifier.classify_page(dir_url, html_str, heading)

    logger.debug(f"Page classified as: {page_type} (confidence: {confidence})")

    # Step 2: Check if we should exclude this page
    if page_classifier.should_exclude(dir_url, html_str):
        logger.warning(f"Excluding page (type: {page_type}): {dir_url[:80]}")
        return []

    # Step 3: Extract contacts directly from this page
    direct_contacts = extract_contacts_from_page(
        dir_url,
        dir_soup,
        target_roles,
        institution_name,
        institution_url,
        state,
        program_type
    )
    all_contacts.extend(direct_contacts)

    logger.info(f"Direct extraction: {len(direct_contacts)} contacts from {dir_url[:60]}")

    # Step 4: If this is a directory listing, follow profile links IN PARALLEL
    if page_classifier.is_directory_listing(dir_url, html_str):
        logger.info(f"Directory listing detected, extracting profile links...")

        # Extract profile links
        profile_links = link_extractor.extract_profile_links(dir_url, html_str)

        if profile_links:
            logger.info(f"Found {len(profile_links)} profile links, visiting top {min(len(profile_links), max_profile_pages)} in parallel ({concurrency} workers)")

            # Semaphore to limit concurrent fetches
            semaphore = asyncio.Semaphore(concurrency)

            # Get domain rate limiter
            rate_limiter = get_domain_rate_limiter()

            async def fetch_profile(i: int, profile_link) -> List[Dict]:
                """Fetch a single profile page with rate limiting."""
                async with semaphore:
                    try:
                        logger.debug(f"  [{i+1}/{len(profile_links[:max_profile_pages])}] Visiting: {profile_link.url[:70]} (score: {profile_link.score})")

                        # Per-domain rate limiting (async)
                        await rate_limiter.wait_if_needed_async(profile_link.url)

                        # Fetch profile page (async with browser pool)
                        profile_soup = await fetch_page_smart_async(profile_link.url, browser_pool=browser_pool)

                        if not profile_soup:
                            logger.debug(f"    Failed to fetch profile page")
                            return []

                        # Extract contacts from profile page (sync function)
                        profile_contacts = extract_contacts_from_page(
                            profile_link.url,
                            profile_soup,
                            target_roles,
                            institution_name,
                            institution_url,
                            state,
                            program_type
                        )

                        if profile_contacts:
                            logger.debug(f"    Extracted {len(profile_contacts)} contact(s)")
                            return profile_contacts

                        return []

                    except Exception as e:
                        logger.debug(f"    Error scraping profile {profile_link.url[:60]}: {e}")
                        return []

            # Visit profile pages in parallel
            tasks = [fetch_profile(i, link) for i, link in enumerate(profile_links[:max_profile_pages])]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Flatten results
            for result in results:
                if isinstance(result, list):
                    all_contacts.extend(result)
                elif isinstance(result, Exception):
                    logger.debug(f"Profile fetch raised exception: {result}")

            new_contacts = len(all_contacts) - len(direct_contacts)
            logger.success(f"Link following (parallel): {new_contacts} additional contacts from {len(profile_links[:max_profile_pages])} profile pages")
        else:
            logger.debug("No profile links found on directory listing")

    return all_contacts


async def scrape_directories_async(
    directory_urls: List[str],
    target_roles: List[str],
    institution_name: str,
    institution_url: str,
    state: str,
    program_type: str,
    max_directories: int = 5,
    concurrency: int = 3,
    browser_pool=None
) -> List[Dict]:
    """
    Process multiple directory pages in parallel (ASYNC).

    Performance Optimization - Phase 6.2:
    - Fetches and processes multiple directory pages concurrently
    - Uses per-domain rate limiting instead of global delays
    - Expected savings: 2.5 minutes per institution (directory pages)

    Args:
        directory_urls: List of directory page URLs to process
        target_roles: Target role titles to match
        institution_name: Institution name
        institution_url: Institution URL
        state: State abbreviation
        program_type: 'Law School' or 'Paralegal Program'
        max_directories: Maximum number of directories to process
        concurrency: Number of concurrent directory fetches

    Returns:
        Combined list of all contacts from all directories
    """
    from modules.domain_rate_limiter import get_domain_rate_limiter

    # Limit directory URLs
    directory_urls = directory_urls[:max_directories]

    if not directory_urls:
        return []

    logger.info(f"Processing {len(directory_urls)} directory pages in parallel ({concurrency} workers)")

    # Semaphore to limit concurrent directory fetches
    semaphore = asyncio.Semaphore(concurrency)
    rate_limiter = get_domain_rate_limiter()

    async def process_directory(i: int, dir_url: str) -> List[Dict]:
        """Fetch and process a single directory page with rate limiting."""
        async with semaphore:
            try:
                logger.debug(f"Directory {i+1}/{len(directory_urls)}: {dir_url[:60]}")

                # Per-domain rate limiting (async)
                await rate_limiter.wait_if_needed_async(dir_url)

                # Fetch directory page (async with browser pool)
                dir_soup = await fetch_page_smart_async(dir_url, browser_pool=browser_pool)

                if not dir_soup:
                    logger.error(f"Failed to fetch {dir_url[:60]}")
                    return []

                # Use multi-tier extraction with async profile link visiting
                if ENABLE_ASYNC_PROFILE_LINKS:
                    contacts = await scrape_with_link_following_async(
                        dir_url,
                        dir_soup,
                        target_roles,
                        institution_name,
                        institution_url,
                        state,
                        program_type,
                        max_profile_pages=20,
                        concurrency=PROFILE_LINK_CONCURRENCY,
                        browser_pool=browser_pool
                    )
                else:
                    # Fallback to sync version (run in executor)
                    contacts = await loop.run_in_executor(
                        None,
                        scrape_with_link_following,
                        dir_url,
                        dir_soup,
                        target_roles,
                        institution_name,
                        institution_url,
                        state,
                        program_type,
                        20  # max_profile_pages
                    )

                logger.info(f"Extracted {len(contacts)} contacts from {dir_url[:60]}")
                return contacts

            except Exception as e:
                logger.error(f"Failed to scrape directory {dir_url[:60]}: {e}")
                return []

    # Process all directories in parallel
    tasks = [process_directory(i, url) for i, url in enumerate(directory_urls)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten results
    all_contacts = []
    for result in results:
        if isinstance(result, list):
            all_contacts.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"Directory processing raised exception: {result}")

    logger.success(f"Parallel directory processing: {len(all_contacts)} total contacts from {len(directory_urls)} pages")

    return all_contacts


# =============================================================================
# Main Extraction Function
# =============================================================================

@rate_limit(calls=1, period=RATE_LIMIT_DELAY)
def scrape_institution_contacts(
    institution_name: str,
    institution_url: str,
    state: str,
    program_type: str
) -> pd.DataFrame:
    """
    Scrape contacts from a single institution.

    Args:
        institution_name: Name of institution
        institution_url: Institution's website URL
        state: State abbreviation
        program_type: 'Law School' or 'Paralegal Program'

    Returns:
        DataFrame of contacts found
    """
    logger.info("=" * 70)
    logger.info(f"Scraping: {institution_name}")
    logger.info(f"URL: {institution_url}")
    logger.info("=" * 70)

    all_contacts = []

    # Determine which roles to target
    if program_type == 'Law School':
        target_roles = LAW_SCHOOL_ROLES
        prog_type_short = 'law'
    else:
        target_roles = PARALEGAL_PROGRAM_ROLES
        prog_type_short = 'paralegal'

    try:
        # Fetch homepage using smart fetching (static first, Playwright fallback)
        soup = fetch_page_smart(institution_url)

        if not soup:
            logger.error(f"Failed to fetch homepage for {institution_name}")
            return pd.DataFrame()

        # Find directory pages
        directory_urls = find_directory_pages(institution_url, soup, prog_type_short)

        if not directory_urls:
            logger.warning(f"No directory pages found, trying homepage")
            directory_urls = [institution_url]

        logger.info(f"Found {len(directory_urls)} pages to scrape")

        # Performance Optimization - Phase 6.2: Process directories in parallel if enabled
        if ENABLE_ASYNC_DIRECTORIES:
            logger.debug(f"Using async directory processing ({DIRECTORY_CONCURRENCY} workers)")
            all_contacts = asyncio.run(scrape_directories_async(
                directory_urls,
                target_roles,
                institution_name,
                institution_url,
                state,
                program_type,
                max_directories=5,
                concurrency=DIRECTORY_CONCURRENCY
            ))
        else:
            # Serial processing (original code)
            for dir_url in directory_urls[:5]:  # Limit to first 5 pages
                time.sleep(RATE_LIMIT_DELAY)

                try:
                    # Use smart fetching for directory pages
                    dir_soup = fetch_page_smart(dir_url)

                    if not dir_soup:
                        logger.error(f"Failed to fetch {dir_url}")
                        continue

                    # Use multi-tier extraction with link following
                    # Performance Optimization - Phase 6.1: Use async version if enabled
                    if ENABLE_ASYNC_PROFILE_LINKS:
                        logger.debug(f"Using async profile link visiting ({PROFILE_LINK_CONCURRENCY} workers)")
                        contacts = asyncio.run(scrape_with_link_following_async(
                            dir_url,
                            dir_soup,
                            target_roles,
                            institution_name,
                            institution_url,
                            state,
                            program_type,
                            max_profile_pages=20,  # Visit up to 20 individual profiles per directory
                            concurrency=PROFILE_LINK_CONCURRENCY
                        ))
                    else:
                        contacts = scrape_with_link_following(
                            dir_url,
                            dir_soup,
                            target_roles,
                            institution_name,
                            institution_url,
                            state,
                            program_type,
                            max_profile_pages=20  # Visit up to 20 individual profiles per directory
                        )

                    all_contacts.extend(contacts)
                    logger.info(f"Extracted {len(contacts)} contacts from {dir_url[:60]}")

                except Exception as e:
                    logger.error(f"Failed to scrape {dir_url}: {e}")
                    continue

        # Deduplicate across all pages
        all_contacts = deduplicate_contacts(all_contacts)

        logger.success(f"Found {len(all_contacts)} contacts at {institution_name}")

    except Exception as e:
        logger.error(f"Failed to scrape {institution_name}: {e}")

    # Convert to DataFrame
    if all_contacts:
        df = pd.DataFrame(all_contacts)
    else:
        # Return empty DataFrame with proper columns
        df = pd.DataFrame(columns=[
            'institution_name', 'institution_url', 'state', 'program_type',
            'first_name', 'last_name', 'full_name', 'title', 'matched_role',
            'email', 'phone', 'confidence_score', 'title_match_score',
            'extraction_method', 'source_url', 'extracted_at'
        ])

    logger.info("=" * 70)

    return df


async def scrape_institution_contacts_async(
    institution_name: str,
    institution_url: str,
    state: str,
    program_type: str,
    browser_pool=None
) -> pd.DataFrame:
    """
    Async version of scrape_institution_contacts with browser pooling (Sprint 2.2).

    Uses native async/await throughout - no thread pool executors.
    Integrates with browser pool for efficient Playwright usage.

    Args:
        institution_name: Name of institution
        institution_url: Institution's website URL
        state: State abbreviation
        program_type: 'Law School' or 'Paralegal Program'
        browser_pool: Optional browser pool instance

    Returns:
        DataFrame of contacts found
    """
    logger.info("=" * 70)
    logger.info(f"[ASYNC] Scraping: {institution_name}")
    logger.info(f"URL: {institution_url}")
    logger.info("=" * 70)

    all_contacts = []

    # Determine which roles to target
    if program_type == 'Law School':
        target_roles = LAW_SCHOOL_ROLES
        prog_type_short = 'law'
    else:
        target_roles = PARALEGAL_PROGRAM_ROLES
        prog_type_short = 'paralegal'

    try:
        # Fetch homepage using async smart fetching
        logger.info(f"Fetching homepage for {institution_name}...")
        soup = await fetch_page_smart_async(institution_url, browser_pool=browser_pool)

        if not soup:
            logger.error(f"Failed to fetch homepage for {institution_name}")
            return pd.DataFrame()

        # Find directory pages (sync parsing, but fast)
        logger.info(f"Finding directory pages for {institution_name}...")
        directory_urls = find_directory_pages(institution_url, soup, prog_type_short)

        if not directory_urls:
            logger.warning(f"No directory pages found for {institution_name}, trying homepage")
            directory_urls = [institution_url]

        logger.info(f"Found {len(directory_urls)} directory pages for {institution_name}")

        # Scrape directories asynchronously with browser pool
        all_contacts = await scrape_directories_async(
            directory_urls,
            target_roles,
            institution_name,
            institution_url,
            state,
            program_type,
            max_directories=5,
            concurrency=DIRECTORY_CONCURRENCY,
            browser_pool=browser_pool  # Pass pool through
        )

        if not all_contacts:
            logger.warning(f"No contacts extracted from {institution_name}")
            return pd.DataFrame()

        # Deduplicate across all pages
        all_contacts = deduplicate_contacts(all_contacts)

        logger.success(f"Found {len(all_contacts)} contacts at {institution_name}")

    except Exception as e:
        logger.error(f"Error scraping {institution_name}: {e}", exc_info=True)

    # Convert to DataFrame
    if all_contacts:
        df = pd.DataFrame(all_contacts)
    else:
        # Return empty DataFrame with proper columns
        df = pd.DataFrame(columns=[
            'institution_name', 'institution_url', 'state', 'program_type',
            'first_name', 'last_name', 'full_name', 'title', 'matched_role',
            'email', 'phone', 'confidence_score', 'title_match_score',
            'extraction_method', 'source_url', 'extracted_at'
        ])

    logger.info("=" * 70)

    return df


# =============================================================================
# Batch Processing
# =============================================================================

def scrape_multiple_institutions(
    institutions_df: pd.DataFrame,
    max_institutions: Optional[int] = None
) -> pd.DataFrame:
    """
    Scrape contacts from multiple institutions.

    Args:
        institutions_df: DataFrame with institution info (from target_discovery)
        max_institutions: Maximum number of institutions to scrape (None = all)

    Returns:
        Combined DataFrame of all contacts
    """
    logger.info("=" * 70)
    logger.info(f"Starting batch scraping of {len(institutions_df)} institutions")
    logger.info("=" * 70)

    all_contacts = []

    # Limit number of institutions if specified
    if max_institutions:
        institutions_df = institutions_df.head(max_institutions)
        logger.info(f"Limited to {max_institutions} institutions for testing")

    for idx, row in institutions_df.iterrows():
        contacts_df = scrape_institution_contacts(
            institution_name=row['name'],
            institution_url=row['url'],
            state=row['state'],
            program_type=row['type']
        )

        if not contacts_df.empty:
            all_contacts.append(contacts_df)

    # Combine all results
    if all_contacts:
        combined_df = pd.concat(all_contacts, ignore_index=True)
        logger.success(f"Total contacts extracted: {len(combined_df)}")
    else:
        logger.warning("No contacts extracted from any institution")
        combined_df = pd.DataFrame()

    return combined_df


# =============================================================================
# Async / Parallel Scraping (Sprint 2.1)
# =============================================================================

async def scrape_institution_async(
    institution_name: str,
    institution_url: str,
    state: str,
    program_type: str,
    semaphore: asyncio.Semaphore,
    institution_num: int,
    total_institutions: int,
    browser_pool=None
) -> pd.DataFrame:
    """
    Async wrapper for scraping a single institution with feature flag routing (Sprint 2.2).

    Routes between two paths based on USE_BROWSER_POOL feature flag:
    - True: Native async with browser pool (new path)
    - False: Thread pool executor (legacy path, backward compatible)

    Args:
        institution_name: Name of institution
        institution_url: URL to scrape
        state: State abbreviation
        program_type: Type of program
        semaphore: Asyncio semaphore for concurrency control
        institution_num: Current institution number (for logging)
        total_institutions: Total number of institutions (for logging)
        browser_pool: Optional browser pool instance (used when USE_BROWSER_POOL=True)

    Returns:
        DataFrame of contacts
    """
    from config.settings import USE_BROWSER_POOL

    async with semaphore:
        logger.info(f"[{institution_num}/{total_institutions}] Starting: {institution_name}")

        start_time = time.time()

        try:
            if USE_BROWSER_POOL:
                # NEW: Native async path with browser pool
                logger.debug(f"Using browser pool for {institution_name}")
                contacts_df = await scrape_institution_contacts_async(
                    institution_name,
                    institution_url,
                    state,
                    program_type,
                    browser_pool=browser_pool
                )
            else:
                # OLD: Thread pool executor (backward compatible)
                logger.debug(f"Using thread pool executor for {institution_name}")
                loop = asyncio.get_event_loop()
                contacts_df = await loop.run_in_executor(
                    None,  # Use default executor
                    scrape_institution_contacts,
                    institution_name,
                    institution_url,
                    state,
                    program_type
                )

            elapsed = time.time() - start_time

            if not contacts_df.empty:
                logger.success(f"[{institution_num}/{total_institutions}] Completed: {institution_name} ({len(contacts_df)} contacts, {elapsed:.1f}s)")
            else:
                logger.warning(f"[{institution_num}/{total_institutions}] Completed: {institution_name} (0 contacts, {elapsed:.1f}s)")

            return contacts_df

        except Exception as e:
            logger.error(f"[{institution_num}/{total_institutions}] Failed: {institution_name}: {e}")
            return pd.DataFrame()


async def scrape_multiple_institutions_async(
    institutions_df: pd.DataFrame,
    max_institutions: Optional[int] = None,
    max_parallel: int = 6,
    streaming_writer: Optional['StreamingContactWriter'] = None
) -> pd.DataFrame:
    """
    Scrape contacts from multiple institutions in parallel using asyncio.

    Args:
        institutions_df: DataFrame with institution info (from target_discovery)
        max_institutions: Maximum number of institutions to scrape (None = all)
        max_parallel: Maximum number of parallel workers (default: 6)
        streaming_writer: Optional writer for progressive saves (enables resume capability)

    Returns:
        Combined DataFrame of all contacts
    """
    # Resume logic: skip already-completed institutions
    original_count = len(institutions_df)
    if streaming_writer and streaming_writer.institutions_completed:
        completed_names = streaming_writer.institutions_completed
        institutions_df = institutions_df[~institutions_df['name'].isin(completed_names)].copy()
        skipped = original_count - len(institutions_df)
        if skipped > 0:
            logger.warning("=" * 70)
            logger.warning(f"RESUMING: Skipping {skipped} already-completed institutions")
            logger.warning(f"Completed institutions loaded from: {streaming_writer.resume_file}")
            logger.warning("=" * 70)

    logger.info("=" * 70)
    logger.info(f"Starting ASYNC batch scraping of {len(institutions_df)} institutions")
    logger.info(f"Max parallel workers: {max_parallel}")
    if streaming_writer:
        logger.info(f"Progressive saves: ENABLED ({streaming_writer.output_file})")
    logger.info("=" * 70)

    # Limit number of institutions if specified
    if max_institutions:
        institutions_df = institutions_df.head(max_institutions)
        logger.info(f"Limited to {max_institutions} institutions for testing")

    # Initialize browser pool if USE_BROWSER_POOL is enabled
    from config.settings import USE_BROWSER_POOL
    browser_pool = None
    if USE_BROWSER_POOL:
        try:
            from modules.browser_pool import get_browser_pool, close_browser_pool
            logger.info(f"Initializing browser pool (size=3)...")
            browser_pool = await get_browser_pool(pool_size=3)
            logger.info("✓ Browser pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize browser pool: {e}")
            logger.warning("Falling back to thread pool executor mode")
            # Continue without pool (USE_BROWSER_POOL will route to executor)

    try:
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_parallel)

        # Create tasks for all institutions (check shutdown flag before creating each task)
        tasks = []
        institution_names = []  # Track names for streaming writer
        for idx, row in institutions_df.iterrows():
            # Check if shutdown was requested
            global _shutdown_requested
            if _shutdown_requested:
                logger.warning(f"Shutdown requested before creating task for {row['name']}. Stopping task creation.")
                break

            task = scrape_institution_async(
                institution_name=row['name'],
                institution_url=row['url'],
                state=row['state'],
                program_type=row['type'],
                semaphore=semaphore,
                institution_num=idx + 1,
                total_institutions=len(institutions_df),
                browser_pool=browser_pool  # Pass pool to all tasks
            )
            tasks.append(task)
            institution_names.append(row['name'])

        # Run all tasks concurrently
        logger.info(f"\nLaunching {len(tasks)} async scraping tasks...")
        start_time = time.time()

        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time
        logger.success(f"\nAll tasks completed in {elapsed:.1f} seconds")
        logger.info(f"Average: {elapsed / len(tasks):.1f}s per institution (with {max_parallel}x parallelization)")

        # Filter out exceptions and combine results
        all_contacts = []
        success_count = 0
        error_count = 0

        for i, result in enumerate(results):
            institution_name = institution_names[i] if i < len(institution_names) else f"Institution {i+1}"

            if isinstance(result, Exception):
                logger.error(f"Task {i+1} ({institution_name}) failed with error: {result}")
                error_count += 1
            elif isinstance(result, pd.DataFrame) and not result.empty:
                all_contacts.append(result)
                success_count += 1

                # Progressive save: write to streaming writer immediately
                if streaming_writer:
                    try:
                        contacts_dict = result.to_dict('records')
                        streaming_writer.write_contacts(contacts_dict, institution_name)
                        streaming_writer.mark_institution_completed(institution_name)
                        logger.debug(f"✓ Saved {len(contacts_dict)} contacts from {institution_name} to disk")
                    except Exception as e:
                        logger.error(f"Failed to write contacts from {institution_name} to streaming writer: {e}")

        logger.info(f"\nResults summary:")
        logger.info(f"  Successful: {success_count}/{len(tasks)}")
        logger.info(f"  Failed: {error_count}/{len(tasks)}")
        logger.info(f"  Empty: {len(tasks) - success_count - error_count}/{len(tasks)}")

        # Combine all results
        if all_contacts:
            combined_df = pd.concat(all_contacts, ignore_index=True)
            logger.success(f"Total contacts extracted: {len(combined_df)}")
        else:
            logger.warning("No contacts extracted from any institution")
            combined_df = pd.DataFrame()

        return combined_df

    finally:
        # Cleanup browser pool
        if browser_pool and USE_BROWSER_POOL:
            try:
                logger.info("Closing browser pool...")
                from modules.browser_pool import close_browser_pool
                await close_browser_pool()
                logger.info("✓ Browser pool closed")
            except Exception as e:
                logger.error(f"Error closing browser pool: {e}")


def run_async_scraping(
    institutions_df: pd.DataFrame,
    max_institutions: Optional[int] = None,
    max_parallel: int = 6,
    streaming_writer: Optional['StreamingContactWriter'] = None
) -> pd.DataFrame:
    """
    Synchronous wrapper for async scraping.
    Use this from non-async code (like main.py).

    Args:
        institutions_df: DataFrame with institution info
        max_institutions: Maximum number of institutions to scrape
        max_parallel: Maximum number of parallel workers
        streaming_writer: Optional writer for progressive saves

    Returns:
        Combined DataFrame of all contacts
    """
    # Set up signal handlers for graceful shutdown
    setup_signal_handlers()

    # Get or create event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Run async function
    return loop.run_until_complete(
        scrape_multiple_institutions_async(
            institutions_df,
            max_institutions,
            max_parallel,
            streaming_writer
        )
    )


# =============================================================================
# Export public API
# =============================================================================

__all__ = [
    'match_title_to_role',
    'calculate_contact_confidence',
    'find_directory_pages',
    'detect_email_pattern',
    'construct_email',
    'extract_contacts_from_page',
    'scrape_institution_contacts',
    'scrape_multiple_institutions',
    'scrape_institution_async',
    'scrape_multiple_institutions_async',
    'run_async_scraping',
]
