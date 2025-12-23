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

# Initialize logger
setup_logger("target_discovery")

# User agent for requests
ua = UserAgent() if USE_RANDOM_USER_AGENT else None


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
        logger.info(f"Fetching: {url}")
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        logger.success(f"Successfully fetched: {url}")
        return soup

    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
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

    # ABA official list URL
    aba_url = "https://www.americanbar.org/groups/legal_education/resources/aba_approved_law_schools/"

    soup = fetch_page(aba_url)

    schools = []

    if soup:
        # The ABA website has a table/list of law schools
        # Let's try multiple parsing strategies

        # Strategy 1: Look for links containing law school names
        logger.info("Parsing ABA website for law schools...")

        # Find all links that might be law schools
        for link in soup.find_all('a', href=True):
            text = clean_text(link.get_text())
            href = link['href']

            # Skip empty or too short text
            if len(text) < 5:
                continue

            # Look for patterns indicating law schools
            if any(keyword in text.lower() for keyword in [
                'law school', 'school of law', 'college of law',
                'law center', 'university', 'college'
            ]):
                # Try to extract location info
                state = None
                city = None

                # Look for state abbreviations in text or nearby
                state_pattern = r'\b([A-Z]{2})\b'
                state_match = re.search(state_pattern, text)
                if state_match:
                    state = state_match.group(1)

                # Parse URL to get website
                school_url = href
                if not href.startswith('http'):
                    school_url = urljoin(aba_url, href)

                school_entry = {
                    'name': text,
                    'state': state,
                    'city': city,
                    'url': school_url if validate_url(school_url) else '',
                    'type': 'Law School',
                    'accreditation_status': 'ABA Approved',
                }

                schools.append(school_entry)

        # Strategy 2: Look for specific HTML structures (tables, lists)
        # Check for tables
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    # Look for school name and location
                    for i, cell in enumerate(cells):
                        text = clean_text(cell.get_text())
                        if 'law' in text.lower() and len(text) > 10:
                            # Potential school found in table
                            link = cell.find('a', href=True)
                            school_url = ''
                            if link:
                                school_url = link['href']
                                if not school_url.startswith('http'):
                                    school_url = urljoin(aba_url, school_url)

                            # Try to find state in adjacent cells
                            state = None
                            if i + 1 < len(cells):
                                next_text = clean_text(cells[i + 1].get_text())
                                state_match = re.search(r'\b([A-Z]{2})\b', next_text)
                                if state_match:
                                    state = state_match.group(1)

                            school_entry = {
                                'name': text,
                                'state': state,
                                'city': None,
                                'url': school_url if validate_url(school_url) else '',
                                'type': 'Law School',
                                'accreditation_status': 'ABA Approved',
                            }
                            schools.append(school_entry)

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
        df = df[df['state'].isin(states)]
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

    # Check cache first
    cache_filename = f"paralegal_programs_{get_timestamp()}.csv"
    if states:
        cache_filename = f"paralegal_programs_{'_'.join(sorted(states))}_{get_timestamp()}.csv"

    cached_data = load_cached_file(cache_filename.replace(get_timestamp(), '*'), CACHE_DIR)
    if cached_data is not None:
        if states:
            cached_data = cached_data[cached_data['state'].isin(states)]
        logger.info(f"Using cached data: {len(cached_data)} paralegal programs")
        return cached_data

    # AAfPE (American Association for Paralegal Education) directory
    aafpe_url = "https://www.aafpe.org/"

    logger.info("Searching for paralegal programs...")
    logger.warning("Note: Full implementation requires detailed scraping of AAfPE and state systems")
    logger.info("Creating sample dataset for testing purposes...")

    # Sample paralegal programs for testing
    sample_programs = [
        {'name': 'UCLA Extension Paralegal Program', 'state': 'CA', 'city': 'Los Angeles',
         'url': 'https://www.uclaextension.edu/law', 'type': 'Paralegal Program', 'accreditation_status': 'AAfPE Approved'},
        {'name': 'UC Berkeley Extension Paralegal Program', 'state': 'CA', 'city': 'Berkeley',
         'url': 'https://extension.berkeley.edu/programs/paralegal', 'type': 'Paralegal Program', 'accreditation_status': 'AAfPE Approved'},
        {'name': 'De Anza College Paralegal Studies', 'state': 'CA', 'city': 'Cupertino',
         'url': 'https://www.deanza.edu/paralegal/', 'type': 'Paralegal Program', 'accreditation_status': 'AAfPE Approved'},
        {'name': 'City College of San Francisco Paralegal Studies', 'state': 'CA', 'city': 'San Francisco',
         'url': 'https://www.ccsf.edu/paralegal', 'type': 'Paralegal Program', 'accreditation_status': 'State Approved'},
        {'name': 'NYU School of Professional Studies Paralegal', 'state': 'NY', 'city': 'New York',
         'url': 'https://www.sps.nyu.edu/paralegal', 'type': 'Paralegal Program', 'accreditation_status': 'AAfPE Approved'},
        {'name': 'Pace University Paralegal Studies', 'state': 'NY', 'city': 'New York',
         'url': 'https://www.pace.edu/paralegal', 'type': 'Paralegal Program', 'accreditation_status': 'AAfPE Approved'},
        {'name': 'Adelphi University Paralegal Studies', 'state': 'NY', 'city': 'Garden City',
         'url': 'https://academics.adelphi.edu/paralegal/', 'type': 'Paralegal Program', 'accreditation_status': 'AAfPE Approved'},
        {'name': 'University of Texas at Arlington Paralegal', 'state': 'TX', 'city': 'Arlington',
         'url': 'https://www.uta.edu/academics/paralegal', 'type': 'Paralegal Program', 'accreditation_status': 'AAfPE Approved'},
        {'name': 'Houston Community College Paralegal', 'state': 'TX', 'city': 'Houston',
         'url': 'https://www.hccs.edu/programs/paralegal/', 'type': 'Paralegal Program', 'accreditation_status': 'State Approved'},
        {'name': 'Lone Star College Paralegal Technology', 'state': 'TX', 'city': 'The Woodlands',
         'url': 'https://www.lonestar.edu/paralegal', 'type': 'Paralegal Program', 'accreditation_status': 'State Approved'},
    ]

    df = pd.DataFrame(sample_programs)

    # Filter by states if provided
    if states:
        df = df[df['state'].isin(states)]
        logger.info(f"Filtered to {len(df)} paralegal programs in states: {', '.join(states)}")

    # Sort by state and name
    df = df.sort_values(['state', 'name']).reset_index(drop=True)

    logger.success(f"Found {len(df)} paralegal programs")

    # Cache results
    if not df.empty:
        cache_to_file(df, cache_filename, CACHE_DIR)

    logger.info("=" * 70)
    return df


def get_all_targets(states: Optional[List[str]] = None, program_type: str = 'both') -> pd.DataFrame:
    """
    Get all target institutions (law schools and/or paralegal programs).

    Args:
        states: List of state abbreviations. None = all states
        program_type: 'law', 'paralegal', or 'both'

    Returns:
        Combined DataFrame of all targets
    """
    logger.info(f"Discovering targets: {program_type.upper()}")
    if states:
        logger.info(f"States: {', '.join(states)}")
    else:
        logger.info("States: ALL")

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
