#!/usr/bin/env python3
"""
Performance Test: UC Berkeley School of Law

Tests Phase 6.1 + 6.2 optimizations on Berkeley to validate:
- Expected runtime: 6-7 minutes (vs previous 21 minutes)
- Expected contacts: ~24 contacts (accuracy preserved)
- Async profile link visiting (Phase 6.1)
- Async directory processing (Phase 6.2)

Author: Claude Code
Date: 2025-12-29
"""

import time
import sys
from loguru import logger
from modules.contact_extractor import scrape_institution_contacts

def test_berkeley_performance():
    """
    Performance test for UC Berkeley School of Law.

    Previous baseline (serial processing):
    - Runtime: 21 minutes
    - Contacts: 24 contacts
    - Bottlenecks: Serial profile links (15 min) + serial directories (4 min)

    Expected with Phase 6.1 + 6.2:
    - Runtime: 6-7 minutes (65-70% reduction)
    - Contacts: ~24 contacts (accuracy preserved)
    - Optimizations: Parallel profile links (3 workers) + parallel directories (3 workers)
    """

    logger.info("=" * 80)
    logger.info("PERFORMANCE TEST: UC Berkeley School of Law")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Optimizations Enabled:")
    logger.info("  - Phase 6.1: Async profile link visiting (3 workers)")
    logger.info("  - Phase 6.2: Async directory processing (3 workers)")
    logger.info("")
    logger.info("Expected Performance:")
    logger.info("  - Previous runtime: ~21 minutes (serial processing)")
    logger.info("  - Target runtime: 6-7 minutes (65-70% reduction)")
    logger.info("  - Expected contacts: ~24 contacts")
    logger.info("")
    logger.info("=" * 80)
    logger.info("")

    # Test institution
    institution_name = "University of California, Berkeley School of Law"
    institution_url = "https://www.law.berkeley.edu/"
    state = "CA"
    program_type = "Law School"

    # Start timer
    start_time = time.time()
    logger.info(f"[{time.strftime('%H:%M:%S')}] Starting extraction...")
    logger.info("")

    try:
        # Run extraction
        contacts_df = scrape_institution_contacts(
            institution_name=institution_name,
            institution_url=institution_url,
            state=state,
            program_type=program_type
        )

        # End timer
        end_time = time.time()
        elapsed_seconds = end_time - start_time
        elapsed_minutes = elapsed_seconds / 60

        # Results
        num_contacts = len(contacts_df)

        logger.info("")
        logger.info("=" * 80)
        logger.info("PERFORMANCE TEST RESULTS")
        logger.info("=" * 80)
        logger.info("")
        logger.info(f"Institution: {institution_name}")
        logger.info(f"Runtime: {elapsed_minutes:.2f} minutes ({elapsed_seconds:.1f} seconds)")
        logger.info(f"Contacts extracted: {num_contacts}")
        logger.info("")

        # Performance comparison
        previous_runtime = 21.0  # minutes (from previous test)
        previous_contacts = 24

        time_reduction = ((previous_runtime - elapsed_minutes) / previous_runtime) * 100
        speedup = previous_runtime / elapsed_minutes if elapsed_minutes > 0 else 0

        logger.info("Performance Comparison:")
        logger.info(f"  Previous runtime: {previous_runtime:.1f} minutes")
        logger.info(f"  New runtime: {elapsed_minutes:.2f} minutes")
        logger.info(f"  Time reduction: {time_reduction:.1f}%")
        logger.info(f"  Speedup: {speedup:.2f}x faster")
        logger.info("")

        # Accuracy validation
        contact_difference = num_contacts - previous_contacts
        contact_change_pct = (contact_difference / previous_contacts) * 100 if previous_contacts > 0 else 0

        logger.info("Accuracy Validation:")
        logger.info(f"  Previous contacts: {previous_contacts}")
        logger.info(f"  New contacts: {num_contacts}")
        logger.info(f"  Change: {contact_difference:+d} ({contact_change_pct:+.1f}%)")
        logger.info("")

        # Overall assessment
        target_runtime_min = 6.0
        target_runtime_max = 7.0
        target_contacts_min = 20
        target_contacts_max = 28

        runtime_ok = target_runtime_min <= elapsed_minutes <= target_runtime_max
        contacts_ok = target_contacts_min <= num_contacts <= target_contacts_max

        logger.info("Target Validation:")
        logger.info(f"  Target runtime: {target_runtime_min}-{target_runtime_max} minutes → {'✅ PASS' if runtime_ok else '❌ FAIL'}")
        logger.info(f"  Target contacts: {target_contacts_min}-{target_contacts_max} → {'✅ PASS' if contacts_ok else '❌ FAIL'}")
        logger.info("")

        if runtime_ok and contacts_ok:
            logger.success("=" * 80)
            logger.success("✅ PERFORMANCE TEST PASSED!")
            logger.success(f"Achieved {speedup:.2f}x speedup with {time_reduction:.1f}% time reduction")
            logger.success("=" * 80)
            return True
        elif contacts_ok and not runtime_ok:
            if elapsed_minutes < target_runtime_min:
                logger.success("=" * 80)
                logger.success("✅ PERFORMANCE TEST EXCEEDED EXPECTATIONS!")
                logger.success(f"Runtime {elapsed_minutes:.2f} min is faster than target {target_runtime_min}-{target_runtime_max} min")
                logger.success("=" * 80)
                return True
            else:
                logger.warning("=" * 80)
                logger.warning("⚠️  PERFORMANCE TEST SLOWER THAN EXPECTED")
                logger.warning(f"Runtime {elapsed_minutes:.2f} min exceeds target {target_runtime_max} min")
                logger.warning("Accuracy preserved, but additional optimization needed")
                logger.warning("=" * 80)
                return False
        else:
            logger.error("=" * 80)
            logger.error("❌ PERFORMANCE TEST FAILED")
            if not runtime_ok:
                logger.error(f"Runtime {elapsed_minutes:.2f} min outside target {target_runtime_min}-{target_runtime_max} min")
            if not contacts_ok:
                logger.error(f"Contacts {num_contacts} outside target {target_contacts_min}-{target_contacts_max}")
            logger.error("=" * 80)
            return False

    except Exception as e:
        end_time = time.time()
        elapsed_seconds = end_time - start_time
        elapsed_minutes = elapsed_seconds / 60

        logger.error("")
        logger.error("=" * 80)
        logger.error("❌ PERFORMANCE TEST ERROR")
        logger.error("=" * 80)
        logger.error(f"Error after {elapsed_minutes:.2f} minutes: {e}")
        logger.error("=" * 80)

        import traceback
        logger.error(traceback.format_exc())

        return False


if __name__ == "__main__":
    logger.info("Starting Berkeley Performance Test...")
    logger.info("")

    success = test_berkeley_performance()

    sys.exit(0 if success else 1)
