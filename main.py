#!/usr/bin/env python3
"""
Legal Education Contact Scraper - Main CLI Interface

Complete workflow: Target Discovery + Contact Extraction
Discovers institutions and extracts contact information.
"""

import sys
from typing import List, Optional

from loguru import logger
from tqdm import tqdm

from config.settings import validate_config, OUTPUT_DIR
from modules.utils import setup_logger, save_dataframe
from modules.target_discovery import get_all_targets
from modules.contact_extractor import scrape_multiple_institutions
from modules.email_validator import enrich_contact_data


# US State Abbreviations
US_STATES = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
]


def print_banner():
    """Print application banner."""
    print("=" * 70)
    print(" " * 15 + "LEGAL EDUCATION CONTACT SCRAPER")
    print(" " * 18 + "Target Discovery + Contact Extraction")
    print("=" * 70)
    print()


def get_user_input_states() -> Optional[List[str]]:
    """
    Get states from user input.

    Returns:
        List of state abbreviations or None for all states
    """
    print("Which states would you like to target?")
    print("  - Enter state abbreviations separated by commas (e.g., CA, NY, TX)")
    print("  - Enter 'ALL' for all states")
    print("  - Press Enter for sample states (CA, NY, TX)")
    print()

    user_input = input("States: ").strip().upper()

    if not user_input:
        # Default to sample states
        return ['CA', 'NY', 'TX']

    if user_input == 'ALL':
        return None  # None means all states

    # Parse comma-separated list
    states = [s.strip() for s in user_input.split(',')]

    # Validate state abbreviations
    invalid_states = [s for s in states if s not in US_STATES]
    if invalid_states:
        logger.warning(f"Invalid state abbreviations: {', '.join(invalid_states)}")
        logger.warning("Removing invalid states...")
        states = [s for s in states if s in US_STATES]

    if not states:
        logger.error("No valid states provided")
        return None

    return states


def get_user_input_program_type() -> str:
    """
    Get program type from user input.

    Returns:
        'law', 'paralegal', or 'both'
    """
    print("\nWhich type of programs would you like to discover?")
    print("  1. Law Schools only")
    print("  2. Paralegal Programs only")
    print("  3. Both (default)")
    print()

    user_input = input("Choice [1-3]: ").strip()

    if user_input == '1':
        return 'law'
    elif user_input == '2':
        return 'paralegal'
    else:
        return 'both'


def get_user_input_mode() -> str:
    """
    Get execution mode from user input.

    Returns:
        'discovery' or 'full'
    """
    print("\nWhat would you like to do?")
    print("  1. Discovery only (find institutions)")
    print("  2. Full extraction (discovery + contact scraping) (default)")
    print()

    user_input = input("Choice [1-2]: ").strip()

    if user_input == '1':
        return 'discovery'
    else:
        return 'full'


def get_max_institutions() -> Optional[int]:
    """
    Get maximum number of institutions to scrape.

    Returns:
        Integer limit or None for all
    """
    print("\nHow many institutions would you like to scrape?")
    print("  - Enter a number (e.g., 5)")
    print("  - Press Enter for all discovered institutions")
    print()

    user_input = input("Limit: ").strip()

    if not user_input:
        return None

    try:
        limit = int(user_input)
        if limit <= 0:
            logger.warning("Invalid limit, using all institutions")
            return None
        return limit
    except ValueError:
        logger.warning("Invalid input, using all institutions")
        return None


