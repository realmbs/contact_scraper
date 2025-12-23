"""
Test script to verify contact extraction on real institutions.

This script will:
1. Get a small set of law schools and paralegal programs
2. Attempt to scrape contacts from each
3. Display results and statistics
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.target_discovery import get_all_targets
from modules.contact_extractor import scrape_multiple_institutions
from modules.utils import setup_logger, save_dataframe
from config.settings import validate_config

# Initialize logger
logger = setup_logger("test_scraper")


def main():
    """Run contact extraction test."""
    logger.info("=" * 70)
    logger.info("Contact Extraction Test - Phase 2")
    logger.info("=" * 70)

    # Validate configuration
    validate_config()

    # Get sample targets
    logger.info("\nDiscovering test targets...")
    targets = get_all_targets(states=['CA', 'NY'], program_type='both')

    if targets.empty:
        logger.error("No targets found. Cannot proceed with test.")
        return

    logger.info(f"\nFound {len(targets)} total targets")
    logger.info(f"  Law Schools: {len(targets[targets['type'] == 'Law School'])}")
    logger.info(f"  Paralegal Programs: {len(targets[targets['type'] == 'Paralegal Program'])}")

    # Limit to 3 of each type for testing
    law_schools = targets[targets['type'] == 'Law School'].head(3)
    paralegal_programs = targets[targets['type'] == 'Paralegal Program'].head(3)

    test_targets = pd.concat([law_schools, paralegal_programs], ignore_index=True)

    logger.info(f"\nTesting on {len(test_targets)} institutions:")
    for idx, row in test_targets.iterrows():
        logger.info(f"  {idx + 1}. {row['name']} ({row['type']})")

    # Scrape contacts
    logger.info("\n" + "=" * 70)
    logger.info("Starting Contact Extraction")
    logger.info("=" * 70 + "\n")

    contacts = scrape_multiple_institutions(test_targets)

    # Display results
    logger.info("\n" + "=" * 70)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 70)

    if contacts.empty:
        logger.warning("No contacts extracted.")
        logger.info("\nThis is expected for the initial test as we're using sample data")
        logger.info("and may need to adjust scraping strategies for specific sites.")
    else:
        logger.success(f"Total contacts extracted: {len(contacts)}")

        # Statistics
        logger.info(f"\nBreakdown by program type:")
        logger.info(f"  Law Schools: {len(contacts[contacts['program_type'] == 'Law School'])}")
        logger.info(f"  Paralegal Programs: {len(contacts[contacts['program_type'] == 'Paralegal Program'])}")

        logger.info(f"\nContacts with email: {len(contacts[contacts['email'] != ''])}")
        logger.info(f"Contacts with phone: {len(contacts[contacts['phone'] != ''])}")

        # Confidence score distribution
        high_conf = len(contacts[contacts['confidence_score'] >= 75])
        med_conf = len(contacts[(contacts['confidence_score'] >= 50) & (contacts['confidence_score'] < 75)])
        low_conf = len(contacts[contacts['confidence_score'] < 50])

        logger.info(f"\nConfidence score distribution:")
        logger.info(f"  High (75+):     {high_conf} ({high_conf/len(contacts)*100:.1f}%)")
        logger.info(f"  Medium (50-74): {med_conf} ({med_conf/len(contacts)*100:.1f}%)")
        logger.info(f"  Low (<50):      {low_conf} ({low_conf/len(contacts)*100:.1f}%)")

        # Top matched roles
        role_counts = contacts['matched_role'].value_counts()
        logger.info(f"\nTop matched roles:")
        for role, count in role_counts.head(5).items():
            if role:
                logger.info(f"  {role}: {count}")

        # Save results
        output_file = save_dataframe(contacts, "test_contacts_raw.csv")
        logger.success(f"\nResults saved to: {output_file}")

        # Show sample contacts
        logger.info("\n" + "=" * 70)
        logger.info("SAMPLE CONTACTS (Top 5)")
        logger.info("=" * 70)

        for idx, row in contacts.head(5).iterrows():
            logger.info(f"\n{idx + 1}. {row['full_name']}")
            logger.info(f"   Title: {row['title']}")
            logger.info(f"   Institution: {row['institution_name']}")
            logger.info(f"   Email: {row['email'] or 'N/A'}")
            logger.info(f"   Phone: {row['phone'] or 'N/A'}")
            logger.info(f"   Confidence: {row['confidence_score']}")

    logger.info("\n" + "=" * 70)
    logger.info("Test complete!")
    logger.info("=" * 70)


if __name__ == '__main__':
    import pandas as pd
    main()
