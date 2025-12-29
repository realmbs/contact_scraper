"""
AAfPE Paralegal Program Scraper

Scrapes the American Association for Paralegal Education (AAfPE) member
schools directory to discover paralegal programs nationwide.

URL: https://aafpe.org/memberschoools
Expected Output: ~350 paralegal programs organized by state

Author: Claude Code
Date: 2025-12-26
Sprint: 1.2
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from typing import List, Dict, Optional
import re
from pathlib import Path
import json
from datetime import datetime, timedelta

from modules.utils import setup_logger, rate_limit
from config.settings import RATE_LIMIT_DELAY, CACHE_DIR

# Initialize logger
logger = setup_logger("aafpe_scraper")

# User agent for requests
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'


def get_user_agent() -> str:
    """Get user agent string for requests."""
    return USER_AGENT

# Configuration
AAFPE_URL = "https://aafpe.org/memberschoools"
CACHE_FILE = Path(CACHE_DIR) / "aafpe_programs.json"
CACHE_DURATION = timedelta(hours=24)  # 24-hour cache


def fetch_aafpe_page() -> Optional[BeautifulSoup]:
    """
    Fetch the AAfPE member schools directory page.

    Returns:
        BeautifulSoup object or None if fetch fails
    """
    try:
        logger.info(f"Fetching AAfPE member schools directory: {AAFPE_URL}")

        headers = {
            'User-Agent': get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

        response = requests.get(AAFPE_URL, headers=headers, timeout=30)
        response.raise_for_status()

        logger.success(f"Successfully fetched AAfPE page ({len(response.content)} bytes)")
        return BeautifulSoup(response.content, 'html.parser')

    except requests.RequestException as e:
        logger.error(f"Failed to fetch AAfPE page: {e}")
        return None


def parse_state_sections(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Parse state-organized program sections from AAfPE directory.

    Args:
        soup: BeautifulSoup object of the page

    Returns:
        List of dictionaries with program data:
        [
            {
                'name': 'University of XYZ',
                'url': 'https://xyz.edu',
                'state': 'California',
                'program_type': 'paralegal'
            },
            ...
        ]
    """
    programs = []

    # Find all state sections
    # The page structure has h2 tags for state names followed by ul lists
    state_headers = soup.find_all('h2')

    logger.info(f"Found {len(state_headers)} state sections")

    for header in state_headers:
        state_name = header.get_text().strip()

        # Skip non-state sections (like "Other")
        if state_name.lower() in ['other', 'non-member', 'organizations']:
            logger.debug(f"Skipping non-state section: {state_name}")
            continue

        # Find the next ul element (sibling of h2)
        ul_list = header.find_next_sibling('ul')

        if not ul_list:
            logger.warning(f"No program list found for state: {state_name}")
            continue

        # Extract all program links in this state
        program_links = ul_list.find_all('a')

        for link in program_links:
            program_name = link.get_text().strip()
            program_url = link.get('href', '').strip()

            # Skip empty entries
            if not program_name:
                continue

            # Validate and normalize URL
            if program_url and not program_url.startswith('http'):
                if program_url.startswith('//'):
                    program_url = 'https:' + program_url
                elif program_url.startswith('/'):
                    program_url = 'https://aafpe.org' + program_url
                else:
                    program_url = 'https://' + program_url

            # Clean up program name (remove extra whitespace)
            program_name = re.sub(r'\s+', ' ', program_name).strip()

            programs.append({
                'name': program_name,
                'url': program_url or '',
                'state': state_name,
                'program_type': 'paralegal'
            })

            logger.debug(f"  [{state_name}] {program_name}")

    logger.success(f"Extracted {len(programs)} paralegal programs from AAfPE directory")
    return programs


def save_to_cache(programs: List[Dict[str, str]]) -> None:
    """
    Save programs to cache file with timestamp.

    Args:
        programs: List of program dictionaries
    """
    try:
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'programs': programs,
            'count': len(programs)
        }

        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)

        logger.debug(f"Saved {len(programs)} programs to cache: {CACHE_FILE}")

    except Exception as e:
        logger.warning(f"Failed to save cache: {e}")


def load_from_cache() -> Optional[List[Dict[str, str]]]:
    """
    Load programs from cache if available and not expired.

    Returns:
        List of program dictionaries or None if cache invalid/expired
    """
    try:
        if not CACHE_FILE.exists():
            logger.debug("No cache file found")
            return None

        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)

        # Check cache age
        cache_time = datetime.fromisoformat(cache_data['timestamp'])
        cache_age = datetime.now() - cache_time

        if cache_age > CACHE_DURATION:
            logger.info(f"Cache expired (age: {cache_age.total_seconds() / 3600:.1f}h)")
            return None

        programs = cache_data.get('programs', [])
        logger.success(f"Loaded {len(programs)} programs from cache (age: {cache_age.total_seconds() / 3600:.1f}h)")

        return programs

    except Exception as e:
        logger.warning(f"Failed to load cache: {e}")
        return None


