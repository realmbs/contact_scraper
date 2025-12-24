"""
Deduplication Module for Contact Scraper
Removes duplicate contacts and compares with existing databases.

Deduplication Strategy (Hierarchical):
    1. Email match (exact) - Primary identifier
    2. Name + Institution match - Fallback for contacts without emails

Merge Strategy:
    - Merge all fields from both records
    - Prefer newest non-empty values
    - Recalculate confidence score based on merged data

Functions:
    - deduplicate_contacts: Main deduplication function (internal)
    - deduplicate_by_email: Email-based matching
    - deduplicate_by_name_institution: Name+institution fallback
    - load_existing_database: Load CSV/Excel existing contacts
    - compare_with_existing: Classify new/duplicate/update
    - merge_contact_records: Smart field merging with confidence recalc
"""

from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import logging
from pathlib import Path
import re

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """
    Normalize name for comparison (lowercase, remove extra whitespace).

    Args:
        name: Name string to normalize

    Returns:
        Normalized name string
    """
    if pd.isna(name):
        return ""
    return re.sub(r'\s+', ' ', str(name).strip().lower())


def normalize_email(email: str) -> str:
    """
    Normalize email for comparison (lowercase, strip whitespace).

    Args:
        email: Email string to normalize

    Returns:
        Normalized email string
    """
    if pd.isna(email):
        return ""
    return str(email).strip().lower()


def deduplicate_by_email(contacts_df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove duplicates based on email address (exact match).

    Args:
        contacts_df: DataFrame with contacts

    Returns:
        DataFrame with email duplicates removed (keeps first occurrence)
    """
    if contacts_df.empty or 'email' not in contacts_df.columns:
        return contacts_df

    initial_count = len(contacts_df)

    # Filter to contacts with email
    with_email = contacts_df[contacts_df['email'].notna()].copy()
    without_email = contacts_df[contacts_df['email'].isna()].copy()

    if with_email.empty:
        logger.info("No contacts with emails to deduplicate")
        return contacts_df

    # Normalize emails for comparison
    with_email['_normalized_email'] = with_email['email'].apply(normalize_email)

    # Remove duplicates by normalized email (keep first)
    deduplicated = with_email.drop_duplicates(subset=['_normalized_email'], keep='first')
    deduplicated = deduplicated.drop(columns=['_normalized_email'])

    # Combine with contacts without emails
    result = pd.concat([deduplicated, without_email], ignore_index=True)

    duplicates_removed = initial_count - len(result)
    logger.info(f"Email deduplication: removed {duplicates_removed} duplicates (by email)")

    return result


def deduplicate_by_name_institution(contacts_df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove duplicates based on name + institution match.
    Only applies to contacts without emails (already deduplicated by email).

    Args:
        contacts_df: DataFrame with contacts

    Returns:
        DataFrame with name+institution duplicates removed
    """
    if contacts_df.empty:
        return contacts_df

    required_cols = ['full_name', 'institution_name']
    if not all(col in contacts_df.columns for col in required_cols):
        logger.warning(f"Missing columns for name+institution deduplication: {required_cols}")
        return contacts_df

    initial_count = len(contacts_df)

    # Filter to contacts without email (already deduplicated by email)
    without_email = contacts_df[contacts_df['email'].isna()].copy()
    with_email = contacts_df[contacts_df['email'].notna()].copy()

    if without_email.empty:
        logger.info("No contacts without emails to deduplicate by name+institution")
        return contacts_df

    # Normalize names and institutions
    without_email['_normalized_name'] = without_email['full_name'].apply(normalize_name)
    without_email['_normalized_institution'] = without_email['institution_name'].apply(normalize_name)

    # Remove duplicates by name+institution (keep first)
    deduplicated = without_email.drop_duplicates(
        subset=['_normalized_name', '_normalized_institution'],
        keep='first'
    )
    deduplicated = deduplicated.drop(columns=['_normalized_name', '_normalized_institution'])

    # Combine with contacts that have emails
    result = pd.concat([with_email, deduplicated], ignore_index=True)

    duplicates_removed = initial_count - len(result)
    logger.info(f"Name+institution deduplication: removed {duplicates_removed} duplicates")

    return result


def deduplicate_contacts(contacts_df: pd.DataFrame) -> pd.DataFrame:
    """
    Main deduplication function using hierarchical strategy.

    Strategy:
        1. Deduplicate by email (exact match) - primary identifier
        2. Deduplicate by name+institution - fallback for contacts without emails

    Args:
        contacts_df: DataFrame with contacts to deduplicate

    Returns:
        DataFrame with duplicates removed
    """
    if contacts_df.empty:
        logger.warning("Empty contacts DataFrame provided for deduplication")
        return contacts_df

    initial_count = len(contacts_df)
    logger.info(f"Starting deduplication: {initial_count} contacts")

    # Step 1: Deduplicate by email
    deduplicated = deduplicate_by_email(contacts_df)

    # Step 2: Deduplicate by name+institution (for contacts without emails)
    deduplicated = deduplicate_by_name_institution(deduplicated)

    final_count = len(deduplicated)
    total_removed = initial_count - final_count
    removal_pct = round((total_removed / initial_count) * 100, 1) if initial_count > 0 else 0.0

    logger.info(f"Deduplication complete: {total_removed} duplicates removed ({removal_pct}%), {final_count} unique contacts remain")

    return deduplicated


def load_existing_database(file_path: str) -> Optional[pd.DataFrame]:
    """
    Load existing contacts database from CSV or Excel file.

    Args:
        file_path: Path to existing contacts file (.csv or .xlsx)

    Returns:
        DataFrame with existing contacts, or None if load fails
    """
    path = Path(file_path)

    if not path.exists():
        logger.error(f"Existing database file not found: {file_path}")
        return None

    try:
        if path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path)
            logger.info(f"Loaded existing database from CSV: {len(df)} contacts")
        elif path.suffix.lower() in ['.xlsx', '.xls']:
            # Try to load from "All Contacts" sheet first, fall back to first sheet
            try:
                df = pd.read_excel(file_path, sheet_name='All Contacts')
                logger.info(f"Loaded existing database from Excel (All Contacts sheet): {len(df)} contacts")
            except ValueError:
                df = pd.read_excel(file_path, sheet_name=0)
                logger.info(f"Loaded existing database from Excel (first sheet): {len(df)} contacts")
        else:
            logger.error(f"Unsupported file format: {path.suffix}. Use .csv or .xlsx")
            return None

        return df

    except Exception as e:
        logger.error(f"Failed to load existing database: {e}")
        return None


