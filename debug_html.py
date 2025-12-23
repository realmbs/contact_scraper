"""
Debug script to inspect HTML structure from Playwright.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.contact_extractor import fetch_page_with_playwright
from modules.utils import setup_logger

logger = setup_logger("debug_html")

url = "https://law.stanford.edu/directory/?tax_and_terms=1067"

logger.info(f"Fetching {url} with Playwright...")
soup = fetch_page_with_playwright(url)

if soup:
    # Find profile/contact sections
    profiles = soup.find_all(['div', 'section', 'article'], class_=lambda x: x and any(
        keyword in str(x).lower() for keyword in ['profile', 'person', 'staff', 'faculty']
    ))

    logger.info(f"Found {len(profiles)} profile sections")

    if profiles:
        # Show first profile structure
        first = profiles[0]
        print("\n" + "=" * 70)
        print("FIRST PROFILE HTML:")
        print("=" * 70)
        print(first.prettify()[:2000])
        print("...\n")

        # Look for common patterns
        print("=" * 70)
        print("ANALYSIS:")
        print("=" * 70)

        # Names
        headings = first.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'b'])
        print(f"\nHeadings ({len(headings)}):")
        for h in headings[:5]:
            print(f"  - {h.name}: {h.get_text(strip=True)}")

        # Links
        links = first.find_all('a')
        print(f"\nLinks ({len(links)}):")
        for link in links[:5]:
            print(f"  - href: {link.get('href')}")
            print(f"    text: {link.get_text(strip=True)}")

        # Emails
        emails = first.find_all('a', href=lambda x: x and 'mailto:' in x)
        print(f"\nEmails ({len(emails)}):")
        for email in emails[:5]:
            print(f"  - {email.get('href')}")

        # Classes
        print(f"\nClasses on first profile:")
        print(f"  {first.get('class')}")

        # All text
        print(f"\nFull text content:")
        print(first.get_text(separator=' | ', strip=True)[:500])
