"""
API Client Initialization with Graceful Degradation.

This module provides functions to initialize API clients for email finding,
validation, and enrichment. All APIs are optional - the system will work
without them, with gracefully degraded functionality.
"""

from typing import Optional
from loguru import logger

from config.settings import (
    HUNTER_API_KEY,
    ZEROBOUNCE_API_KEY,
    NEVERBOUNCE_API_KEY,
    PROXYCURL_API_KEY,
)


def get_hunter_client() -> Optional[object]:
    """
    Initialize Hunter.io client for email finding.

    Returns:
        Hunter client object if API key is available, None otherwise.
    """
    if not HUNTER_API_KEY or HUNTER_API_KEY == 'your_hunter_api_key_here':
        logger.info("Hunter.io API key not configured - email finding will be limited")
        return None

    try:
        from pyhunter import PyHunter
        client = PyHunter(HUNTER_API_KEY)
        logger.success("Hunter.io client initialized successfully")
        return client
    except ImportError:
        logger.warning("pyhunter package not installed - skipping Hunter.io integration")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Hunter.io client: {e}")
        return None


def get_zerobounce_client() -> Optional[object]:
    """
    Initialize ZeroBounce client for email validation.

    Returns:
        ZeroBounce client object if API key is available, None otherwise.
    """
    if not ZEROBOUNCE_API_KEY or ZEROBOUNCE_API_KEY == 'your_zerobounce_api_key_here':
        logger.info("ZeroBounce API key not configured - email validation will be limited")
        return None

    try:
        # Note: zerobounce package has installation issues
        # We'll implement direct API calls if needed
        logger.warning("ZeroBounce integration not yet implemented - use NeverBounce or direct API")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize ZeroBounce client: {e}")
        return None


def get_neverbounce_client() -> Optional[object]:
    """
    Initialize NeverBounce client for email validation.

    Returns:
        NeverBounce client object if API key is available, None otherwise.
    """
    if not NEVERBOUNCE_API_KEY or NEVERBOUNCE_API_KEY == 'your_neverbounce_api_key_here':
        logger.info("NeverBounce API key not configured - email validation will be limited")
        return None

    try:
        # NeverBounce implementation will be added when needed
        logger.info("NeverBounce integration pending - will use direct API calls")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize NeverBounce client: {e}")
        return None


def get_proxycurl_client() -> Optional[dict]:
    """
    Initialize Proxycurl configuration for LinkedIn enrichment.

    Note: Proxycurl doesn't have an official Python client, so we return
    a configuration dict for use with requests.

    Returns:
        Configuration dict if API key is available, None otherwise.
    """
    if not PROXYCURL_API_KEY or PROXYCURL_API_KEY == 'your_proxycurl_api_key_here':
        logger.info("Proxycurl API key not configured - LinkedIn enrichment disabled")
        return None

    try:
        config = {
            'api_key': PROXYCURL_API_KEY,
            'base_url': 'https://nubela.co/proxycurl/api/v2',
            'headers': {
                'Authorization': f'Bearer {PROXYCURL_API_KEY}'
            }
        }
        logger.success("Proxycurl configuration initialized successfully")
        return config
    except Exception as e:
        logger.error(f"Failed to initialize Proxycurl configuration: {e}")
        return None


def validate_email_with_hunter(email: str, hunter_client: Optional[object]) -> Optional[dict]:
    """
    Validate an email address using Hunter.io.

    Args:
        email: Email address to validate
        hunter_client: Hunter.io client instance (or None)

    Returns:
        Validation result dict or None if client not available
    """
    if not hunter_client:
        return None

    try:
        result = hunter_client.email_verifier(email)
        return {
            'email': email,
            'status': result.get('status'),
            'score': result.get('score', 0),
            'result': result.get('result'),
            'sources': result.get('sources', []),
        }
    except Exception as e:
        logger.warning(f"Hunter.io validation failed for {email}: {e}")
        return None


def find_email_with_hunter(
    first_name: str,
    last_name: str,
    domain: str,
    hunter_client: Optional[object]
) -> Optional[dict]:
    """
    Find an email address using Hunter.io.

    Args:
        first_name: Contact's first name
        last_name: Contact's last name
        domain: Institution domain (e.g., 'harvard.edu')
        hunter_client: Hunter.io client instance (or None)

    Returns:
        Email finding result dict or None if client not available
    """
    if not hunter_client:
        return None

    try:
        result = hunter_client.email_finder(
            first_name=first_name,
            last_name=last_name,
            domain=domain
        )
        return {
            'email': result.get('email'),
            'score': result.get('score', 0),
            'position': result.get('position'),
            'sources': result.get('sources', []),
        }
    except Exception as e:
        logger.warning(f"Hunter.io email finding failed for {first_name} {last_name} at {domain}: {e}")
        return None


def get_api_status() -> dict:
    """
    Get status of all API integrations.

    Returns:
        Dict mapping API names to availability status
    """
    return {
        'hunter': get_hunter_client() is not None,
        'zerobounce': get_zerobounce_client() is not None,
        'neverbounce': get_neverbounce_client() is not None,
        'proxycurl': get_proxycurl_client() is not None,
    }


# =============================================================================
# Export public API
# =============================================================================

__all__ = [
    'get_hunter_client',
    'get_zerobounce_client',
    'get_neverbounce_client',
    'get_proxycurl_client',
    'validate_email_with_hunter',
    'find_email_with_hunter',
    'get_api_status',
]
