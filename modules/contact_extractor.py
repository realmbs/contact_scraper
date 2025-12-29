"""
Contact Extraction Module for Legal Education Contact Scraper.

Extracts contact information from law school and paralegal program websites.
Uses intelligent directory discovery, fuzzy title matching, and email pattern detection.
"""

import re
import time
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

# Initialize logger
setup_logger("contact_extractor")

# Initialize timeout manager (Sprint 3.3)
timeout_manager = get_timeout_manager(default_timeout=PLAYWRIGHT_TIMEOUT)

# Initialize domain rate limiter (Sprint 3.1)
domain_rate_limiter = get_domain_rate_limiter(default_delay=2.0)

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

    # EXCLUSION patterns - skip these URLs entirely
    exclusion_patterns = [
        r'admissions?(?!.*staff)',  # /admissions, /admission (unless /admissions-staff)
        r'scholarship',              # /faculty/scholarship
        r'workshop',                 # /faculty/workshops
        r'apply',                    # /apply, /how-to-apply
        r'contact-us',               # /contact-us forms
        r'contact\b(?!.*directory)', # /contact (unless /contact-directory)
        r'news',                     # /news
        r'events?',                  # /events
        r'calendar',                 # /calendar
        r'student.*portal',          # /student-portal
        r'alumni',                   # /alumni
        r'donate',                   # /donate
        r'giving',                   # /giving
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

        if any(keyword in classes for keyword in [
            'profile', 'person', 'staff', 'faculty', 'contact',
            'member', 'bio', 'card', 'directory'
        ]):
            potential_sections.append(tag)

    # If no structured profiles found, try table rows
    if not potential_sections:
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            potential_sections.extend(rows)

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
    if not name:
        for tag in section.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'b', 'span', 'div']):
            classes = ' '.join(tag.get('class', [])).lower()
            tag_text = clean_text(tag.get_text())

            if any(keyword in classes for keyword in ['name', 'title', 'heading']):
                if not name and len(tag_text) > 3 and len(tag_text.split()) >= 2:
                    # Likely a name
                    name = tag_text

            if not title and any(keyword in classes for keyword in ['title', 'position', 'role', 'job']):
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
        email = email_tag.get('href', '').replace('mailto:', '').strip()
        if not email:
            email = clean_text(email_tag.get_text())
    else:
        # Try extracting from text
        email = extract_email(text)

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
        # Search text for common title keywords
        title_keywords = ['director', 'dean', 'professor', 'librarian', 'coordinator', 'chair', 'head']
        for line in text.split('\n'):
            line_clean = clean_text(line).lower()
            if any(keyword in line_clean for keyword in title_keywords):
                if len(line_clean) > 5 and len(line_clean) < 100:
                    title = clean_text(line)
                    break

    # Skip if no name or title found
    if not name and not title:
        return None

    # If we have title but no name, or vice versa, we can still proceed
    # but prioritize contacts with both

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

        # Scrape each directory page
        for dir_url in directory_urls[:5]:  # Limit to first 5 pages
            time.sleep(RATE_LIMIT_DELAY)

            try:
                # Use smart fetching for directory pages too
                dir_soup = fetch_page_smart(dir_url)

                if not dir_soup:
                    logger.error(f"Failed to fetch {dir_url}")
                    continue

                contacts = extract_contacts_from_page(
                    dir_url,
                    dir_soup,
                    target_roles,
                    institution_name,
                    institution_url,
                    state,
                    program_type
                )

                all_contacts.extend(contacts)

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
    total_institutions: int
) -> pd.DataFrame:
    """
    Async wrapper for scraping a single institution.

    Args:
        institution_name: Name of institution
        institution_url: URL to scrape
        state: State abbreviation
        program_type: Type of program
        semaphore: Asyncio semaphore for concurrency control
        institution_num: Current institution number (for logging)
        total_institutions: Total number of institutions (for logging)

    Returns:
        DataFrame of contacts
    """
    async with semaphore:
        logger.info(f"[{institution_num}/{total_institutions}] Starting: {institution_name}")

        # Run the synchronous scraping function in executor
        loop = asyncio.get_event_loop()
        contacts_df = await loop.run_in_executor(
            None,  # Use default executor
            scrape_institution_contacts,
            institution_name,
            institution_url,
            state,
            program_type
        )

        if not contacts_df.empty:
            logger.success(f"[{institution_num}/{total_institutions}] Completed: {institution_name} ({len(contacts_df)} contacts)")
        else:
            logger.warning(f"[{institution_num}/{total_institutions}] Completed: {institution_name} (0 contacts)")

        return contacts_df


async def scrape_multiple_institutions_async(
    institutions_df: pd.DataFrame,
    max_institutions: Optional[int] = None,
    max_parallel: int = 6
) -> pd.DataFrame:
    """
    Scrape contacts from multiple institutions in parallel using asyncio.

    Args:
        institutions_df: DataFrame with institution info (from target_discovery)
        max_institutions: Maximum number of institutions to scrape (None = all)
        max_parallel: Maximum number of parallel workers (default: 6)

    Returns:
        Combined DataFrame of all contacts
    """
    logger.info("=" * 70)
    logger.info(f"Starting ASYNC batch scraping of {len(institutions_df)} institutions")
    logger.info(f"Max parallel workers: {max_parallel}")
    logger.info("=" * 70)

    # Limit number of institutions if specified
    if max_institutions:
        institutions_df = institutions_df.head(max_institutions)
        logger.info(f"Limited to {max_institutions} institutions for testing")

    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_parallel)

    # Create tasks for all institutions
    tasks = []
    for idx, row in institutions_df.iterrows():
        task = scrape_institution_async(
            institution_name=row['name'],
            institution_url=row['url'],
            state=row['state'],
            program_type=row['type'],
            semaphore=semaphore,
            institution_num=idx + 1,
            total_institutions=len(institutions_df)
        )
        tasks.append(task)

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
        if isinstance(result, Exception):
            logger.error(f"Task {i+1} failed with error: {result}")
            error_count += 1
        elif isinstance(result, pd.DataFrame) and not result.empty:
            all_contacts.append(result)
            success_count += 1

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


def run_async_scraping(
    institutions_df: pd.DataFrame,
    max_institutions: Optional[int] = None,
    max_parallel: int = 6
) -> pd.DataFrame:
    """
    Synchronous wrapper for async scraping.
    Use this from non-async code (like main.py).

    Args:
        institutions_df: DataFrame with institution info
        max_institutions: Maximum number of institutions to scrape
        max_parallel: Maximum number of parallel workers

    Returns:
        Combined DataFrame of all contacts
    """
    # Get or create event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Run async function
    return loop.run_until_complete(
        scrape_multiple_institutions_async(institutions_df, max_institutions, max_parallel)
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