def main():
    """Main entry point for the scraper."""
    # Setup logging
    setup_logger("main")

    # Print banner
    print_banner()

    # Validate configuration
    logger.info("Validating configuration...")
    validate_config()
    print()

    # Get user input
    states = get_user_input_states()
    program_type = get_user_input_program_type()
    mode = get_user_input_mode()

    max_institutions = None
    if mode == 'full':
        max_institutions = get_max_institutions()

    # Confirm settings
    print("\n" + "=" * 70)
    print("CONFIGURATION SUMMARY")
    print("=" * 70)
    print(f"Mode: {mode.upper()}")
    print(f"States: {', '.join(states) if states else 'ALL'}")
    print(f"Program Type: {program_type.upper()}")
    if mode == 'full':
        print(f"Institution Limit: {max_institutions if max_institutions else 'ALL'}")
    print("=" * 70)
    print()

    confirm = input("Proceed? [Y/n]: ").strip().lower()
    if confirm and confirm not in ['y', 'yes']:
        logger.info("Operation cancelled by user")
        return

    # Run target discovery
    print("\n" + "=" * 70)
    print("PHASE 1: DISCOVERING TARGETS")
    print("=" * 70)
    print()

    try:
        targets = get_all_targets(states=states, program_type=program_type)

        if targets.empty:
            logger.error("No targets found")
            return

        # Display discovery results
        print("\n" + "=" * 70)
        print("DISCOVERY RESULTS")
        print("=" * 70)
        print(f"Total Targets: {len(targets)}")
        print(f"  Law Schools: {len(targets[targets['type'] == 'Law School'])}")
        print(f"  Paralegal Programs: {len(targets[targets['type'] == 'Paralegal Program'])}")
        print()

        # Show breakdown by state
        print("Breakdown by State:")
        state_counts = targets['state'].value_counts()
        for state, count in state_counts.items():
            print(f"  {state}: {count}")
        print()

        # Save targets
        print("Saving targets...")
        targets_file = save_dataframe(
            targets,
            'targets_discovered.csv',
            output_dir=OUTPUT_DIR,
            add_timestamp=True
        )
        logger.success(f"Targets saved to: {targets_file}")

        # If discovery only, stop here
        if mode == 'discovery':
            print("\n" + "=" * 70)
            print("DISCOVERY COMPLETE")
            print("=" * 70)
            print(f"Results saved to: {targets_file}")
            print()
            print("Next Steps:")
            print("  - Review the discovered targets")
            print("  - Run in 'Full extraction' mode to scrape contacts")
            print("=" * 70)
            return

        # Phase 2: Contact Extraction
        print("\n" + "=" * 70)
        print("PHASE 2: EXTRACTING CONTACTS")
        print("=" * 70)
        print()

        contacts = scrape_multiple_institutions(targets, max_institutions=max_institutions)

        # Phase 3: Email Validation & Enrichment (if contacts found)
        if not contacts.empty:
            print("\n" + "=" * 70)
            print("PHASE 3: EMAIL VALIDATION & ENRICHMENT")
            print("=" * 70)
            print()

            # Enrich contact data with email validation
            contacts = enrich_contact_data(contacts)

        # Display contact extraction results
        print("\n" + "=" * 70)
        print("CONTACT EXTRACTION RESULTS")
        print("=" * 70)

        if contacts.empty:
            print("No contacts extracted.")
            print()
            print("Common reasons:")
            print("  - Anti-scraping measures (403 Forbidden)")
            print("  - JavaScript-heavy sites (need Playwright)")
            print("  - Outdated URLs or changed website structures")
            print()
            print("Recommendations:")
            print("  - Try fewer institutions for testing")
            print("  - Check logs for specific errors")
            print("  - Consider enabling Playwright for JavaScript sites")
        else:
            print(f"Total Contacts: {len(contacts)}")
            print(f"  Law Schools: {len(contacts[contacts['program_type'] == 'Law School'])}")
            print(f"  Paralegal Programs: {len(contacts[contacts['program_type'] == 'Paralegal Program'])}")
            print()

            # Email and phone stats
            emails_found = len(contacts[contacts['email'] != ''])
            phones_found = len(contacts[contacts['phone'] != ''])
            print(f"Contacts with email: {emails_found} ({emails_found/len(contacts)*100:.1f}%)")
            print(f"Contacts with phone: {phones_found} ({phones_found/len(contacts)*100:.1f}%)")
            print()

            # Email validation stats (if Phase 3 completed)
            if 'email_status' in contacts.columns:
                validated = len(contacts[contacts['email_status'].isin(['valid', 'deliverable'])])
                catchall = len(contacts[contacts['email_is_catchall'] == True])
                invalid = len(contacts[contacts['email_status'].isin(['invalid', 'undeliverable'])])

                print("Email Quality:")
                if emails_found > 0:
                    print(f"  Validated deliverable: {validated} ({validated/emails_found*100:.1f}%)")
                    print(f"  Catch-all domains: {catchall} ({catchall/emails_found*100:.1f}%)")
                    print(f"  Invalid: {invalid} ({invalid/emails_found*100:.1f}%)")
                else:
                    print("  No emails to validate")
                print()

            # Confidence distribution
            high_conf = len(contacts[contacts['confidence_score'] >= 75])
            med_conf = len(contacts[(contacts['confidence_score'] >= 50) & (contacts['confidence_score'] < 75)])
            low_conf = len(contacts[contacts['confidence_score'] < 50])

            print("Confidence Distribution:")
            print(f"  High (75+):     {high_conf} ({high_conf/len(contacts)*100:.1f}%)")
            print(f"  Medium (50-74): {med_conf} ({med_conf/len(contacts)*100:.1f}%)")
            print(f"  Low (<50):      {low_conf} ({low_conf/len(contacts)*100:.1f}%)")
            print()

            # Top matched roles
            role_counts = contacts['matched_role'].value_counts()
            if not role_counts.empty:
                print("Top Matched Roles:")
                for role, count in role_counts.head(5).items():
                    if role:
                        print(f"  {role}: {count}")
                print()

            # Save contacts
            print("Saving contacts...")
            contacts_file = save_dataframe(
                contacts,
                'contacts_raw.csv',
                output_dir=OUTPUT_DIR,
                add_timestamp=True
            )
            logger.success(f"Contacts saved to: {contacts_file}")

        # Final summary
        print("\n" + "=" * 70)
        print("EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Targets saved to: {targets_file}")
        if not contacts.empty:
            print(f"Contacts saved to: {contacts_file}")
        print()
        print("Next Steps:")
        print("  - Review extracted contacts")
        if not contacts.empty:
            print("  - Proceed to Phase 3: Email Validation & Enrichment")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        logger.info("Operation cancelled by user (KeyboardInterrupt)")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
