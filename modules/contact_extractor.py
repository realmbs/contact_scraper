"""
Contact Extraction Module for Legal Education Contact Scraper.

Extracts contact information from law school and paralegal program websites.
Uses intelligent directory discovery, fuzzy title matching, and email pattern detection.
"""

import re
import time
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urljoin, urlparse
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup
from loguru import logger
from fuzzywuzzy import fuzz
from fake_useragent import UserAgent

from config.settings import (
    LAW_SCHOOL_ROLES,
    PARALEGAL_PROGRAM_ROLES,
    ALL_TARGET_ROLES,
    USE_RANDOM_USER_AGENT,
    REQUEST_TIMEOUT,
    RATE_LIMIT_DELAY,
    MIN_CONFIDENCE_SCORE,
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

# Initialize logger
setup_logger("contact_extractor")

# User agent for requests
ua = UserAgent() if USE_RANDOM_USER_AGENT else None


def get_user_agent() -> str:
    """Get user agent string."""
    if USE_RANDOM_USER_AGENT and ua:
        return ua.random
    return 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'


# =============================================================================
# Title Matching with Fuzzy Logic
# =============================================================================

def match_title_to_role(
    title: str,
    target_roles: List[str],
    threshold: int = 70
) -> Tuple[Optional[str], int, int]:
    """
    Match a job title to target roles using fuzzy matching.

    Uses multiple fuzzy matching strategies:
    1. Token sort ratio (handles word order variations)
    2. Partial ratio (handles titles with extra words)
    3. Keyword detection (specific role keywords)

    Args:
        title: Job title to match
        target_roles: List of target role names
        threshold: Minimum fuzzy match score (0-100)

    Returns:
        Tuple of (matched_role, confidence_score, match_score)
        - matched_role: Best matching role name or None
        - confidence_score: Confidence points for scoring (0-20)
        - match_score: Fuzzy match score (0-100)
    """
    title_clean = clean_text(title).lower()

    if not title_clean:
        return None, 0, 0

    best_match = None
    best_score = 0

    # Keywords that boost confidence for each category
    law_keywords = ['law', 'legal', 'library', 'librarian', 'dean', 'experiential', 'clinical', 'writing']
    paralegal_keywords = ['paralegal', 'legal studies', 'workforce', 'career', 'technical']

    for role in target_roles:
        role_clean = clean_text(role).lower()

        # Calculate fuzzy match scores
        token_sort = fuzz.token_sort_ratio(title_clean, role_clean)
        partial = fuzz.partial_ratio(title_clean, role_clean)
        simple = fuzz.ratio(title_clean, role_clean)

        # Use the best score from different methods
        score = max(token_sort, partial, simple)

        # Boost score if key words match
        role_words = set(role_clean.split())
        title_words = set(title_clean.split())
        common_words = role_words.intersection(title_words)

        if common_words:
            # Boost based on number of matching words
            word_boost = min(15, len(common_words) * 5)
            score = min(100, score + word_boost)

        if score > best_score:
            best_score = score
            best_match = role

    # Calculate confidence points (0-20 for title match)
    confidence_score = 0
    if best_score >= 90:
        confidence_score = 20  # Exact or very close match
    elif best_score >= threshold:
        confidence_score = 10  # Good match
    else:
        best_match = None  # Below threshold

    return best_match, confidence_score, best_score


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
    Find directory/staff pages on institution website.

    Looks for common patterns in navigation and links:
    - /faculty, /staff, /administration
    - /directory, /people, /about/people
    - /our-team, /leadership

    Args:
        base_url: Institution's base URL
        soup: BeautifulSoup object of homepage
        program_type: 'law' or 'paralegal' for context-specific searching

    Returns:
        List of directory page URLs
    """
    directory_urls = set()

    # Common directory page patterns
    patterns = [
        r'faculty',
        r'staff',
        r'people',
        r'directory',
        r'administration',
        r'team',
        r'leadership',
        r'contact',
        r'about.*people',
        r'about.*staff',
        r'about.*faculty',
    ]

    # Program-specific patterns
    if program_type == 'law':
        patterns.extend([
            r'library.*staff',
            r'clinical.*faculty',
            r'academic.*affairs',
        ])
    elif program_type == 'paralegal':
        patterns.extend([
            r'paralegal.*faculty',
            r'legal.*studies',
            r'department',
        ])

    # Find all links
    for link in soup.find_all('a', href=True):
        href = link['href'].lower()
        text = clean_text(link.get_text()).lower()

        # Check if URL or link text matches patterns
        for pattern in patterns:
            if re.search(pattern, href) or re.search(pattern, text):
                # Construct absolute URL
                full_url = urljoin(base_url, link['href'])

                # Validate and add
                if validate_url(full_url):
                    directory_urls.add(normalize_url(full_url))
                    logger.debug(f"Found directory page: {full_url}")
                break

    return list(directory_urls)


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

    # Look for name in common heading tags or class names
    for tag in section.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'b', 'span', 'div']):
        classes = ' '.join(tag.get('class', [])).lower()
        tag_text = clean_text(tag.get_text())

        if any(keyword in classes for keyword in ['name', 'title', 'heading']):
            if not name and len(tag_text) > 3 and len(tag_text.split()) >= 2:
                # Likely a name
                name = tag_text

        if any(keyword in classes for keyword in ['title', 'position', 'role', 'job']):
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

    # Extract email
    email_tag = section.find('a', href=re.compile(r'mailto:', re.I))
    if email_tag:
        email = email_tag['href'].replace('mailto:', '').strip()
    else:
        # Try extracting from text
        email = extract_email(text)

    # Extract phone
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

    # Match title to target roles
    matched_role = None
    title_confidence = 0
    title_match_score = 0

    if title:
        matched_role, title_confidence, title_match_score = match_title_to_role(
            title,
            target_roles
        )

    # Skip if title doesn't match our targets
    if title and not matched_role:
        logger.debug(f"Skipping contact: title '{title}' doesn't match target roles")
        return None

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

    # Build contact record
    contact = {
        'institution_name': institution_name,
        'institution_url': institution_url,
        'state': state,
        'program_type': program_type,
        'first_name': name_parts['first_name'],
        'last_name': name_parts['last_name'],
        'full_name': name or '',
        'title': title or '',
        'matched_role': matched_role or '',
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
        # Fetch homepage
        import requests
        headers = {
            'User-Agent': get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        response = requests.get(institution_url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

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
                dir_response = requests.get(dir_url, headers=headers, timeout=REQUEST_TIMEOUT)
                dir_response.raise_for_status()
                dir_soup = BeautifulSoup(dir_response.content, 'html.parser')

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
]
