#!/usr/bin/env python3
"""
Legal Education Contact Scraper - Main CLI Interface

Phase 1: Target Discovery
Discovers law schools and paralegal programs for scraping.
"""

import sys
from typing import List, Optional

from loguru import logger
from tqdm import tqdm

from config.settings import validate_config, OUTPUT_DIR
from modules.utils import setup_logger, save_dataframe
from modules.target_discovery import get_all_targets


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
    print(" " * 22 + "Phase 1: Target Discovery")
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

    # Confirm settings
    print("\n" + "=" * 70)
    print("CONFIGURATION SUMMARY")
    print("=" * 70)
    print(f"States: {', '.join(states) if states else 'ALL'}")
    print(f"Program Type: {program_type.upper()}")
    print("=" * 70)
    print()

    confirm = input("Proceed with target discovery? [Y/n]: ").strip().lower()
    if confirm and confirm not in ['y', 'yes']:
        logger.info("Operation cancelled by user")
        return

    # Run target discovery
    print("\n" + "=" * 70)
    print("DISCOVERING TARGETS")
    print("=" * 70)
    print()

    try:
        targets = get_all_targets(states=states, program_type=program_type)

        if targets.empty:
            logger.error("No targets found")
            return

        # Display results
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

        # Save results
        print("Saving results...")
        output_file = save_dataframe(
            targets,
            'targets_discovered.csv',
            output_dir=OUTPUT_DIR,
            add_timestamp=True
        )

        print("\n" + "=" * 70)
        print("PHASE 1 COMPLETE")
        print("=" * 70)
        print(f"Results saved to: {output_file}")
        print()
        print("Next Steps:")
        print("  - Review the discovered targets")
        print("  - Proceed to Phase 2: Contact Extraction (coming soon)")
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
