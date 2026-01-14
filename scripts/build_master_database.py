"""
Master Institution Database Builder

Consolidates all institution sources into a single master database.
Sources:
- ABA Law Schools (197 institutions)
- AAfPE Paralegal Programs (199 institutions)

Total: 396 institutions

Author: Claude Code
Date: 2025-12-26
Sprint: 1.4
"""

import pandas as pd
from datetime import datetime
from pathlib import Path

from modules.target_discovery import get_aba_law_schools, get_paralegal_programs
from modules.utils import setup_logger

# Initialize logger
logger = setup_logger("master_database")

# Output directory
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def build_master_database(save_to_disk: bool = True) -> pd.DataFrame:
    """
    Build consolidated master institution database.

    Args:
        save_to_disk: Whether to save to CSV file

    Returns:
        DataFrame with all institutions
    """
    logger.info("=" * 80)
    logger.info("BUILDING MASTER INSTITUTION DATABASE")
    logger.info("=" * 80)

    # Fetch all law schools
    logger.info("\nStep 1: Fetching ABA Law Schools...")
    law_schools = get_aba_law_schools()
    logger.success(f"Retrieved {len(law_schools)} law schools")

    # Fetch all paralegal programs
    logger.info("\nStep 2: Fetching AAfPE Paralegal Programs...")
    paralegal_programs = get_paralegal_programs()
    logger.success(f"Retrieved {len(paralegal_programs)} paralegal programs")

    # Combine datasets
    logger.info("\nStep 3: Consolidating databases...")

    # Ensure both have same columns
    required_columns = ['name', 'state', 'city', 'url', 'type', 'accreditation_status']

    for col in required_columns:
        if col not in law_schools.columns:
            law_schools[col] = ''
        if col not in paralegal_programs.columns:
            paralegal_programs[col] = ''

    # Select only required columns
    law_schools = law_schools[required_columns]
    paralegal_programs = paralegal_programs[required_columns]

    # Concatenate
    master_df = pd.concat([law_schools, paralegal_programs], ignore_index=True)

    # Add metadata columns
    master_df['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    master_df['source'] = master_df['type'].apply(
        lambda x: 'ABA' if 'Law School' in x else 'AAfPE'
    )

    # Add unique ID
    master_df['institution_id'] = range(1, len(master_df) + 1)

    # Reorder columns
    column_order = [
        'institution_id',
        'name',
        'type',
        'state',
        'city',
        'url',
        'accreditation_status',
        'source',
        'last_updated'
    ]
    master_df = master_df[column_order]

    # Sort by type and name
    master_df = master_df.sort_values(['type', 'name']).reset_index(drop=True)

    # Update institution_id after sorting
    master_df['institution_id'] = range(1, len(master_df) + 1)

    logger.success(f"Consolidated {len(master_df)} total institutions")

    # Print statistics
    logger.info("\n" + "=" * 80)
    logger.info("MASTER DATABASE STATISTICS")
    logger.info("=" * 80)

    logger.info(f"\nTotal Institutions: {len(master_df)}")

    logger.info(f"\nBreakdown by Type:")
    for inst_type, count in master_df['type'].value_counts().items():
        logger.info(f"  {inst_type}: {count}")

    logger.info(f"\nBreakdown by Source:")
    for source, count in master_df['source'].value_counts().items():
        logger.info(f"  {source}: {count}")

    logger.info(f"\nInstitutions with State Data: {master_df['state'].notna().sum()} ({master_df['state'].notna().sum() / len(master_df) * 100:.1f}%)")
    logger.info(f"Institutions with City Data: {master_df['city'].notna().sum()} ({master_df['city'].notna().sum() / len(master_df) * 100:.1f}%)")
    logger.info(f"Institutions with URL: {master_df['url'].notna().sum()} ({master_df['url'].notna().sum() / len(master_df) * 100:.1f}%)")

    # Top 10 states
    states_with_data = master_df[master_df['state'] != '']
    if not states_with_data.empty:
        logger.info(f"\nTop 10 States by Institution Count:")
        top_states = states_with_data['state'].value_counts().head(10)
        for state, count in top_states.items():
            logger.info(f"  {state}: {count}")

    # Save to disk
    if save_to_disk:
        logger.info("\n" + "=" * 80)
        logger.info("SAVING TO DISK")
        logger.info("=" * 80)

        # Save master database
        master_file = DATA_DIR / "master_institutions.csv"
        master_df.to_csv(master_file, index=False)
        logger.success(f"Saved master database: {master_file} ({len(master_df)} rows)")

        # Save timestamped version
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        timestamped_file = DATA_DIR / f"master_institutions_{timestamp}.csv"
        master_df.to_csv(timestamped_file, index=False)
        logger.info(f"Saved timestamped version: {timestamped_file}")

        # Save by type
        law_file = DATA_DIR / "law_schools.csv"
        law_schools_only = master_df[master_df['source'] == 'ABA']
        law_schools_only.to_csv(law_file, index=False)
        logger.info(f"Saved law schools: {law_file} ({len(law_schools_only)} rows)")

        paralegal_file = DATA_DIR / "paralegal_programs.csv"
        paralegal_only = master_df[master_df['source'] == 'AAfPE']
        paralegal_only.to_csv(paralegal_file, index=False)
        logger.info(f"Saved paralegal programs: {paralegal_file} ({len(paralegal_only)} rows)")

    logger.info("\n" + "=" * 80)
    logger.info("MASTER DATABASE BUILD COMPLETE")
    logger.info("=" * 80)

    return master_df


