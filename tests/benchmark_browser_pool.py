"""
Performance benchmark: Browser pool vs thread pool (Sprint 2.2).

Compares the two async approaches:
1. Thread pool executor (USE_BROWSER_POOL=False) - legacy mode
2. Browser pool (USE_BROWSER_POOL=True) - new native async mode

Target: 1.2x-1.3x speedup (20-30% faster)
Expected: Save 10-15s per institution by eliminating browser launch overhead
"""

import asyncio
import time
import os
import sys
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.contact_extractor import scrape_multiple_institutions_async
import config.settings as settings


async def benchmark():
    """Compare thread pool vs browser pool on 5 test institutions."""

    print("=" * 70)
    print("BROWSER POOL PERFORMANCE BENCHMARK")
    print("=" * 70)
    print("\nThis benchmark tests performance improvement from browser pooling.")
    print("Expected result: 1.2x-1.3x speedup (20-30% faster)")
    print("\n" + "=" * 70)

    # Test institutions (5 California law schools for consistency)
    institutions = pd.DataFrame([
        {'name': 'Stanford Law School', 'url': 'https://law.stanford.edu', 'type': 'Law School', 'state': 'CA'},
        {'name': 'UC Berkeley School of Law', 'url': 'https://www.law.berkeley.edu', 'type': 'Law School', 'state': 'CA'},
        {'name': 'UCLA School of Law', 'url': 'https://law.ucla.edu', 'type': 'Law School', 'state': 'CA'},
        {'name': 'USC Gould School of Law', 'url': 'https://gould.usc.edu', 'type': 'Law School', 'state': 'CA'},
        {'name': 'UC Irvine School of Law', 'url': 'https://www.law.uci.edu', 'type': 'Law School', 'state': 'CA'},
    ])

    print(f"\nTest dataset: {len(institutions)} institutions")
    print("Parallelism: 6 concurrent workers")
    print("\n" + "=" * 70)

    # =========================================================================
    # Benchmark 1: Thread Pool Executor (Legacy Mode)
    # =========================================================================

    print("\n### BENCHMARK 1: Thread Pool Executor (Legacy Mode) ###\n")
    print("Mode: USE_BROWSER_POOL=False")
    print("Method: run_in_executor() with sync functions")
    print("Expected: Slower due to browser launch overhead")
    print("\nStarting...\n")

    settings.USE_BROWSER_POOL = False
    start1 = time.time()

    try:
        result1 = await scrape_multiple_institutions_async(
            institutions,
            max_parallel=6
        )
        time1 = time.time() - start1

        print(f"\n✓ Benchmark 1 Complete")
        print(f"  Time: {time1:.1f}s")
        print(f"  Contacts: {len(result1)}")
        print(f"  Success rate: {len(result1) / len(institutions) * 100:.0f}%")
        print(f"  Avg time per institution: {time1 / len(institutions):.1f}s")

    except Exception as e:
        print(f"\n✗ Benchmark 1 Failed: {e}")
        time1 = None
        result1 = pd.DataFrame()

    # =========================================================================
    # Benchmark 2: Browser Pool (Native Async Mode)
    # =========================================================================

    print("\n" + "=" * 70)
    print("\n### BENCHMARK 2: Browser Pool (Native Async Mode) ###\n")
    print("Mode: USE_BROWSER_POOL=True")
    print("Method: Native async with persistent browsers")
    print("Expected: Faster due to browser reuse")
    print("\nStarting...\n")

    settings.USE_BROWSER_POOL = True
    start2 = time.time()

    try:
        result2 = await scrape_multiple_institutions_async(
            institutions,
            max_parallel=6
        )
        time2 = time.time() - start2

        print(f"\n✓ Benchmark 2 Complete")
        print(f"  Time: {time2:.1f}s")
        print(f"  Contacts: {len(result2)}")
        print(f"  Success rate: {len(result2) / len(institutions) * 100:.0f}%")
        print(f"  Avg time per institution: {time2 / len(institutions):.1f}s")

    except Exception as e:
        print(f"\n✗ Benchmark 2 Failed: {e}")
        time2 = None
        result2 = pd.DataFrame()

    # =========================================================================
    # Results Analysis
    # =========================================================================

    print("\n" + "=" * 70)
    print("\n### RESULTS SUMMARY ###\n")

    if time1 and time2:
        speedup = time1 / time2
        time_saved = time1 - time2
        percent_faster = (1 - time2 / time1) * 100

        print(f"Thread Pool:   {time1:.1f}s ({len(result1)} contacts)")
        print(f"Browser Pool:  {time2:.1f}s ({len(result2)} contacts)")
        print(f"\nSpeedup:       {speedup:.2f}x")
        print(f"Time Saved:    {time_saved:.1f}s ({percent_faster:.1f}% faster)")
        print(f"Per Institution: {time_saved / len(institutions):.1f}s saved")

        print("\n" + "-" * 70)
        print("\nTarget: 1.2x-1.3x speedup (20-30% improvement)")

        if speedup >= 1.2:
            print(f"Status: ✓ PASS (achieved {speedup:.2f}x speedup)")
        else:
            print(f"Status: ✗ FAIL (only {speedup:.2f}x speedup, target is 1.2x)")

        print("\n" + "-" * 70)
        print("\n### PROJECTIONS FOR FULL DATASET ###\n")

        total_institutions = 396
        projected_thread_pool = time1 / len(institutions) * total_institutions / 3600
        projected_browser_pool = time2 / len(institutions) * total_institutions / 3600
        projected_savings = projected_thread_pool - projected_browser_pool

        print(f"Total institutions: {total_institutions}")
        print(f"Thread Pool:        {projected_thread_pool:.1f} hours")
        print(f"Browser Pool:       {projected_browser_pool:.1f} hours")
        print(f"Time Savings:       {projected_savings:.1f} hours ({projected_savings * 60:.0f} minutes)")

    else:
        print("✗ One or both benchmarks failed - cannot compare")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    """Run benchmark directly with python benchmark_browser_pool.py"""
    asyncio.run(benchmark())