def find_matching_contact(
    new_contact: pd.Series,
    existing_df: pd.DataFrame
) -> Optional[pd.Series]:
    """
    Find matching contact in existing database using hierarchical strategy.

    Args:
        new_contact: Series representing new contact
        existing_df: DataFrame with existing contacts

    Returns:
        Matching contact Series, or None if no match found
    """
    if existing_df.empty:
        return None

    # Strategy 1: Match by email (if email exists)
    if pd.notna(new_contact.get('email')) and 'email' in existing_df.columns:
        normalized_email = normalize_email(new_contact['email'])
        matches = existing_df[existing_df['email'].apply(normalize_email) == normalized_email]

        if not matches.empty:
            return matches.iloc[0]  # Return first match

    # Strategy 2: Match by name + institution (fallback)
    if all(col in existing_df.columns for col in ['full_name', 'institution_name']):
        if pd.notna(new_contact.get('full_name')) and pd.notna(new_contact.get('institution_name')):
            normalized_name = normalize_name(new_contact['full_name'])
            normalized_inst = normalize_name(new_contact['institution_name'])

            matches = existing_df[
                (existing_df['full_name'].apply(normalize_name) == normalized_name) &
                (existing_df['institution_name'].apply(normalize_name) == normalized_inst)
            ]

            if not matches.empty:
                return matches.iloc[0]  # Return first match

    return None


