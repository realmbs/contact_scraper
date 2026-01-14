#!/usr/bin/env python3
"""
Legal Education Contact Scraper - Main CLI Interface

Complete workflow: Target Discovery + Contact Extraction
Discovers institutions and extracts contact information.

OPTIMIZATIONS ENABLED:
- Phase 1: 100% state coverage (197 law schools + 199 paralegal programs)
- Phase 2: Multi-tier extraction (4-tier architecture)
- Phase 3: Email validation & enrichment (Hunter.io, ZeroBounce, NeverBounce)
- Phase 4: Deduplication & quality control
- Phase 6.1: Async profile link visiting (3 workers, 50% time reduction)
- Phase 6.2: Async directory processing (3 workers, parallel page fetching)
- Phase 6.3: Browser pooling (3 persistent browsers, eliminates launch overhead)
- Phase 6.4: Per-domain rate limiting (async, parallel domains)

PERFORMANCE: Berkeley validated at 3.42x speedup (21min → 6.13min)
"""

import sys
from typing import List, Optional

import pandas as pd
from loguru import logger
from tqdm import tqdm

from config.settings import validate_config, OUTPUT_DIR
from modules.utils import setup_logger, save_dataframe
from modules.target_discovery import get_all_targets
from modules.contact_extractor import run_async_scraping  # Sprint 2.1: Async architecture
from modules.email_validator import enrich_contact_data
from modules.deduplication import deduplicate_contacts, load_existing_database, compare_with_existing
from modules.statistics import calculate_contact_statistics
from modules.excel_output import create_excel_workbook
from modules.streaming_writer import StreamingContactWriter  # Progressive saves

# Sprint 2-3 optimization modules (for statistics display)
from modules.fetch_router import get_fetch_router
from modules.domain_rate_limiter import get_domain_rate_limiter
from modules.timeout_manager import get_timeout_manager


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


