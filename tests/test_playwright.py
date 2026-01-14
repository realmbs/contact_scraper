"""
Quick test script for Playwright integration.

Tests the new smart fetching on Stanford Law School directory.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.contact_extractor import (
    fetch_page_smart,
    fetch_page_with_playwright,
    extract_contacts_from_page
)
from modules.utils import setup_logger
from config.settings import LAW_SCHOOL_ROLES

# Initialize logger
logger = setup_logger("test_playwright")

def test_playwright_fetch():
    """Test Playwright fetching on Stanford directory."""

    url = "https://law.stanford.edu/directory/?tax_and_terms=1067"  # Faculty directory

    logger.info("=" * 70)
    logger.info("Testing Playwright Integration")
    logger.info("=" * 70)

    # Test 1: Smart fetch (should use Playwright due to empty static content)
    logger.info("\n1. Testing smart fetch (static → Playwright fallback)...")
    soup = fetch_page_smart(url)

    if soup:
        text_content = soup.get_text(strip=True)
        logger.success(f"Smart fetch succeeded! Content length: {len(text_content)} chars")

        # Count potential contact elements
        profiles = soup.find_all(['div', 'section', 'article'], class_=lambda x: x and any(
            keyword in str(x).lower() for keyword in ['profile', 'person', 'staff', 'faculty']
        ))
        logger.info(f"Found {len(profiles)} potential contact sections")

        # Try extracting contacts
        contacts = extract_contacts_from_page(
            url,
            soup,
            LAW_SCHOOL_ROLES,
            "Stanford Law School",
            "https://law.stanford.edu",
            "CA",
            "Law School"
        )

        logger.info(f"Extracted {len(contacts)} contacts")

        if contacts:
            logger.success("✓ Contact extraction working!")
            for i, contact in enumerate(contacts[:3], 1):
                logger.info(f"\nContact {i}:")
                logger.info(f"  Name: {contact.get('full_name', 'N/A')}")
                logger.info(f"  Title: {contact.get('title', 'N/A')}")
                logger.info(f"  Email: {contact.get('email', 'N/A')}")
                logger.info(f"  Confidence: {contact.get('confidence_score', 0)}")
        else:
            logger.warning("⚠ No contacts extracted - may need to adjust parsing logic")
    else:
        logger.error("✗ Smart fetch failed")

    # Test 2: Direct Playwright fetch
    logger.info("\n2. Testing direct Playwright fetch...")
    pw_soup = fetch_page_with_playwright(url)

    if pw_soup:
        pw_text = pw_soup.get_text(strip=True)
        logger.success(f"Playwright direct fetch succeeded! Content length: {len(pw_text)} chars")
    else:
        logger.error("✗ Playwright direct fetch failed")

    logger.info("\n" + "=" * 70)
    logger.info("Test Complete")
    logger.info("=" * 70)


if __name__ == '__main__':
    test_playwright_fetch()
