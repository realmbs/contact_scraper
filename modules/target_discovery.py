"""
Target Discovery Module for Legal Education Contact Scraper.

Discovers law schools and paralegal programs to scrape for contacts.
"""

import re
import time
from typing import List, Optional, Dict
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from loguru import logger
from fake_useragent import UserAgent

from config.settings import (
    USE_RANDOM_USER_AGENT,
    REQUEST_TIMEOUT,
    RATE_LIMIT_DELAY,
    CACHE_DIR,
)
from modules.utils import (
    setup_logger,
    rate_limit,
    cache_to_file,
    load_cached_file,
    validate_url,
    normalize_url,
    clean_text,
    get_timestamp,
)
from modules.discovery_scrapers.aafpe_scraper import (
    scrape_aafpe_programs,
    filter_by_states,
)

# Initialize logger
setup_logger("target_discovery")

# User agent for requests
ua = UserAgent() if USE_RANDOM_USER_AGENT else None

# Import Playwright fetcher for sites that block static requests (403 Forbidden)
try:
    from playwright.sync_api import sync_playwright
    from config.settings import PLAYWRIGHT_TIMEOUT, HEADLESS_BROWSER
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not available for target discovery")


def get_user_agent() -> str:
    """Get user agent string."""
    if USE_RANDOM_USER_AGENT and ua:
        return ua.random
    return 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'