def get_existing_database_path() -> Optional[str]:
    """
    Get path to existing contacts database for comparison (optional).

    Returns:
        Path to existing database file or None
    """
    print("\nDo you have an existing contacts database to compare against?")
    print("  - Enter path to CSV or Excel file")
    print("  - Press Enter to skip (no comparison)")
    print()

    user_input = input("Database path: ").strip()

    if not user_input:
        return None

    # Expand ~ to home directory
    from pathlib import Path
    path = Path(user_input).expanduser()

    if not path.exists():
        logger.warning(f"File not found: {path}")
        logger.warning("Skipping database comparison...")
        return None

    if path.suffix.lower() not in ['.csv', '.xlsx', '.xls']:
        logger.warning(f"Unsupported file format: {path.suffix}")
        logger.warning("Only .csv and .xlsx files are supported")
        return None

    return str(path)


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
    existing_db_path = None
    if mode == 'full':
        max_institutions = get_max_institutions()
        existing_db_path = get_existing_database_path()

    # Confirm settings
    print("\n" + "=" * 70)
    print("CONFIGURATION SUMMARY")
    print("=" * 70)
    print(f"Mode: {mode.upper()}")
    print(f"States: {', '.join(states) if states else 'ALL'}")
    print(f"Program Type: {program_type.upper()}")
    if mode == 'full':
        print(f"Institution Limit: {max_institutions if max_institutions else 'ALL'}")
        print(f"Existing Database: {existing_db_path if existing_db_path else 'None (no comparison)'}")
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

        # Phase 2: Contact Extraction (with performance optimizations)
        print("\n" + "=" * 70)
        print("PHASE 2: EXTRACTING CONTACTS (OPTIMIZED)")
        print("=" * 70)
        print()

        # Performance optimizations enabled (Phase 6.1-6.4):
        # - 6x institution parallelization (async architecture)
        # - 3x profile link parallelization (async within each institution)
        # - 3x directory parallelization (async page fetching)
        # - Browser pooling (3 persistent browsers, eliminates 2-3s launch overhead)
        # - Per-domain rate limiting (async, allows parallel domain requests)
        # Expected: 3.42x speedup validated on Berkeley (21min → 6.13min)
        logger.info("Using async architecture with 6 parallel workers + multi-tier optimizations")

        # Create streaming writer for progressive saves and Ctrl+C support
        from modules.utils import get_timestamp
        progressive_csv = OUTPUT_DIR / f'contacts_progressive_{get_timestamp()}.csv'
        resume_state_file = OUTPUT_DIR / 'resume_state.json'

        streaming_writer = StreamingContactWriter(
            output_file=str(progressive_csv),
            resume_file=str(resume_state_file)
        )

        # Load resume state if exists
        streaming_writer.load_resume_state()
        if streaming_writer.institutions_completed:
            logger.warning(f"Found resume state: {len(streaming_writer.institutions_completed)} institutions already completed")
            logger.warning("Use Ctrl+C at any time to save progress and exit gracefully")
        else:
            logger.info("Progressive saves enabled - use Ctrl+C at any time to save progress")

        # Run scraping with progressive saves
        try:
            contacts = run_async_scraping(
                targets,
                max_institutions=max_institutions,
                max_parallel=6,
                streaming_writer=streaming_writer
            )
        except KeyboardInterrupt:
            # Graceful shutdown - load what was saved
            print("\n\n" + "=" * 70)
            print("SCRAPING INTERRUPTED - LOADING SAVED PROGRESS")
            print("=" * 70)
            print()

            if progressive_csv.exists():
                logger.info(f"Loading {streaming_writer.contacts_written} contacts from {progressive_csv}")
                contacts = pd.read_csv(progressive_csv)
                logger.success(f"Loaded {len(contacts)} contacts from progressive save file")

                # Show progress summary
                completed = len(streaming_writer.institutions_completed)
                total = len(targets) if max_institutions is None else min(max_institutions, len(targets))
                print(f"\nProgress: {completed}/{total} institutions completed ({completed/total*100:.1f}%)")
                print(f"Contacts saved: {len(contacts)}")
                print(f"\nResume state saved to: {resume_state_file}")
                print("To resume: Run the script again with the same parameters")
                print("=" * 70)
            else:
                logger.warning("No progressive save file found - no contacts extracted yet")
                contacts = pd.DataFrame()  # Empty DataFrame

                # Re-raise to exit gracefully
                raise

        # Phase 3: Email Validation & Enrichment (if contacts found)
        if not contacts.empty:
            print("\n" + "=" * 70)
            print("PHASE 3: EMAIL VALIDATION & ENRICHMENT")
            print("=" * 70)
            print()

            # Enrich contact data with email validation
            contacts = enrich_contact_data(contacts)

        # Phase 4: Deduplication, Statistics & Excel Output (if contacts found)
        if not contacts.empty:
            print("\n" + "=" * 70)
            print("PHASE 4: DEDUPLICATION & QUALITY CONTROL")
            print("=" * 70)
            print()

            # Step 1: Internal deduplication
            logger.info("Deduplicating contacts...")
            initial_count = len(contacts)
            contacts = deduplicate_contacts(contacts)
            duplicates_removed = initial_count - len(contacts)
            logger.success(f"Deduplication complete: {duplicates_removed} duplicates removed, {len(contacts)} unique contacts")

            # Step 2: Compare with existing database (if provided)
            new_contacts_df = contacts.copy()
            duplicates_df = None
            updates_df = None

            if existing_db_path:
                logger.info(f"Loading existing database from: {existing_db_path}")
                existing_db = load_existing_database(existing_db_path)

                if existing_db is not None:
                    logger.info("Comparing with existing database...")
                    new_contacts_df, duplicates_df, updates_df = compare_with_existing(contacts, existing_db)

                    logger.success(f"Comparison complete: {len(new_contacts_df)} new, {len(duplicates_df)} duplicates, {len(updates_df)} updates")

                    # Save classification results
                    if not new_contacts_df.empty:
                        new_file = save_dataframe(new_contacts_df, 'contacts_new.csv', output_dir=OUTPUT_DIR, add_timestamp=True)
                        logger.success(f"New contacts saved to: {new_file}")

                    if not duplicates_df.empty:
                        dup_file = save_dataframe(duplicates_df, 'contacts_duplicates.csv', output_dir=OUTPUT_DIR, add_timestamp=True)
                        logger.success(f"Duplicates saved to: {dup_file}")

                    if not updates_df.empty:
                        upd_file = save_dataframe(updates_df, 'contacts_updates.csv', output_dir=OUTPUT_DIR, add_timestamp=True)
                        logger.success(f"Updates saved to: {upd_file}")

            # Step 3: Calculate statistics
            logger.info("Calculating statistics...")
            stats = calculate_contact_statistics(contacts, targets)
            logger.success("Statistics calculation complete")

            # Step 4: Generate Excel workbook
            logger.info("Generating Excel workbook...")
            from modules.utils import get_timestamp
            excel_filename = f"contacts_final_{get_timestamp()}.xlsx"
            excel_path = OUTPUT_DIR / excel_filename

            success = create_excel_workbook(contacts, stats, str(excel_path), targets)

            if success:
                logger.success(f"Excel workbook created: {excel_path}")
            else:
                logger.error("Failed to create Excel workbook")

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

        # Display optimization statistics (Sprint 2-3 + Multi-Tier Phase 5-6)
        print("\n" + "=" * 70)
        print("OPTIMIZATION STATISTICS")
        print("=" * 70)
        print()
        print("NOTE: Phase 6.1-6.3 (async optimizations + browser pooling) are active")
        print("      but don't have separate statistics. Performance measured via total runtime.")
        print()

        # Fetch router stats
        try:
            router = get_fetch_router()
            router_stats = router.get_stats_summary()
            print("Smart Fetch Routing (Sprint 2.3):")
            print(f"  Domains tracked: {router_stats['domains_tracked']}")
            print(f"  Static fetches: {router_stats['static_total']} ({router_stats['static_rate']:.1%} success)")
            print(f"  Playwright fetches: {router_stats['playwright_total']} ({router_stats['playwright_rate']:.1%} success)")
            print(f"  Total fetches: {router_stats['total_fetches']}")
            print()
        except:
            pass  # Router stats not available

        # Domain rate limiter stats
        try:
            rate_limiter = get_domain_rate_limiter()
            limiter_stats = rate_limiter.get_stats()
            print("Per-Domain Rate Limiting (Sprint 3.1):")
            print(f"  Total requests: {limiter_stats['total_requests']}")
            print(f"  Total delays: {limiter_stats['total_delays']}s")
            print(f"  Avg delay per request: {limiter_stats['avg_delay_per_request']}s")
            print(f"  Domains accessed: {limiter_stats['domains_accessed']}")
            print(f"  Domains with errors: {limiter_stats['domains_with_errors']}")
            print()
        except:
            pass  # Rate limiter stats not available

        # Timeout manager stats
        try:
            timeout_mgr = get_timeout_manager()
            timeout_stats = timeout_mgr.get_stats()
            print("Intelligent Timeout Tuning (Sprint 3.3):")
            print(f"  Total requests: {timeout_stats['total_requests']}")
            print(f"  Timeouts: {timeout_stats['total_timeouts']} ({timeout_stats['timeout_rate']}%)")
            print(f"  Fast-fails: {timeout_stats['total_fast_fails']}")
            print(f"  Avg timeout: {timeout_stats['avg_timeout_ms']}ms (default: {timeout_stats['default_timeout_ms']}ms)")
            print(f"  Domains tracked: {timeout_stats['domains_tracked']}")
            print()
        except:
            pass  # Timeout stats not available

        # Multi-Tier extraction stats (Phase 5)
        try:
            from modules.page_classifier import get_page_classifier
            from modules.link_extractor import get_link_extractor
            from modules.email_deobfuscator import get_email_deobfuscator

            # Page classifier stats
            classifier = get_page_classifier()
            classifier_stats = classifier.stats
            if classifier_stats['total_classified'] > 0:
                print("Page Classification (Multi-Tier Phase 5):")
                print(f"  Total pages classified: {classifier_stats['total_classified']}")
                by_type = classifier_stats.get('by_type', {})
                if by_type:
                    for page_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:5]:
                        print(f"  {page_type}: {count}")
                print()

            # Link extractor stats
            link_extractor = get_link_extractor()
            link_stats = link_extractor.get_stats()
            if link_stats['pages_processed'] > 0:
                print("Profile Link Extraction (Multi-Tier Phase 5):")
                print(f"  Directory pages processed: {link_stats['pages_processed']}")
                print(f"  Total links found: {link_stats['total_links_found']}")
                print(f"  Profile links extracted: {link_stats['links_filtered']}")
                print(f"  Avg links per page: {link_stats['avg_links_per_page']}")
                print()

            # Email deobfuscator stats
            deobfuscator = get_email_deobfuscator()
            deobf_stats = deobfuscator.get_stats()
            if deobf_stats['total_deobfuscated'] > 0:
                print("Email De-obfuscation (Multi-Tier Phase 5):")
                print(f"  Total emails deobfuscated: {deobf_stats['total_deobfuscated']}")
                print(f"  Cloudflare decoded: {deobf_stats['cloudflare_decoded']}")
                print(f"  Text patterns decoded: {deobf_stats['text_pattern_decoded']}")
                print(f"  JavaScript extracted: {deobf_stats['javascript_extracted']}")
                print(f"  Noscript extracted: {deobf_stats['noscript_extracted']}")
                print()
        except Exception as e:
            logger.debug(f"Multi-tier stats not available: {e}")
            pass  # Multi-tier stats not available

        # Final summary
        print("=" * 70)
        print("EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Targets saved to: {targets_file}")
        if not contacts.empty:
            print(f"Contacts (CSV) saved to: {contacts_file}")
            if 'excel_path' in locals() and success:
                print(f"Contacts (Excel) saved to: {excel_path}")

            if existing_db_path:
                print()
                print("Database Comparison Results:")
                print(f"  New contacts: {len(new_contacts_df)}")
                if duplicates_df is not None:
                    print(f"  Duplicates: {len(duplicates_df)}")
                if updates_df is not None:
                    print(f"  Updates: {len(updates_df)}")
        print()
        print("Next Steps:")
        print("  - Review the Excel workbook with all sheets")
        print("  - Check Statistics Summary sheet for detailed metrics")
        print("  - Review Scraping Log for success/failure breakdown")
        if not contacts.empty and len(contacts[contacts['confidence_score'] < 50]) > 0:
            print("  - Review 'Needs Review' sheet for low-confidence contacts")
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