@rate_limit(calls=1, period=RATE_LIMIT_DELAY)
def scrape_aafpe_programs(use_cache: bool = True) -> pd.DataFrame:
    """
    Main entry point: Scrape AAfPE paralegal programs directory.

    Args:
        use_cache: Whether to use cached results (default: True)

    Returns:
        DataFrame with columns: name, url, state, program_type

    Example:
        >>> df = scrape_aafpe_programs()
        >>> print(df.head())
                                     name                              url         state program_type
        0  University of Alabama at Birmingham  https://www.uab.edu/paralegal  Alabama      paralegal
        1              Auburn University         https://www.auburn.edu      Alabama      paralegal
        ...
    """
    logger.info("=" * 80)
    logger.info("AAfPE PARALEGAL PROGRAM SCRAPER")
    logger.info("=" * 80)

    # Try cache first
    if use_cache:
        cached_programs = load_from_cache()
        if cached_programs:
            return pd.DataFrame(cached_programs)

    # Fetch and parse
    soup = fetch_aafpe_page()

    if not soup:
        logger.error("Failed to fetch AAfPE page - returning empty DataFrame")
        return pd.DataFrame(columns=['name', 'url', 'state', 'program_type'])

    # Parse programs
    programs = parse_state_sections(soup)

    if not programs:
        logger.warning("No programs extracted from AAfPE page")
        return pd.DataFrame(columns=['name', 'url', 'state', 'program_type'])

    # Save to cache
    save_to_cache(programs)

    # Convert to DataFrame
    df = pd.DataFrame(programs)

    # Log summary
    logger.info("\nSummary:")
    logger.info(f"  Total programs: {len(df)}")
    logger.info(f"  States covered: {df['state'].nunique()}")
    logger.info(f"  Programs with URLs: {df['url'].astype(bool).sum()}")

    # Top 5 states by program count
    logger.info("\nTop 5 states by program count:")
    top_states = df['state'].value_counts().head(5)
    for state, count in top_states.items():
        logger.info(f"  {state}: {count}")

    logger.info("=" * 80)

    return df


def filter_by_states(df: pd.DataFrame, states: List[str]) -> pd.DataFrame:
    """
    Filter programs by state(s).

    Args:
        df: DataFrame of programs
        states: List of state names or abbreviations (case-insensitive)

    Returns:
        Filtered DataFrame

    Example:
        >>> df = scrape_aafpe_programs()
        >>> ca_programs = filter_by_states(df, ['California', 'CA'])
    """
    if not states:
        return df

    # Normalize state inputs to lowercase for matching
    state_filters = [s.lower().strip() for s in states]

    # Create state abbreviation mapping
    state_abbrev = {
        'alabama': 'al', 'alaska': 'ak', 'arizona': 'az', 'arkansas': 'ar',
        'california': 'ca', 'colorado': 'co', 'connecticut': 'ct', 'delaware': 'de',
        'florida': 'fl', 'georgia': 'ga', 'hawaii': 'hi', 'idaho': 'id',
        'illinois': 'il', 'indiana': 'in', 'iowa': 'ia', 'kansas': 'ks',
        'kentucky': 'ky', 'louisiana': 'la', 'maine': 'me', 'maryland': 'md',
        'massachusetts': 'ma', 'michigan': 'mi', 'minnesota': 'mn', 'mississippi': 'ms',
        'missouri': 'mo', 'montana': 'mt', 'nebraska': 'ne', 'nevada': 'nv',
        'new hampshire': 'nh', 'new jersey': 'nj', 'new mexico': 'nm', 'new york': 'ny',
        'north carolina': 'nc', 'north dakota': 'nd', 'ohio': 'oh', 'oklahoma': 'ok',
        'oregon': 'or', 'pennsylvania': 'pa', 'rhode island': 'ri', 'south carolina': 'sc',
        'south dakota': 'sd', 'tennessee': 'tn', 'texas': 'tx', 'utah': 'ut',
        'vermont': 'vt', 'virginia': 'va', 'washington': 'wa', 'west virginia': 'wv',
        'wisconsin': 'wi', 'wyoming': 'wy'
    }

    # Match by full name or abbreviation
    def matches_state(state_name: str) -> bool:
        state_lower = state_name.lower().strip()

        # Check if state name directly matches
        if state_lower in state_filters:
            return True

        # Check if state abbreviation matches
        state_abbr = state_abbrev.get(state_lower, '')
        if state_abbr in state_filters:
            return True

        return False

    filtered = df[df['state'].apply(matches_state)]

    logger.info(f"Filtered to {len(filtered)} programs in states: {', '.join(states)}")

    return filtered


# ============================================================================
# CLI Testing
# ============================================================================

if __name__ == '__main__':
    import sys

    # Test scraper
    print("\n" + "=" * 80)
    print("TESTING AAfPE PARALEGAL PROGRAM SCRAPER")
    print("=" * 80 + "\n")

    # Scrape all programs
    df = scrape_aafpe_programs(use_cache=False)  # Force fresh scrape for testing

    print(f"\nTotal programs scraped: {len(df)}")
    print(f"States covered: {df['state'].nunique()}")

    # Test state filtering
    if len(sys.argv) > 1:
        test_states = sys.argv[1].split(',')
        print(f"\nTesting state filter: {test_states}")
        filtered = filter_by_states(df, test_states)

        print(f"\nFiltered results ({len(filtered)} programs):")
        print(filtered.to_string(index=False))
    else:
        # Show sample
        print("\nSample programs (first 10):")
        print(df.head(10).to_string(index=False))

        print("\n\nTip: Run with state filter:")
        print("  python modules/discovery_scrapers/aafpe_scraper.py CA,NY,TX")
