#!/usr/bin/env python3
"""
Performance Benchmarking Script - Sprint 4.1

Comprehensive benchmarking at multiple scales: 10, 50, 100, 396 institutions
Measures: runtime, memory, success rate, throughput, optimization effectiveness

Author: Claude Code
Date: 2025-12-28
"""

import os
import sys
import time
import psutil
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from loguru import logger
from modules.utils import setup_logger
from modules.target_discovery import get_all_targets
from modules.contact_extractor import run_async_scraping
from modules.fetch_router import get_fetch_router
from modules.domain_rate_limiter import get_domain_rate_limiter
from modules.timeout_manager import get_timeout_manager


def get_memory_usage_mb() -> float:
    """Get current memory usage in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def run_benchmark(
    scale: int,
    states: Optional[List[str]] = None,
    program_type: str = 'both',
    max_parallel: int = 6
) -> Dict:
    """
    Run a single benchmark test at specified scale.

    Args:
        scale: Number of institutions to test
        states: List of states to target (None = all)
        program_type: 'law', 'paralegal', or 'both'
        max_parallel: Number of parallel workers

    Returns:
        Dictionary with benchmark results
    """
    logger.info("=" * 80)
    logger.info(f"BENCHMARK: {scale} INSTITUTIONS")
    logger.info("=" * 80)

    # Record start metrics
    start_time = time.time()
    start_memory = get_memory_usage_mb()

    # Get targets
    logger.info(f"Discovering targets (states: {states or 'ALL'}, type: {program_type})...")
    targets = get_all_targets(states=states, program_type=program_type)

    if targets.empty:
        logger.error("No targets found")
        return None

    # Limit to benchmark scale
    if len(targets) > scale:
        targets = targets.head(scale)
        logger.info(f"Limited to {scale} institutions for benchmark")

    logger.info(f"Testing with {len(targets)} institutions")
    logger.info(f"  Law Schools: {len(targets[targets['type'] == 'Law School'])}")
    logger.info(f"  Paralegal Programs: {len(targets[targets['type'] == 'Paralegal Program'])}")

    # Run extraction
    logger.info(f"\nStarting extraction with {max_parallel}x parallel workers...")
    extraction_start = time.time()

    contacts = run_async_scraping(targets, max_institutions=scale, max_parallel=max_parallel)

    extraction_time = time.time() - extraction_start
    total_time = time.time() - start_time

    # Record end metrics
    end_memory = get_memory_usage_mb()
    peak_memory = end_memory  # Approximate (actual peak would need continuous monitoring)

    # Calculate success metrics
    total_institutions = len(targets)
    contacts_extracted = len(contacts)

    # Calculate success rate (institutions with > 0 contacts)
    if not contacts.empty:
        institutions_with_contacts = contacts['institution_name'].nunique()
        success_rate = (institutions_with_contacts / total_institutions) * 100
    else:
        institutions_with_contacts = 0
        success_rate = 0.0

    # Get optimization statistics
    router_stats = {}
    limiter_stats = {}
    timeout_stats = {}

    try:
        router = get_fetch_router()
        router_stats = router.get_stats_summary()
    except:
        pass

    try:
        limiter = get_domain_rate_limiter()
        limiter_stats = limiter.get_stats()
    except:
        pass

    try:
        timeout_mgr = get_timeout_manager()
        timeout_stats = timeout_mgr.get_stats()
    except:
        pass

    # Calculate throughput
    throughput_per_hour = (total_institutions / total_time) * 3600 if total_time > 0 else 0
    avg_time_per_institution = total_time / total_institutions if total_institutions > 0 else 0

    # Build results dictionary
    results = {
        # Scale
        'scale': scale,
        'institutions_tested': total_institutions,
        'states': ', '.join(states) if states else 'ALL',
        'program_type': program_type,

        # Performance
        'total_time_seconds': round(total_time, 2),
        'extraction_time_seconds': round(extraction_time, 2),
        'avg_time_per_institution': round(avg_time_per_institution, 2),
        'throughput_institutions_per_hour': round(throughput_per_hour, 1),

        # Memory
        'start_memory_mb': round(start_memory, 1),
        'end_memory_mb': round(end_memory, 1),
        'peak_memory_mb': round(peak_memory, 1),
        'memory_increase_mb': round(end_memory - start_memory, 1),

        # Success metrics
        'contacts_extracted': contacts_extracted,
        'institutions_with_contacts': institutions_with_contacts,
        'success_rate_percent': round(success_rate, 1),

        # Optimization stats
        'fetch_router_domains': router_stats.get('domains_tracked', 0),
        'fetch_router_static_pct': round(router_stats.get('static_rate', 0) * 100, 1),
        'fetch_router_playwright_pct': round(router_stats.get('playwright_rate', 0) * 100, 1),

        'rate_limiter_requests': limiter_stats.get('total_requests', 0),
        'rate_limiter_avg_delay': limiter_stats.get('avg_delay_per_request', 0),

        'timeout_manager_requests': timeout_stats.get('total_requests', 0),
        'timeout_manager_timeout_rate': timeout_stats.get('timeout_rate', 0),
        'timeout_manager_avg_timeout_ms': timeout_stats.get('avg_timeout_ms', 0),

        # Timestamp
        'timestamp': datetime.now().isoformat(),
    }

    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("BENCHMARK RESULTS")
    logger.info("=" * 80)
    logger.info(f"Scale: {scale} institutions")
    logger.info(f"Total Time: {format_duration(total_time)}")
    logger.info(f"Extraction Time: {format_duration(extraction_time)}")
    logger.info(f"Avg per Institution: {avg_time_per_institution:.1f}s")
    logger.info(f"Throughput: {throughput_per_hour:.1f} institutions/hour")
    logger.info("")
    logger.info(f"Memory: {start_memory:.1f}MB → {end_memory:.1f}MB (Δ {end_memory - start_memory:.1f}MB)")
    logger.info("")
    logger.info(f"Contacts Extracted: {contacts_extracted}")
    logger.info(f"Institutions with Contacts: {institutions_with_contacts}/{total_institutions}")
    logger.info(f"Success Rate: {success_rate:.1f}%")
    logger.info("")

    if router_stats:
        logger.info(f"Fetch Router: {router_stats.get('domains_tracked', 0)} domains tracked")
        logger.info(f"  Static: {router_stats.get('static_total', 0)} requests ({router_stats.get('static_rate', 0):.1%} success)")
        logger.info(f"  Playwright: {router_stats.get('playwright_total', 0)} requests ({router_stats.get('playwright_rate', 0):.1%} success)")
        logger.info("")

    if timeout_stats:
        logger.info(f"Timeout Manager: {timeout_stats.get('total_requests', 0)} requests")
        logger.info(f"  Timeout rate: {timeout_stats.get('timeout_rate', 0):.1f}%")
        logger.info(f"  Avg timeout: {timeout_stats.get('avg_timeout_ms', 0):.0f}ms")
        logger.info("")

    logger.info("=" * 80)

    return results


def run_full_benchmark_suite():
    """Run complete benchmark suite at multiple scales."""
    setup_logger("benchmark")

    print("=" * 80)
    print(" " * 20 + "PERFORMANCE BENCHMARK SUITE")
    print(" " * 25 + "Sprint 4.1")
    print("=" * 80)
    print()

    # Define benchmark configurations
    benchmarks = [
        # Small scale: Quick validation (CA law schools only)
        {
            'name': 'Small Scale (10 institutions)',
            'scale': 10,
            'states': ['CA', 'NY'],
            'program_type': 'law',
        },
        # Medium scale: Performance test (multi-state)
        {
            'name': 'Medium Scale (50 institutions)',
            'scale': 50,
            'states': ['CA', 'NY', 'TX', 'FL', 'IL'],
            'program_type': 'both',
        },
        # Large scale: Stress test
        {
            'name': 'Large Scale (100 institutions)',
            'scale': 100,
            'states': None,  # All states
            'program_type': 'both',
        },
    ]

    # Ask user which benchmarks to run
    print("Available benchmarks:")
    for i, bench in enumerate(benchmarks, 1):
        print(f"  {i}. {bench['name']}")
    print(f"  4. All benchmarks")
    print(f"  5. Full database (396 institutions) - WARNING: Takes ~5-6 hours")
    print()

    choice = input("Which benchmark(s) to run? [1-5]: ").strip()

    if choice == '4':
        # Run all defined benchmarks
        selected_benchmarks = benchmarks
    elif choice == '5':
        # Full database benchmark
        selected_benchmarks = [{
            'name': 'Full Database (396 institutions)',
            'scale': 396,
            'states': None,
            'program_type': 'both',
        }]
    elif choice in ['1', '2', '3']:
        # Single benchmark
        selected_benchmarks = [benchmarks[int(choice) - 1]]
    else:
        print("Invalid choice. Defaulting to Small Scale.")
        selected_benchmarks = [benchmarks[0]]

    # Confirm
    print("\n" + "=" * 80)
    print("BENCHMARK PLAN")
    print("=" * 80)
    for bench in selected_benchmarks:
        print(f"  • {bench['name']}")
    print("=" * 80)
    print()

    confirm = input("Proceed? [Y/n]: ").strip().lower()
    if confirm and confirm not in ['y', 'yes']:
        print("Benchmark cancelled.")
        return

    # Run benchmarks
    all_results = []

    for i, config in enumerate(selected_benchmarks, 1):
        print(f"\n\n{'=' * 80}")
        print(f"BENCHMARK {i}/{len(selected_benchmarks)}: {config['name']}")
        print(f"{'=' * 80}\n")

        try:
            results = run_benchmark(
                scale=config['scale'],
                states=config['states'],
                program_type=config['program_type'],
                max_parallel=6
            )

            if results:
                all_results.append(results)

                # Short pause between benchmarks
                if i < len(selected_benchmarks):
                    logger.info(f"\nPausing 10 seconds before next benchmark...\n")
                    time.sleep(10)

        except KeyboardInterrupt:
            logger.warning("\nBenchmark interrupted by user")
            break
        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            logger.exception(e)

    # Save results to CSV
    if all_results:
        results_df = pd.DataFrame(all_results)
        output_dir = Path('output/benchmarks')
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = output_dir / f'benchmark_results_{timestamp}.csv'

        results_df.to_csv(results_file, index=False)
        logger.success(f"\nBenchmark results saved to: {results_file}")

        # Print summary
        print("\n" + "=" * 80)
        print("BENCHMARK SUITE SUMMARY")
        print("=" * 80)
        print()
        print(results_df.to_string(index=False))
        print()
        print("=" * 80)

    print("\nBenchmark suite complete!")


if __name__ == '__main__':
    run_full_benchmark_suite()