def load_master_database() -> pd.DataFrame:
    """
    Load the master institution database from disk.

    Returns:
        DataFrame with all institutions, or empty DataFrame if not found
    """
    master_file = DATA_DIR / "master_institutions.csv"

    if not master_file.exists():
        logger.warning(f"Master database not found: {master_file}")
        logger.info("Run build_master_database() first to create it")
        return pd.DataFrame()

    try:
        df = pd.read_csv(master_file)
        logger.success(f"Loaded master database: {len(df)} institutions")
        return df
    except Exception as e:
        logger.error(f"Failed to load master database: {e}")
        return pd.DataFrame()


def get_institutions_by_state(state: str) -> pd.DataFrame:
    """
    Get all institutions in a specific state.

    Args:
        state: State name or abbreviation

    Returns:
        Filtered DataFrame
    """
    df = load_master_database()

    if df.empty:
        return df

    # Filter by state (case-insensitive)
    filtered = df[df['state'].str.lower() == state.lower()]

    logger.info(f"Found {len(filtered)} institutions in {state}")
    return filtered


def get_institutions_by_type(inst_type: str) -> pd.DataFrame:
    """
    Get all institutions of a specific type.

    Args:
        inst_type: 'law' or 'paralegal'

    Returns:
        Filtered DataFrame
    """
    df = load_master_database()

    if df.empty:
        return df

    # Filter by type
    if inst_type.lower() == 'law':
        filtered = df[df['source'] == 'ABA']
    elif inst_type.lower() == 'paralegal':
        filtered = df[df['source'] == 'AAfPE']
    else:
        logger.warning(f"Unknown type: {inst_type}. Use 'law' or 'paralegal'")
        return pd.DataFrame()

    logger.info(f"Found {len(filtered)} {inst_type} institutions")
    return filtered


# ============================================================================
# CLI Testing
# ============================================================================

if __name__ == '__main__':
    import sys

    print("\n" + "=" * 80)
    print("MASTER INSTITUTION DATABASE BUILDER")
    print("=" * 80 + "\n")

    # Build master database
    if len(sys.argv) > 1 and sys.argv[1] == '--no-save':
        master_df = build_master_database(save_to_disk=False)
    else:
        master_df = build_master_database(save_to_disk=True)

    # Show sample
    print("\nSample institutions (first 10):")
    print(master_df.head(10).to_string(index=False))

    print("\n" + "=" * 80)
    print("Build complete! Master database saved to data/master_institutions.csv")
    print("=" * 80)
