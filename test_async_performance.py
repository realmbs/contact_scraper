"""
Test Async Performance - Sprint 2.1

Compares serial vs async scraping performance to measure speedup.
"""

import time
import pandas as pd
from modules.target_discovery import get_all_targets
from modules.contact_extractor import scrape_multiple_institutions, run_async_scraping
from modules.utils import setup_logger

logger = setup_logger("async_test")

def test_async_performance(num_institutions: int = 12):
    """
    Test async scraping performance vs serial.

    Args:
        num_institutions: Number of institutions to test (default: 12 for 2x6 batches)
    """
    print("\n" + "=" * 80)
    print(f"ASYNC PERFORMANCE TEST - {num_institutions} institutions")
    print("=" * 80 + "\n")

    # Get test institutions
    logger.info("Fetching test institutions...")
    institutions = get_all_targets(states=['CA'], program_type='paralegal')

    if len(institutions) < num_institutions:
        logger.warning(f"Only {len(institutions)} institutions available, using all")
        num_institutions = len(institutions)
    else:
        institutions = institutions.head(num_institutions)

    logger.info(f"Testing with {num_institutions} institutions from California paralegal programs\n")

    # Test 1: Serial scraping (baseline)
    print("\n" + "=" * 80)
    print("TEST 1: SERIAL SCRAPING (BASELINE)")
    print("=" * 80)

    start_serial = time.time()
    serial_results = scrape_multiple_institutions(institutions, max_institutions=num_institutions)
    serial_time = time.time() - start_serial

    logger.info(f"\nSerial scraping completed:")
    logger.info(f"  Time: {serial_time:.1f} seconds")
    logger.info(f"  Contacts extracted: {len(serial_results)}")
    logger.info(f"  Average per institution: {serial_time / num_institutions:.1f}s")

    # Test 2: Async scraping (6x parallelization)
    print("\n" + "=" * 80)
    print("TEST 2: ASYNC SCRAPING (6x PARALLEL WORKERS)")
    print("=" * 80)

    start_async = time.time()
    async_results = run_async_scraping(institutions, max_institutions=num_institutions, max_parallel=6)
    async_time = time.time() - start_async

    logger.info(f"\nAsync scraping completed:")
    logger.info(f"  Time: {async_time:.1f} seconds")
    logger.info(f"  Contacts extracted: {len(async_results)}")
    logger.info(f"  Average per institution: {async_time / num_institutions:.1f}s")

    # Calculate speedup
    speedup = serial_time / async_time if async_time > 0 else 0

    print("\n" + "=" * 80)
    print("PERFORMANCE COMPARISON")
    print("=" * 80)

    print(f"\nSerial (baseline):   {serial_time:.1f}s for {num_institutions} institutions")
    print(f"Async (6x parallel): {async_time:.1f}s for {num_institutions} institutions")
    print(f"\nSpeedup: {speedup:.2f}x")
    print(f"Time saved: {serial_time - async_time:.1f}s ({(serial_time - async_time) / serial_time * 100:.1f}%)")

    # Projected performance for 396 institutions
    projected_serial = (serial_time / num_institutions) * 396
    projected_async = (async_time / num_institutions) * 396

    print(f"\n" + "=" * 80)
    print("PROJECTED PERFORMANCE FOR FULL DATABASE (396 institutions)")
    print("=" * 80)

    print(f"\nSerial (projected):   {projected_serial / 60:.1f} minutes ({projected_serial / 3600:.1f} hours)")
    print(f"Async (projected):    {projected_async / 60:.1f} minutes ({projected_async / 3600:.1f} hours)")
    print(f"Time savings:         {(projected_serial - projected_async) / 60:.1f} minutes")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80 + "\n")

    return {
        'serial_time': serial_time,
        'async_time': async_time,
        'speedup': speedup,
        'serial_contacts': len(serial_results),
        'async_contacts': len(async_results),
    }


if __name__ == '__main__':
    import sys

    # Get number of institutions from command line or use default
    num_institutions = int(sys.argv[1]) if len(sys.argv) > 1 else 12

    results = test_async_performance(num_institutions)

    print("\nResults dictionary:")
    for key, value in results.items():
        print(f"  {key}: {value}")
