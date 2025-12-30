#!/usr/bin/env python3
"""
Multi-Tier Extraction Test Script

Tests the new multi-tier extraction system on previously failed law schools.
Measures improvement in contact extraction success rate.

Target sites (previously returned 0 contacts):
- UC Irvine School of Law
- UC Berkeley School of Law (Faculty)
- American University Washington College of Law
- Capital University Law School
- UC Davis School of Law

Author: Claude Code
Date: 2025-12-29
"""

import sys
import pandas as pd
from loguru import logger
from modules.utils import setup_logger
from modules.contact_extractor import scrape_institution_contacts

# Setup logging
setup_logger("multi_tier_test")

# Test cases: Previously failed sites
TEST_CASES = [
    {
        'name': 'University of California, Irvine School of Law',
        'url': 'https://www.law.uci.edu/',
        'state': 'CA',
        'type': 'Law School',
        'previous_result': 0,  # 0 contacts in benchmark
        'failure_reason': 'Found student directories and portals instead of faculty pages'
    },
    {
        'name': 'University of California, Berkeley School of Law',
        'url': 'https://www.law.berkeley.edu/',
        'state': 'CA',
        'type': 'Law School',
        'previous_result': 1,  # Only 1 contact in benchmark
        'failure_reason': 'Faculty listing page, emails hidden on individual profile pages'
    },
    {
        'name': 'American University Washington College of Law',
        'url': 'https://www.wcl.american.edu/',
        'state': 'DC',
        'type': 'Law School',
        'previous_result': 0,
        'failure_reason': 'JavaScript-heavy site with multi-level navigation'
    },
    {
        'name': 'Capital University Law School',
        'url': 'https://www.law.capital.edu/',
        'state': 'OH',
        'type': 'Law School',
        'previous_result': 0,
        'failure_reason': 'Contact information not visible on directory pages'
    },
    {
        'name': 'University of California, Davis School of Law',
        'url': 'https://law.ucdavis.edu/',
        'state': 'CA',
        'type': 'Law School',
        'previous_result': 0,
        'failure_reason': 'Multi-level navigation, emails on profile pages only'
    },
]


def run_targeted_test():
    """Run multi-tier extraction test on previously failed sites."""

    print("=" * 80)
    print(" " * 20 + "MULTI-TIER EXTRACTION TEST")
    print(" " * 22 + "Testing Previously Failed Sites")
    print("=" * 80)
    print()

    results = []

    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\n{'=' * 80}")
        print(f"TEST {i}/{len(TEST_CASES)}: {test_case['name']}")
        print(f"{'=' * 80}")
        print(f"Previous result: {test_case['previous_result']} contacts")
        print(f"Failure reason: {test_case['failure_reason']}")
        print(f"URL: {test_case['url']}")
        print()

        try:
            # Run extraction
            logger.info(f"Starting extraction for {test_case['name']}...")

            contacts_df = scrape_institution_contacts(
                institution_name=test_case['name'],
                institution_url=test_case['url'],
                state=test_case['state'],
                program_type=test_case['type']
            )

            # Count results
            contacts_found = len(contacts_df)

            # Calculate improvement
            improvement = contacts_found - test_case['previous_result']
            improvement_pct = (improvement / max(test_case['previous_result'], 1)) * 100

            # Store result
            result = {
                'institution': test_case['name'],
                'previous_contacts': test_case['previous_result'],
                'new_contacts': contacts_found,
                'improvement': improvement,
                'improvement_pct': improvement_pct,
                'success': contacts_found > 0
            }
            results.append(result)

            # Display result
            print()
            print("=" * 80)
            print("RESULT:")
            print(f"  Previous: {test_case['previous_result']} contacts")
            print(f"  New:      {contacts_found} contacts")
            print(f"  Change:   {'+' if improvement >= 0 else ''}{improvement} contacts")
            if test_case['previous_result'] > 0:
                print(f"  Improvement: {improvement_pct:+.0f}%")
            else:
                print(f"  Improvement: {'SUCCESS!' if contacts_found > 0 else 'Still 0'}")
            print("=" * 80)

            # Show sample contacts
            if contacts_found > 0:
                print("\nSAMPLE CONTACTS EXTRACTED:")
                sample_size = min(5, contacts_found)
                for idx, row in contacts_df.head(sample_size).iterrows():
                    print(f"  - {row['full_name']}: {row['title'][:50]} ({row['email'][:30]})")
                if contacts_found > 5:
                    print(f"  ... and {contacts_found - 5} more")

        except Exception as e:
            logger.error(f"Test failed for {test_case['name']}: {e}")
            logger.exception(e)
            result = {
                'institution': test_case['name'],
                'previous_contacts': test_case['previous_result'],
                'new_contacts': 0,
                'improvement': 0,
                'improvement_pct': 0,
                'success': False,
                'error': str(e)
            }
            results.append(result)

    # Summary
    print("\n\n" + "=" * 80)
    print(" " * 25 + "TEST SUMMARY")
    print("=" * 80)
    print()

    results_df = pd.DataFrame(results)

    # Calculate statistics
    total_tests = len(results)
    successful_tests = results_df['success'].sum()
    success_rate = (successful_tests / total_tests) * 100

    total_previous = results_df['previous_contacts'].sum()
    total_new = results_df['new_contacts'].sum()
    total_improvement = total_new - total_previous

    avg_contacts_before = total_previous / total_tests
    avg_contacts_after = total_new / total_tests

    print(f"Tests run: {total_tests}")
    print(f"Successful extractions: {successful_tests}/{total_tests} ({success_rate:.0f}%)")
    print()
    print(f"Total contacts extracted:")
    print(f"  Before: {total_previous} contacts ({avg_contacts_before:.1f} avg)")
    print(f"  After:  {total_new} contacts ({avg_contacts_after:.1f} avg)")
    print(f"  Change: {'+' if total_improvement >= 0 else ''}{total_improvement} contacts")
    print()

    # Detailed breakdown
    print("DETAILED RESULTS:")
    print("-" * 80)
    for _, row in results_df.iterrows():
        print(f"{row['institution'][:45]:45} | {row['previous_contacts']:3d} → {row['new_contacts']:3d} | {'+' if row['improvement'] >= 0 else ''}{row['improvement']:3d}")
    print("-" * 80)

    # Assessment
    print()
    print("ASSESSMENT:")
    if success_rate >= 80:
        print("  ✅ EXCELLENT: Multi-tier extraction working as expected!")
    elif success_rate >= 60:
        print("  ✓ GOOD: Significant improvement, but room for optimization")
    elif success_rate >= 40:
        print("  ~ MODERATE: Some improvement, needs further work")
    else:
        print("  ✗ POOR: Multi-tier extraction needs debugging")

    print()
    print("=" * 80)

    return results_df


if __name__ == '__main__':
    results = run_targeted_test()
    print("\nTest complete!")