def merge_contact_records(
    existing_contact: pd.Series,
    new_contact: pd.Series
) -> pd.Series:
    """
    Merge two contact records with smart field merging.

    Strategy:
        - Prefer newest non-empty values for most fields
        - Keep higher confidence score
        - Preserve validation data if newer is better
        - Add merge metadata

    Args:
        existing_contact: Series with existing contact data
        new_contact: Series with new contact data

    Returns:
        Merged contact Series
    """
    merged = existing_contact.copy()

    # Fields to always update from new contact (prefer newest)
    always_update = [
        'title', 'matched_role', 'title_match_score',
        'source_url', 'extraction_method', 'extracted_at'
    ]

    # Fields to update only if new value is non-empty and existing is empty
    update_if_empty = [
        'first_name', 'last_name', 'full_name',
        'email', 'phone', 'institution_url', 'state', 'program_type'
    ]

    # Email validation fields - prefer newest if validation is better
    email_validation_fields = [
        'email_source', 'email_status', 'email_score',
        'email_is_catchall', 'email_is_disposable', 'email_validation_service'
    ]

    # Update always-update fields
    for field in always_update:
        if field in new_contact.index and pd.notna(new_contact[field]):
            merged[field] = new_contact[field]

    # Update if empty fields
    for field in update_if_empty:
        if field in new_contact.index and pd.notna(new_contact[field]) and new_contact[field] != '':
            existing_value = existing_contact.get(field)
            # Consider both NA and empty string as "empty"
            if pd.isna(existing_value) or existing_value == '':
                merged[field] = new_contact[field]

    # Update email validation fields if new validation is better
    if 'email_status' in new_contact.index and pd.notna(new_contact['email_status']):
        existing_status = existing_contact.get('email_status', 'unknown')
        new_status = new_contact['email_status']

        # Quality ranking: valid > catch-all > unknown > invalid
        status_quality = {'valid': 4, 'catch-all': 3, 'unknown': 2, 'invalid': 1, 'no_email': 0}
        existing_quality = status_quality.get(existing_status, 0)
        new_quality = status_quality.get(new_status, 0)

        if new_quality >= existing_quality:
            for field in email_validation_fields:
                if field in new_contact.index:
                    merged[field] = new_contact[field]

    # Recalculate confidence score based on merged data
    # Start with base score from new contact (most recent scrape)
    base_score = new_contact.get('confidence_score', existing_contact.get('confidence_score', 50))

    # Adjust based on email validation
    email_status = merged.get('email_status', 'unknown')
    if email_status == 'valid':
        base_score += 10  # Bonus for valid email
    elif email_status == 'catch-all':
        base_score -= 5  # Penalty for catch-all

    # Adjust based on data completeness
    if pd.notna(merged.get('phone')):
        base_score += 5  # Bonus for having phone

    # Cap at 100
    merged['confidence_score'] = min(100, base_score)

    # Add merge metadata
    merged['last_updated'] = new_contact.get('extracted_at', pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'))
    merged['record_source'] = 'merged'

    return merged


def compare_with_existing(
    new_contacts_df: pd.DataFrame,
    existing_contacts_df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Compare new contacts with existing database and classify them.

    Args:
        new_contacts_df: DataFrame with newly scraped contacts
        existing_contacts_df: DataFrame with existing contacts database

    Returns:
        Tuple of (new_contacts, duplicates, updates) DataFrames
            - new_contacts: Contacts not in existing database
            - duplicates: Contacts already in database (no changes)
            - updates: Contacts with updated information (merged records)
    """
    if new_contacts_df.empty:
        logger.warning("No new contacts to compare")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    if existing_contacts_df is None or existing_contacts_df.empty:
        logger.info("No existing database provided - all contacts are new")
        return new_contacts_df.copy(), pd.DataFrame(), pd.DataFrame()

    logger.info(f"Comparing {len(new_contacts_df)} new contacts with {len(existing_contacts_df)} existing contacts")

    new_list = []
    duplicate_list = []
    update_list = []

    for idx, new_contact in new_contacts_df.iterrows():
        matching_contact = find_matching_contact(new_contact, existing_contacts_df)

        if matching_contact is None:
            # No match found - this is a new contact
            new_list.append(new_contact)
        else:
            # Match found - check if it's a duplicate or update
            # Compare key fields to determine if there are meaningful changes
            has_changes = False

            # Check if email changed
            if pd.notna(new_contact.get('email')) and new_contact['email'] != matching_contact.get('email'):
                has_changes = True

            # Check if title changed
            if pd.notna(new_contact.get('title')) and new_contact['title'] != matching_contact.get('title'):
                has_changes = True

            # Check if phone changed
            if pd.notna(new_contact.get('phone')) and new_contact['phone'] != matching_contact.get('phone'):
                has_changes = True

            # Check if email validation improved
            if pd.notna(new_contact.get('email_status')):
                existing_status = matching_contact.get('email_status', 'unknown')
                new_status = new_contact['email_status']
                status_quality = {'valid': 4, 'catch-all': 3, 'unknown': 2, 'invalid': 1, 'no_email': 0}
                if status_quality.get(new_status, 0) > status_quality.get(existing_status, 0):
                    has_changes = True

            if has_changes:
                # This is an update - merge the records
                merged_contact = merge_contact_records(matching_contact, new_contact)
                update_list.append(merged_contact)
            else:
                # This is a duplicate - no meaningful changes
                duplicate_list.append(new_contact)

    # Convert lists to DataFrames
    new_df = pd.DataFrame(new_list) if new_list else pd.DataFrame()
    duplicates_df = pd.DataFrame(duplicate_list) if duplicate_list else pd.DataFrame()
    updates_df = pd.DataFrame(update_list) if update_list else pd.DataFrame()

    logger.info(f"Classification complete: {len(new_df)} new, {len(duplicates_df)} duplicates, {len(updates_df)} updates")

    return new_df, duplicates_df, updates_df
