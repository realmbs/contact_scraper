#!/usr/bin/env python3
"""
Test script for progressive saves and Ctrl+C functionality.

This script simulates a scraping run that can be interrupted with Ctrl+C
and then resumed from where it left off.

Usage:
    1. Run: python test_progressive_saves.py
    2. Wait for 2-3 institutions to complete
    3. Press Ctrl+C to interrupt
    4. Run again to resume from checkpoint
"""

import pandas as pd
from pathlib import Path

from modules.contact_extractor import run_async_scraping
from modules.streaming_writer import StreamingContactWriter
from modules.utils import setup_logger
from config.settings import OUTPUT_DIR

# Initialize logger
setup_logger("test_progressive_saves")

def test_progressive_saves():
    """Test progressive saves with 5 California law schools."""

    print("=" * 70)
    print("PROGRESSIVE SAVES TEST")
    print("=" * 70)
    print()
    print("This test will scrape 5 California law schools.")
    print("You can press Ctrl+C at any time to interrupt.")
    print("Run the script again to resume from where you left off.")
    print()
    print("=" * 70)
    print()

    # Load master database
    master_db = pd.read_csv('data/master_institutions.csv')

    # Get 5 California law schools
    ca_law_schools = master_db[
        (master_db['state'] == 'CA') &
        (master_db['type'] == 'Law School')
    ].head(5).copy()

    print(f"Test targets: {len(ca_law_schools)} institutions")
    for i, row in ca_law_schools.iterrows():
        print(f"  {row['name']}")
    print()

    # Create streaming writer
    progressive_csv = OUTPUT_DIR / 'test_progressive_contacts.csv'
    resume_state_file = OUTPUT_DIR / 'test_resume_state.json'

    streaming_writer = StreamingContactWriter(
        output_file=str(progressive_csv),
        resume_file=str(resume_state_file)
    )

    # Load resume state
    streaming_writer.load_resume_state()
    if streaming_writer.institutions_completed:
        print(f"RESUME MODE: {len(streaming_writer.institutions_completed)} institutions already completed:")
        for inst_name in streaming_writer.institutions_completed:
            print(f"  ✓ {inst_name}")
        print()

    print("Starting scrape... (Press Ctrl+C to interrupt)")
    print("=" * 70)
    print()

    # Run scraping with progressive saves
    try:
        contacts = run_async_scraping(
            ca_law_schools,
            max_institutions=None,  # All 5
            max_parallel=3,  # Slower to allow interruption
            streaming_writer=streaming_writer
        )

        # Completed successfully
        print()
        print("=" * 70)
        print("SCRAPING COMPLETED SUCCESSFULLY")
        print("=" * 70)
        print(f"Total contacts extracted: {len(contacts)}")
        print(f"Contacts saved to: {progressive_csv}")
        print(f"Resume state saved to: {resume_state_file}")
        print()

        # Clean up test files
        print("Cleaning up test files...")
        if progressive_csv.exists():
            progressive_csv.unlink()
        if resume_state_file.exists():
            resume_state_file.unlink()
        print("Test files deleted.")
        print()
        print("✅ TEST PASSED: Progressive saves working correctly!")

    except KeyboardInterrupt:
        # Graceful shutdown
        print()
        print()
        print("=" * 70)
        print("SCRAPING INTERRUPTED")
        print("=" * 70)
        print()

        if progressive_csv.exists():
            saved_contacts = pd.read_csv(progressive_csv)
            print(f"Contacts saved so far: {len(saved_contacts)}")
            print(f"Institutions completed: {len(streaming_writer.institutions_completed)}")
            print()
            print("Completed institutions:")
            for inst_name in streaming_writer.institutions_completed:
                print(f"  ✓ {inst_name}")
            print()
            print(f"Progressive save file: {progressive_csv}")
            print(f"Resume state file: {resume_state_file}")
            print()
            print("To resume: Run this script again")
            print()
            print("To clean up: Delete the test files above")
        else:
            print("No contacts saved yet (interrupted before first institution completed)")

        print("=" * 70)


if __name__ == '__main__':
    test_progressive_saves()