@rate_limit(calls=1, period=RATE_LIMIT_DELAY)
def fetch_page(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[BeautifulSoup]:
    """
    Fetch a web page and return BeautifulSoup object.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        BeautifulSoup object or None if failed
    """
    headers = {
        'User-Agent': get_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }

    try:
        logger.info(f"Fetching (static): {url}")
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.success(f"Successfully fetched (static): {url}")
        return soup

    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


@rate_limit(calls=1, period=RATE_LIMIT_DELAY)
def fetch_page_with_playwright(url: str) -> Optional[BeautifulSoup]:
    """
    Fetch a web page using Playwright (headless browser) to bypass bot detection.

    Use this for sites that return 403 Forbidden on static requests.

    Args:
        url: URL to fetch

    Returns:
        BeautifulSoup object or None if failed
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not available - cannot fetch dynamic content")
        return None

    try:
        logger.info(f"Fetching with Playwright: {url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=HEADLESS_BROWSER)
            context = browser.new_context(
                user_agent=get_user_agent(),
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()

            # Navigate to page with timeout
            page.goto(url, wait_until='domcontentloaded', timeout=PLAYWRIGHT_TIMEOUT)

            # Wait a bit for JavaScript to render
            page.wait_for_timeout(2000)

            # Get page content
            html = page.content()

            # Cleanup
            browser.close()

            soup = BeautifulSoup(html, 'html.parser')
            logger.success(f"Successfully fetched with Playwright: {url}")
            return soup

    except Exception as e:
        logger.error(f"Playwright fetch failed for {url}: {e}")
        return None


def get_aba_law_schools(states: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Get list of ABA-accredited law schools.

    Args:
        states: List of state abbreviations (e.g., ['CA', 'NY']). None = all states

    Returns:
        DataFrame with columns: name, state, city, url, type, accreditation_status
    """
    logger.info("=" * 70)
    logger.info("Starting ABA Law School Discovery")
    logger.info("=" * 70)

    # Check cache first
    cache_filename = f"aba_law_schools_{get_timestamp()}.csv"
    if states:
        cache_filename = f"aba_law_schools_{'_'.join(sorted(states))}_{get_timestamp()}.csv"

    # Try to load recent cache (within last 24 hours)
    cached_data = load_cached_file(cache_filename.replace(get_timestamp(), '*'), CACHE_DIR)
    if cached_data is not None:
        if states:
            cached_data = cached_data[cached_data['state'].isin(states)]
        logger.info(f"Using cached data: {len(cached_data)} law schools")
        return cached_data

    # ABA official list URL - use the alphabetical list page (has all 196 schools)
    aba_url = "https://www.americanbar.org/groups/legal_education/accreditation/approved-law-schools/alphabetical/"

    # The ABA site blocks static requests with 403 Forbidden, so use Playwright directly
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available - cannot scrape ABA website")
        logger.warning("Creating sample data for testing purposes...")
        # Fall through to sample data below
        soup = None
    else:
        soup = fetch_page_with_playwright(aba_url)

    schools = []

    if soup:
        logger.info("Parsing ABA alphabetical school list...")

        # Schools are in <li> elements with pattern: "School Name (Year)"
        lis = soup.find_all('li')

        for li in lis:
            text = li.get_text().strip()
            # Look for pattern: school name followed by (year)
            year_match = re.search(r'\((\d{4})\)', text)
            if year_match:
                # Extract school name (everything before the year)
                name_match = re.match(r'(.+?)\s*\(\d{4}\)', text)
                if name_match:
                    name = name_match.group(1).strip()
                    year = year_match.group(1)

                    # Get URL from link within this <li>
                    link = li.find('a', href=True)
                    school_url = ''
                    if link:
                        href = link['href']
                        if href.startswith('http'):
                            school_url = href
                        elif href.startswith('/'):
                            school_url = 'https://www.americanbar.org' + href

                    # Try to infer state from school name
                    # Many schools are named like: "California - Berkeley", "Arkansas - Little Rock"
                    state = None
                    city = None

                    # Pattern 1: "State - City" format
                    state_city_match = re.match(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*-\s*(.+)', name)
                    if state_city_match:
                        potential_state = state_city_match.group(1)
                        potential_city = state_city_match.group(2)
                        # Check if this looks like a state name (basic heuristic)
                        if len(potential_state.split()) <= 2:  # "New York", "South Carolina", etc.
                            state = potential_state
                            city = potential_city

                    # If no state extracted, leave as None (will need manual mapping or geo lookup)

                    school_entry = {
                        'name': name,
                        'state': state,
                        'city': city,
                        'url': school_url if validate_url(school_url) else '',
                        'type': 'Law School',
                        'accreditation_status': f'ABA Approved ({year})',
                    }
                    schools.append(school_entry)

        logger.success(f"Extracted {len(schools)} schools from ABA alphabetical list")

    # Create DataFrame
    df = pd.DataFrame(schools)

    if df.empty:
        logger.warning("No law schools found. The ABA website structure may have changed.")
        logger.warning("Creating sample data for testing purposes...")

        # Fallback: Create a sample dataset of known law schools
        sample_schools = [
            {'name': 'Harvard Law School', 'state': 'MA', 'city': 'Cambridge',
             'url': 'https://hls.harvard.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'Stanford Law School', 'state': 'CA', 'city': 'Stanford',
             'url': 'https://law.stanford.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'Yale Law School', 'state': 'CT', 'city': 'New Haven',
             'url': 'https://law.yale.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'UC Berkeley School of Law', 'state': 'CA', 'city': 'Berkeley',
             'url': 'https://www.law.berkeley.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'NYU School of Law', 'state': 'NY', 'city': 'New York',
             'url': 'https://www.law.nyu.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'Columbia Law School', 'state': 'NY', 'city': 'New York',
             'url': 'https://www.law.columbia.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'University of Chicago Law School', 'state': 'IL', 'city': 'Chicago',
             'url': 'https://www.law.uchicago.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'University of Michigan Law School', 'state': 'MI', 'city': 'Ann Arbor',
             'url': 'https://www.law.umich.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'UCLA School of Law', 'state': 'CA', 'city': 'Los Angeles',
             'url': 'https://law.ucla.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
            {'name': 'USC Gould School of Law', 'state': 'CA', 'city': 'Los Angeles',
             'url': 'https://gould.usc.edu', 'type': 'Law School', 'accreditation_status': 'ABA Approved'},
        ]
        df = pd.DataFrame(sample_schools)
        logger.info("Using sample law school data for testing")

    # Remove duplicates based on name
    df = df.drop_duplicates(subset=['name'], keep='first')

    # Filter by states if provided
    if states:
        # NOTE: State filtering only works for 18/197 schools with "State - City" naming
        # Most schools (Harvard, Yale, Florida, Miami, etc.) have state=None
        # TODO: Add school name → state mapping for better filtering

        df_filtered = df[df['state'].notna() & df['state'].isin(states)]

        if len(df_filtered) == 0:
            logger.warning(f"State filtering returned 0 law schools for {', '.join(states)}")
            logger.warning("Most ABA schools lack state data (only 18/197 have it)")
            logger.warning("Returning ALL law schools instead - filter manually or use master_institutions.csv")
            # Don't filter - return all schools
        else:
            df = df_filtered
            logger.info(f"Filtered to {len(df)} law schools in states: {', '.join(states)}")

    # Clean up data
    df['name'] = df['name'].apply(clean_text)
    df['url'] = df['url'].apply(lambda x: normalize_url(x) if validate_url(x) else '')

    # Sort by state and name
    df = df.sort_values(['state', 'name']).reset_index(drop=True)

    logger.success(f"Found {len(df)} ABA-accredited law schools")

    # Cache results
    if not df.empty:
        cache_to_file(df, cache_filename, CACHE_DIR)

    logger.info("=" * 70)
    return df


def get_paralegal_programs(states: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Get list of paralegal programs.

    Args:
        states: List of state abbreviations (e.g., ['CA', 'NY']). None = all states

    Returns:
        DataFrame with columns: name, state, city, url, type, accreditation_status
    """
    logger.info("=" * 70)
    logger.info("Starting Paralegal Program Discovery")
    logger.info("=" * 70)

    # Scrape AAfPE (American Association for Paralegal Education) directory
    logger.info("Scraping AAfPE paralegal programs directory...")

    try:
        # Use AAfPE scraper (with caching built-in)
        df = scrape_aafpe_programs(use_cache=True)

        if df.empty:
            logger.warning("No programs found from AAfPE scraper")
            return pd.DataFrame(columns=['name', 'state', 'city', 'url', 'type', 'accreditation_status'])

        # Filter by states if provided
        if states:
            df = filter_by_states(df, states)
            logger.info(f"Filtered to {len(df)} paralegal programs in states: {', '.join(states)}")

        # Transform columns to match expected output format
        # AAfPE scraper provides: name, url, state, program_type
        # Expected format: name, state, city, url, type, accreditation_status

        # Add missing columns
        df['city'] = ''  # City not available from AAfPE directory
        df['type'] = 'Paralegal Program'  # All are paralegal programs
        df['accreditation_status'] = 'AAfPE Member'  # All are AAfPE members

        # Reorder columns to match expected format
        df = df[['name', 'state', 'city', 'url', 'type', 'accreditation_status']]

    except Exception as e:
        logger.error(f"Failed to scrape AAfPE programs: {e}")
        logger.info("Falling back to empty dataset")
        return pd.DataFrame(columns=['name', 'state', 'city', 'url', 'type', 'accreditation_status'])

    # Sort by state and name
    df = df.sort_values(['state', 'name']).reset_index(drop=True)

    logger.success(f"Found {len(df)} paralegal programs")
    logger.info("=" * 70)
    return df


def load_master_institutions(states: Optional[List[str]] = None, program_type: str = 'both') -> pd.DataFrame:
    """
    Load institutions from master_institutions.csv database.

    This is FASTER and MORE RELIABLE than scraping ABA/AAfPE each time.

    Args:
        states: List of state names or abbreviations (e.g., ['FL', 'Florida', 'CA'])
        program_type: 'law', 'paralegal', or 'both'

    Returns:
        DataFrame with columns matching get_all_targets() output
    """
    from pathlib import Path

    master_file = Path('data/master_institutions.csv')

    if not master_file.exists():
        logger.error(f"Master database not found: {master_file}")
        logger.error("Run: python build_master_database.py")
        return pd.DataFrame()

    # Load CSV
    df = pd.read_csv(master_file)
    logger.info(f"Loaded {len(df)} institutions from master database")

    # Filter by program type
    if program_type == 'law':
        df = df[df['source'] == 'ABA']
    elif program_type == 'paralegal':
        df = df[df['source'] == 'AAfPE']
    # else 'both' - keep all

    # Filter by state (now using direct state column match - 100% coverage after enrichment)
    if states:
        # Normalize state filters to uppercase (state column is uppercase: CA, NY, TX, etc.)
        state_filters = [s.upper() for s in states]

        # Direct state column filtering (works for all institutions now)
        df_filtered = df[df['state'].isin(state_filters)]

        if len(df_filtered) == 0:
            logger.warning(f"No institutions found for states: {', '.join(states)}")
            logger.warning("Available states: " + ", ".join(df['state'].unique()[:20]))
        else:
            logger.info(f"Filtered to {len(df_filtered)} institutions matching states: {', '.join(states)}")

        df = df_filtered

    return df


def get_all_targets(states: Optional[List[str]] = None, program_type: str = 'both') -> pd.DataFrame:
    """
    Get all target institutions (law schools and/or paralegal programs).

    NOW USES master_institutions.csv for better performance and reliability.

    Args:
        states: List of state names or abbreviations (e.g., ['FL', 'Florida', 'CA'])
        program_type: 'law', 'paralegal', or 'both'

    Returns:
        Combined DataFrame of all targets
    """
    logger.info(f"Discovering targets: {program_type.upper()}")
    if states:
        logger.info(f"States: {', '.join(states)}")
    else:
        logger.info("States: ALL")

    # Try to load from master database first
    df = load_master_institutions(states, program_type)

    if not df.empty:
        logger.success(f"Total targets discovered: {len(df)}")
        return df

    # Fallback to old scraping method if master DB doesn't exist
    logger.warning("Master database not found, falling back to live scraping...")

    dfs = []

    if program_type in ['law', 'both']:
        law_schools = get_aba_law_schools(states)
        if not law_schools.empty:
            dfs.append(law_schools)

    if program_type in ['paralegal', 'both']:
        paralegal_programs = get_paralegal_programs(states)
        if not paralegal_programs.empty:
            dfs.append(paralegal_programs)

    if not dfs:
        logger.warning("No targets found")
        return pd.DataFrame()

    # Combine all targets
    combined = pd.concat(dfs, ignore_index=True)

    logger.success(f"Total targets discovered: {len(combined)}")
    logger.info(f"  Law Schools: {len(combined[combined['type'] == 'Law School'])}")
    logger.info(f"  Paralegal Programs: {len(combined[combined['type'] == 'Paralegal Program'])}")

    return combined


# =============================================================================
# Export public API
# =============================================================================

__all__ = [
    'get_aba_law_schools',
    'get_paralegal_programs',
    'get_all_targets',
    'fetch_page',
]
