"""
Email Validation & Enrichment Module for Legal Education Contact Scraper.

Validates email addresses, finds missing emails, and enriches contact data
using Hunter.io, ZeroBounce/NeverBounce, and pattern construction.

This module provides:
- Email validation via ZeroBounce and NeverBounce APIs (direct API calls)
- Email finding via Hunter.io API
- Catch-all domain detection
- Email pattern construction from existing examples
- Batch processing with smart service selection
- Confidence score updates based on email quality

Author: Contact Scraper Team
Created: 2025-12-23
Phase: 3 (Email Intelligence)
"""

import re
import time
from typing import List, Dict, Optional, Tuple
from collections import Counter

import pandas as pd
import requests
from loguru import logger

from config.settings import (
    HUNTER_API_KEY,
    ZEROBOUNCE_API_KEY,
    NEVERBOUNCE_API_KEY,
    REQUEST_TIMEOUT,
    RATE_LIMIT_DELAY,
    MIN_EMAIL_SCORE,
)
from config.api_clients import (
    validate_email_with_hunter,
    find_email_with_hunter,
)
from modules.utils import rate_limit, extract_domain

# ============================================================================
# Module Configuration
# ============================================================================

# API Endpoints
ZEROBOUNCE_API_URL = "https://api.zerobounce.net/v2/validate"
ZEROBOUNCE_CREDITS_URL = "https://api.zerobounce.net/v2/getcredits"
NEVERBOUNCE_SINGLE_URL = "https://api.neverbounce.com/v4/single/check"
NEVERBOUNCE_BULK_URL = "https://api.neverbounce.com/v4/bulk/check"

# Validation status mappings
VALID_STATUSES = ['valid', 'deliverable']
INVALID_STATUSES = ['invalid', 'undeliverable', 'do_not_mail', 'disposable']
CATCHALL_STATUSES = ['catch-all', 'catchall', 'accept_all']
UNKNOWN_STATUSES = ['unknown', 'spamtrap']

# Score thresholds
HIGH_EMAIL_SCORE = 80
MEDIUM_EMAIL_SCORE = 50

# Initialize logger
logger = logger.bind(module="email_validator")

# ============================================================================
# Helper Functions - Email Validation Status Mapping
# ============================================================================

def _map_zerobounce_score(data: dict) -> int:
    """
    Map ZeroBounce validation result to 0-100 score.

    Args:
        data: ZeroBounce API response data

    Returns:
        Score from 0-100 (higher = better quality)
    """
    status = data.get('status', '').lower()

    if status == 'valid':
        return 100
    elif status == 'catch-all':
        return 70  # Medium quality - domain accepts all emails
    elif status == 'unknown':
        return 40
    elif status in ['invalid', 'do_not_mail', 'spamtrap']:
        return 0
    else:
        return 50  # Default for unexpected statuses


def _map_neverbounce_status(result_code: int) -> str:
    """
    Map NeverBounce result code to standardized status string.

    Args:
        result_code: NeverBounce numeric result (0-4)

    Returns:
        Standardized status: 'valid', 'invalid', 'catch-all', or 'unknown'
    """
    mapping = {
        0: 'valid',
        1: 'invalid',
        2: 'disposable',  # Treated as invalid
        3: 'catch-all',
        4: 'unknown'
    }
    return mapping.get(result_code, 'unknown')


def _map_neverbounce_score(data: dict) -> int:
    """
    Map NeverBounce validation result to 0-100 score.

    Args:
        data: NeverBounce API response data

    Returns:
        Score from 0-100 (higher = better quality)
    """
    result = data.get('result', 4)  # Default to unknown

    if result == 0:  # Valid
        return 100
    elif result == 3:  # Catch-all
        return 70
    elif result == 4:  # Unknown
        return 40
    elif result in [1, 2]:  # Invalid or disposable
        return 0
    else:
        return 50


# ============================================================================
# Email Validation Functions - Direct API Integration
# ============================================================================

