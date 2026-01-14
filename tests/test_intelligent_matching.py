"""
Quick test to compare intelligent title matching vs baseline.
Tests on Stanford only for fast comparison.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from modules.target_discovery import get_all_targets
from modules.contact_extractor import scrape_multiple_institutions
from modules.utils import setup_logger

# Initialize logger
logger = setup_logger("test_intelligent")

def main():
    logger.info("=" * 80)
    logger.info("INTELLIGENT TITLE MATCHING - COMPARISON TEST")
    logger.info("=" * 80)

    # Get Stanford only
    targets = get_all_targets(states=['CA'], program_type='law')
    stanford = targets[targets['name'].str.contains('Stanford', case=False, na=False)].head(1)

    if stanford.empty:
        logger.error("Stanford not found")
        return

    logger.info(f"\nTesting: {stanford.iloc[0]['name']}")
    logger.info(f"URL: {stanford.iloc[0]['url']}")

    # Scrape contacts
    contacts = scrape_multiple_institutions(stanford)

    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("RESULTS - WITH INTELLIGENT TITLE MATCHING")
    logger.info("=" * 80)

    if contacts.empty:
        logger.warning("No contacts extracted")
        return

    total = len(contacts)
    with_email = len(contacts[contacts['email'] != ''])

    logger.success(f"Total contacts extracted: {total}")
    logger.info(f"Contacts with email: {with_email}")
    logger.info(f"Contacts with phone: {len(contacts[contacts['phone'] != ''])}")

    # Confidence distribution
    high = len(contacts[contacts['confidence_score'] >= 75])
    medium = len(contacts[(contacts['confidence_score'] >= 50) & (contacts['confidence_score'] < 75)])
    low = len(contacts[contacts['confidence_score'] < 50])

    logger.info(f"\nConfidence score distribution:")
    logger.info(f"  High (75+):     {high} ({high/total*100:.1f}%)")
    logger.info(f"  Medium (50-74): {medium} ({medium/total*100:.1f}%)")
    logger.info(f"  Low (<50):      {low} ({low/total*100:.1f}%)")

    avg_conf = contacts['confidence_score'].mean()
    logger.info(f"  Average:        {avg_conf:.1f}")

    # Check for intelligent matching features
    if 'is_temporary' in contacts.columns:
        temp_roles = len(contacts[contacts['is_temporary'] == True])
        shared_roles = len(contacts[contacts['is_shared_role'] == True])

        logger.info(f"\nIntelligent Matching Metadata:")
        logger.info(f"  Temporary roles (interim/acting): {temp_roles}")
        logger.info(f"  Shared roles (co-director): {shared_roles}")

        # Show normalized titles
        if temp_roles > 0:
            logger.info(f"\n  Temporary role examples:")
            temp_contacts = contacts[contacts['is_temporary'] == True].head(3)
            for _, row in temp_contacts.iterrows():
                logger.info(f"    - Original: {row['title']}")
                logger.info(f"      Normalized: {row['title_normalized']}")
                logger.info(f"      Modifiers: {row['title_modifiers']}")

    # Top matched roles
    role_counts = contacts['matched_role'].value_counts()
    logger.info(f"\nTop matched roles:")
    for role, count in role_counts.head(10).items():
        if role:
            logger.info(f"  {role}: {count}")

    # Sample contacts
    logger.info("\n" + "=" * 80)
    logger.info("SAMPLE CONTACTS (Top 5)")
    logger.info("=" * 80)

    for idx, row in contacts.head(5).iterrows():
        logger.info(f"\n{idx + 1}. {row['full_name']}")
        logger.info(f"   Title: {row['title']}")
        if row.get('title_normalized') and row['title_normalized'] != row['title']:
            logger.info(f"   Normalized: {row['title_normalized']}")
        if row.get('title_modifiers'):
            logger.info(f"   Modifiers: {row['title_modifiers']}")
        logger.info(f"   Matched Role: {row['matched_role']}")
        logger.info(f"   Email: {row['email'] or 'N/A'}")
        logger.info(f"   Confidence: {row['confidence_score']}")

    logger.info("\n" + "=" * 80)
    logger.info("Test complete!")
    logger.info("=" * 80)

if __name__ == '__main__':
    import pandas as pd
    main()