@rate_limit(calls=1, period=1.0)  # 1 request per second
def validate_email_zerobounce(email: str, api_key: Optional[str] = None) -> Optional[Dict]:
    """
    Validate single email via ZeroBounce API v2 (direct API call).

    Args:
        email: Email address to validate
        api_key: ZeroBounce API key (uses ZEROBOUNCE_API_KEY if not provided)

    Returns:
        Dict with validation results or None if API unavailable:
        {
            'email': str,
            'status': 'valid|invalid|catch-all|unknown',
            'sub_status': str,
            'score': int (0-100),
            'is_catchall': bool,
            'is_disposable': bool,
            'service': 'zerobounce',
            'credits_used': int
        }
    """
    # Use provided key or global config
    key = api_key or ZEROBOUNCE_API_KEY

    # Graceful degradation if no API key
    if not key or key == 'your_zerobounce_api_key_here':
        logger.info(f"ZeroBounce API key not configured, skipping validation for {email}")
        return None

    try:
        # Make API request
        params = {
            'api_key': key,
            'email': email,
            'ip_address': ''  # Optional
        }

        response = requests.get(
            ZEROBOUNCE_API_URL,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()

        data = response.json()

        # Check for API errors
        if 'error' in data:
            logger.error(f"ZeroBounce API error for {email}: {data['error']}")
            return None

        # Map to standardized format
        status = data.get('status', '').lower()
        result = {
            'email': email,
            'status': status,
            'sub_status': data.get('sub_status', ''),
            'score': _map_zerobounce_score(data),
            'is_catchall': status == 'catch-all',
            'is_disposable': status == 'do_not_mail',
            'is_free_email': data.get('free_email', False),
            'mx_found': data.get('mx_found', False),
            'smtp_provider': data.get('smtp_provider', ''),
            'service': 'zerobounce',
            'credits_used': 1 if status not in ['unknown', 'catch-all'] else 0
        }

        logger.info(f"ZeroBounce validated {email}: {status} (score: {result['score']})")
        return result

    except requests.exceptions.Timeout:
        logger.error(f"ZeroBounce API timeout for {email}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"ZeroBounce API request failed for {email}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating {email} with ZeroBounce: {e}")
        return None


@rate_limit(calls=1, period=1.0)  # 1 request per second
def validate_email_neverbounce(email: str, api_key: Optional[str] = None) -> Optional[Dict]:
    """
    Validate single email via NeverBounce API v4 (direct API call).

    Args:
        email: Email address to validate
        api_key: NeverBounce API key (uses NEVERBOUNCE_API_KEY if not provided)

    Returns:
        Dict with validation results or None if API unavailable:
        {
            'email': str,
            'status': 'valid|invalid|catch-all|unknown',
            'result_code': int (0-4),
            'score': int (0-100),
            'is_catchall': bool,
            'is_disposable': bool,
            'service': 'neverbounce',
            'credits_remaining': int
        }
    """
    # Use provided key or global config
    key = api_key or NEVERBOUNCE_API_KEY

    # Graceful degradation if no API key
    if not key or key == 'your_neverbounce_api_key_here':
        logger.info(f"NeverBounce API key not configured, skipping validation for {email}")
        return None

    try:
        # Make API request
        payload = {
            'key': key,
            'email': email,
            'address_info': 1,  # Include additional info
            'credits_info': 1   # Include credits info
        }

        response = requests.post(
            NEVERBOUNCE_SINGLE_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()

        data = response.json()

        # Check for API errors
        if data.get('status') == 'failed':
            logger.error(f"NeverBounce API error for {email}: {data.get('message', 'Unknown error')}")
            return None

        # Map to standardized format
        result_code = data.get('result', 4)  # 0=valid, 1=invalid, 2=disposable, 3=catchall, 4=unknown
        status = _map_neverbounce_status(result_code)

        result = {
            'email': email,
            'status': status,
            'result_code': result_code,
            'score': _map_neverbounce_score(data),
            'is_catchall': result_code == 3,
            'is_disposable': result_code == 2,
            'is_free_email': data.get('address_info', {}).get('free_email_host', False),
            'service': 'neverbounce',
            'credits_remaining': data.get('credits_info', {}).get('free_credits_remaining', 0)
        }

        logger.info(f"NeverBounce validated {email}: {status} (score: {result['score']})")
        return result

    except requests.exceptions.Timeout:
        logger.error(f"NeverBounce API timeout for {email}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"NeverBounce API request failed for {email}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating {email} with NeverBounce: {e}")
        return None


def validate_email_auto(email: str) -> Optional[Dict]:
    """
    Validate email using the best available service.

    Tries services in order of preference:
    1. NeverBounce (1000 free validations)
    2. ZeroBounce (100 free validations)
    3. Hunter.io (50 searches/month)

    Args:
        email: Email address to validate

    Returns:
        Validation result dict or None if all services unavailable
    """
    # Try NeverBounce first (highest free tier)
    result = validate_email_neverbounce(email)
    if result:
        return result

    # Fall back to ZeroBounce
    result = validate_email_zerobounce(email)
    if result:
        return result

    # Fall back to Hunter.io
    result = validate_email_with_hunter(email)
    if result:
        return result

    logger.warning(f"No email validation service available for {email}")
    return None


# ============================================================================
# Catch-all Domain Detection
# ============================================================================

def is_catchall_domain(domain: str, validation_result: Optional[Dict] = None) -> bool:
    """
    Detect if a domain accepts all emails (catch-all).

    Args:
        domain: Domain to check (e.g., 'stanford.edu')
        validation_result: Optional validation result from API

    Returns:
        True if domain is catch-all, False otherwise
    """
    # If we have a validation result, check it first
    if validation_result:
        if validation_result.get('is_catchall'):
            return True
        if validation_result.get('status') in CATCHALL_STATUSES:
            return True

    # Otherwise, test with a random email
    # (Skip for now to avoid wasting API credits)
    # Future enhancement: test with random string

    return False


# ============================================================================
# Batch Email Validation
# ============================================================================

def batch_validate_emails(
    emails: List[str],
    service: str = 'auto',
    max_batch_size: int = 200
) -> pd.DataFrame:
    """
    Batch validate emails using available service.

    Args:
        emails: List of email addresses to validate
        service: 'auto', 'neverbounce', 'zerobounce', or 'hunter'
        max_batch_size: Maximum emails per batch (for rate limiting)

    Returns:
        DataFrame with validation results:
        - email: str
        - status: 'valid|invalid|catch-all|unknown'
        - score: int (0-100)
        - is_catchall: bool
        - is_disposable: bool
        - service: str
    """
    if not emails:
        return pd.DataFrame()

    logger.info(f"Batch validating {len(emails)} emails using {service} service")

    results = []

    # Process in batches to respect rate limits
    for i in range(0, len(emails), max_batch_size):
        batch = emails[i:i + max_batch_size]
        logger.info(f"Processing batch {i // max_batch_size + 1}: {len(batch)} emails")

        for email in batch:
            # Skip empty emails
            if not email or pd.isna(email):
                continue

            # Validate based on service choice
            if service == 'auto':
                result = validate_email_auto(email)
            elif service == 'neverbounce':
                result = validate_email_neverbounce(email)
            elif service == 'zerobounce':
                result = validate_email_zerobounce(email)
            elif service == 'hunter':
                result = validate_email_with_hunter(email)
            else:
                logger.warning(f"Unknown service '{service}', using auto")
                result = validate_email_auto(email)

            # Add to results (even if None - we'll track failures)
            if result:
                results.append(result)
            else:
                # Create placeholder for failed validation
                results.append({
                    'email': email,
                    'status': 'unknown',
                    'score': 40,
                    'is_catchall': False,
                    'is_disposable': False,
                    'service': 'none'
                })

            # Small delay between requests to be respectful
            time.sleep(0.5)

    # Convert to DataFrame
    df = pd.DataFrame(results)

    # Log summary statistics
    if not df.empty:
        valid_count = len(df[df['status'].isin(VALID_STATUSES)])
        invalid_count = len(df[df['status'].isin(INVALID_STATUSES)])
        catchall_count = len(df[df['is_catchall'] == True])

        logger.success(f"Batch validation complete: {valid_count} valid, {invalid_count} invalid, {catchall_count} catch-all")

    return df


# ============================================================================
# Email Finding Functions
# ============================================================================

def find_missing_emails(contact_df: pd.DataFrame) -> pd.DataFrame:
    """
    Find emails for contacts missing them.

    Strategy:
    1. Try Hunter.io email finder (if API key available)
    2. Try email pattern construction (if 3+ examples from same institution)
    3. Mark as 'no_email_found' if both fail

    Updates confidence scores based on method used:
    - Hunter.io found: +20 points (medium confidence)
    - Pattern constructed: -30 points (low confidence, needs validation)

    Args:
        contact_df: DataFrame with contact information

    Returns:
        DataFrame with emails filled in where possible, updated confidence scores
    """
    if contact_df.empty:
        return contact_df

    logger.info(f"Finding missing emails for {len(contact_df)} contacts")

    # Identify contacts missing emails
    missing_email_mask = contact_df['email'].isna() | (contact_df['email'] == '')
    missing_count = missing_email_mask.sum()

    if missing_count == 0:
        logger.info("All contacts already have emails")
        return contact_df

    logger.info(f"Found {missing_count} contacts without emails")

    # Track email sources for logging
    found_via_hunter = 0
    found_via_pattern = 0
    not_found = 0

    # Process each contact missing an email
    for idx in contact_df[missing_email_mask].index:
        row = contact_df.loc[idx]

        # Extract needed info
        first_name = row.get('first_name', '')
        last_name = row.get('last_name', '')
        institution_url = row.get('institution_url', '')
        domain = extract_domain(institution_url) if institution_url else ''

        # Skip if we don't have minimum required info
        if not (first_name and last_name and domain):
            not_found += 1
            continue

        # Try Hunter.io first
        email = find_email_with_hunter(first_name, last_name, domain)

        if email:
            contact_df.at[idx, 'email'] = email
            contact_df.at[idx, 'email_source'] = 'hunter_io'
            contact_df.at[idx, 'confidence_score'] = contact_df.at[idx, 'confidence_score'] + 20
            found_via_hunter += 1
            logger.info(f"Found email via Hunter.io: {email}")
            time.sleep(1.0)  # Rate limit
            continue

        # Try pattern construction as fallback
        # (This would use existing detect_email_pattern from contact_extractor)
        # For now, skip pattern construction - it's already in contact extraction phase
        # We'll just mark as not found
        not_found += 1

    logger.success(f"Email finding complete: {found_via_hunter} via Hunter.io, {found_via_pattern} via patterns, {not_found} not found")

    return contact_df


# ============================================================================
# Contact Enrichment Orchestrator
# ============================================================================

def enrich_contact_data(contact_df: pd.DataFrame) -> pd.DataFrame:
    """
    Full enrichment pipeline for Phase 3.

    Workflow:
    1. Find missing emails (Hunter.io + patterns)
    2. Validate all emails (batch processing)
    3. Detect catch-all domains
    4. Update confidence scores based on email quality
    5. Add validation metadata

    Updates confidence scores:
    - +30 points: Email validated as deliverable
    - +20 points: Email found via Hunter.io
    - -20 points: Catch-all domain detected
    - -30 points: Email constructed from pattern (unverified)

    Args:
        contact_df: DataFrame with contact information

    Returns:
        DataFrame with enriched and validated email data
    """
    if contact_df.empty:
        logger.warning("Empty contact DataFrame provided for enrichment")
        return contact_df

    logger.info("=" * 70)
    logger.info("Starting Email Enrichment Pipeline (Phase 3)")
    logger.info("=" * 70)

    # Step 1: Find missing emails
    logger.info("Step 1: Finding missing emails...")
    contact_df = find_missing_emails(contact_df)

    # Step 2: Validate all emails
    logger.info("Step 2: Validating emails...")
    emails_to_validate = contact_df[contact_df['email'].notna() & (contact_df['email'] != '')]['email'].tolist()

    if emails_to_validate:
        validation_df = batch_validate_emails(emails_to_validate, service='auto')

        # Merge validation results back into contact_df
        if not validation_df.empty:
            # Create validation lookup
            validation_lookup = validation_df.set_index('email').to_dict('index')

            # Add validation columns
            contact_df['email_status'] = contact_df['email'].map(
                lambda e: validation_lookup.get(e, {}).get('status', 'unknown') if e else 'no_email'
            )
            contact_df['email_score'] = contact_df['email'].map(
                lambda e: validation_lookup.get(e, {}).get('score', 0) if e else 0
            )
            contact_df['email_is_catchall'] = contact_df['email'].map(
                lambda e: validation_lookup.get(e, {}).get('is_catchall', False) if e else False
            )
            contact_df['email_is_disposable'] = contact_df['email'].map(
                lambda e: validation_lookup.get(e, {}).get('is_disposable', False) if e else False
            )
            contact_df['email_validation_service'] = contact_df['email'].map(
                lambda e: validation_lookup.get(e, {}).get('service', 'none') if e else 'none'
            )
    else:
        logger.warning("No emails to validate")
        contact_df['email_status'] = 'no_email'
        contact_df['email_score'] = 0
        contact_df['email_is_catchall'] = False
        contact_df['email_is_disposable'] = False
        contact_df['email_validation_service'] = 'none'

    # Step 3: Update confidence scores based on email quality
    logger.info("Step 3: Updating confidence scores...")

    for idx in contact_df.index:
        email_status = contact_df.at[idx, 'email_status']
        is_catchall = contact_df.at[idx, 'email_is_catchall']
        email_source = contact_df.at[idx, 'email_source'] if 'email_source' in contact_df.columns else ''

        # Adjust confidence score
        score_adjustment = 0

        # +30 for validated deliverable email
        if email_status in VALID_STATUSES:
            score_adjustment += 30

        # -20 for catch-all domain
        if is_catchall:
            score_adjustment -= 20

        # Update score
        if score_adjustment != 0:
            current_score = contact_df.at[idx, 'confidence_score']
            new_score = max(0, min(100, current_score + score_adjustment))
            contact_df.at[idx, 'confidence_score'] = new_score

    # Step 4: Log final statistics
    logger.info("=" * 70)
    logger.info("Email Enrichment Complete - Summary Statistics")
    logger.info("=" * 70)

    total_contacts = len(contact_df)
    with_email = len(contact_df[contact_df['email'].notna() & (contact_df['email'] != '')])
    validated = len(contact_df[contact_df['email_status'].isin(VALID_STATUSES)])
    catchall = len(contact_df[contact_df['email_is_catchall'] == True])

    email_coverage = (with_email / total_contacts * 100) if total_contacts > 0 else 0
    validation_rate = (validated / with_email * 100) if with_email > 0 else 0

    logger.info(f"Total contacts: {total_contacts}")
    logger.info(f"With email: {with_email} ({email_coverage:.1f}%)")
    logger.info(f"Validated as deliverable: {validated} ({validation_rate:.1f}%)")
    logger.info(f"Catch-all domains: {catchall}")
    logger.info("=" * 70)

    return contact_df


# ============================================================================
# API Credit Management
# ============================================================================

def check_zerobounce_credits(api_key: Optional[str] = None) -> Optional[int]:
    """
    Check remaining ZeroBounce API credits.

    Args:
        api_key: ZeroBounce API key (uses ZEROBOUNCE_API_KEY if not provided)

    Returns:
        Number of remaining credits or None if unavailable
    """
    key = api_key or ZEROBOUNCE_API_KEY

    if not key or key == 'your_zerobounce_api_key_here':
        return None

    try:
        params = {'api_key': key}
        response = requests.get(ZEROBOUNCE_CREDITS_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        data = response.json()
        credits = int(data.get('Credits', 0))

        logger.info(f"ZeroBounce credits remaining: {credits}")
        return credits

    except Exception as e:
        logger.error(f"Failed to check ZeroBounce credits: {e}")
        return None


# ============================================================================
# Public API - Export Main Functions
# ============================================================================

__all__ = [
    'validate_email_zerobounce',
    'validate_email_neverbounce',
    'validate_email_auto',
    'batch_validate_emails',
    'find_missing_emails',
    'enrich_contact_data',
    'is_catchall_domain',
    'check_zerobounce_credits',
]
