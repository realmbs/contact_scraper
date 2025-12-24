"""
Statistics Module for Contact Scraper
Calculates comprehensive statistics for scraped contacts and institutions.

Functions:
    - calculate_contact_statistics: Main orchestrator for all statistics
    - get_state_breakdown: Contact counts by state
    - get_program_type_breakdown: Law schools vs paralegal programs
    - get_email_quality_summary: Email validation metrics
    - get_confidence_distribution: Confidence score histogram
    - get_top_roles: Most common job titles
    - calculate_scraping_success_rate: Extraction success/failure rates
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from collections import Counter
import logging

logger = logging.getLogger(__name__)


def get_state_breakdown(contacts_df: pd.DataFrame) -> Dict[str, int]:
    """
    Calculate contact counts by state.

    Args:
        contacts_df: DataFrame with 'state' column

    Returns:
        Dictionary mapping state abbreviation to contact count
        Example: {'CA': 25, 'NY': 18, 'TX': 12}
    """
    if contacts_df.empty:
        return {}

    if 'state' not in contacts_df.columns:
        logger.warning("No 'state' column found in contacts DataFrame")
        return {}

    state_counts = contacts_df['state'].value_counts().to_dict()

    # Sort by count descending
    state_counts = dict(sorted(state_counts.items(), key=lambda x: x[1], reverse=True))

    logger.info(f"State breakdown calculated: {len(state_counts)} states")
    return state_counts


def get_program_type_breakdown(contacts_df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """
    Calculate contact counts by program type (Law School vs Paralegal Program).

    Args:
        contacts_df: DataFrame with 'program_type' column

    Returns:
        Dictionary with counts and percentages for each program type
        Example: {
            'Law School': {'count': 150, 'percentage': 35.7},
            'Paralegal Program': {'count': 270, 'percentage': 64.3}
        }
    """
    if contacts_df.empty:
        return {}

    if 'program_type' not in contacts_df.columns:
        logger.warning("No 'program_type' column found in contacts DataFrame")
        return {}

    total = len(contacts_df)
    program_counts = contacts_df['program_type'].value_counts().to_dict()

    result = {}
    for program_type, count in program_counts.items():
        result[program_type] = {
            'count': count,
            'percentage': round((count / total) * 100, 1)
        }

    logger.info(f"Program type breakdown: {len(result)} types")
    return result


def get_email_quality_summary(contacts_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate email validation and quality metrics.

    Args:
        contacts_df: DataFrame with email-related columns

    Returns:
        Dictionary with email quality statistics
        Example: {
            'total_contacts': 420,
            'with_email': 385,
            'email_coverage_pct': 91.7,
            'validated': 320,
            'validated_pct': 83.1,
            'valid_deliverable': 290,
            'valid_pct': 75.3,
            'catch_all': 30,
            'catch_all_pct': 7.8,
            'invalid': 15,
            'invalid_pct': 3.9,
            'unknown': 50,
            'unknown_pct': 13.0,
            'validation_services': {'neverbounce': 200, 'zerobounce': 120, 'hunter': 15}
        }
    """
    if contacts_df.empty:
        return {
            'total_contacts': 0,
            'with_email': 0,
            'email_coverage_pct': 0.0
        }

    total = len(contacts_df)

    # Email coverage
    with_email = contacts_df['email'].notna().sum() if 'email' in contacts_df.columns else 0
    email_coverage_pct = round((with_email / total) * 100, 1) if total > 0 else 0.0

    result = {
        'total_contacts': total,
        'with_email': int(with_email),
        'email_coverage_pct': email_coverage_pct
    }

    # Email validation metrics (if Phase 3 columns exist)
    if 'email_status' in contacts_df.columns:
        status_counts = contacts_df['email_status'].value_counts().to_dict()

        validated = sum(count for status, count in status_counts.items()
                       if status in ['valid', 'invalid', 'catch-all'])
        valid_deliverable = status_counts.get('valid', 0)
        catch_all = status_counts.get('catch-all', 0)
        invalid = status_counts.get('invalid', 0)
        unknown = status_counts.get('unknown', 0)

        result.update({
            'validated': int(validated),
            'validated_pct': round((validated / with_email) * 100, 1) if with_email > 0 else 0.0,
            'valid_deliverable': int(valid_deliverable),
            'valid_pct': round((valid_deliverable / with_email) * 100, 1) if with_email > 0 else 0.0,
            'catch_all': int(catch_all),
            'catch_all_pct': round((catch_all / with_email) * 100, 1) if with_email > 0 else 0.0,
            'invalid': int(invalid),
            'invalid_pct': round((invalid / with_email) * 100, 1) if with_email > 0 else 0.0,
            'unknown': int(unknown),
            'unknown_pct': round((unknown / with_email) * 100, 1) if with_email > 0 else 0.0
        })

    # Validation service usage
    if 'email_validation_service' in contacts_df.columns:
        service_counts = contacts_df[contacts_df['email_validation_service'] != 'none']['email_validation_service'].value_counts().to_dict()
        result['validation_services'] = service_counts

    # Email source breakdown
    if 'email_source' in contacts_df.columns:
        source_counts = contacts_df['email_source'].value_counts().to_dict()
        result['email_sources'] = source_counts

    logger.info(f"Email quality summary: {email_coverage_pct}% coverage, {result.get('valid_pct', 0)}% valid")
    return result


def get_confidence_distribution(contacts_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate confidence score distribution with histogram buckets.

    Args:
        contacts_df: DataFrame with 'confidence_score' column

    Returns:
        Dictionary with confidence level counts and statistics
        Example: {
            'high': {'count': 180, 'percentage': 42.9, 'range': '75-100'},
            'medium': {'count': 150, 'percentage': 35.7, 'range': '50-74'},
            'low': {'count': 90, 'percentage': 21.4, 'range': '0-49'},
            'average_score': 67.3,
            'median_score': 70,
            'min_score': 20,
            'max_score': 100
        }
    """
    if contacts_df.empty or 'confidence_score' not in contacts_df.columns:
        return {
            'high': {'count': 0, 'percentage': 0.0, 'range': '75-100'},
            'medium': {'count': 0, 'percentage': 0.0, 'range': '50-74'},
            'low': {'count': 0, 'percentage': 0.0, 'range': '0-49'}
        }

    total = len(contacts_df)
    scores = contacts_df['confidence_score']

    # Categorize by confidence level
    high = (scores >= 75).sum()
    medium = ((scores >= 50) & (scores < 75)).sum()
    low = (scores < 50).sum()

    result = {
        'high': {
            'count': int(high),
            'percentage': round((high / total) * 100, 1),
            'range': '75-100'
        },
        'medium': {
            'count': int(medium),
            'percentage': round((medium / total) * 100, 1),
            'range': '50-74'
        },
        'low': {
            'count': int(low),
            'percentage': round((low / total) * 100, 1),
            'range': '0-49'
        },
        'average_score': round(scores.mean(), 1),
        'median_score': int(scores.median()),
        'min_score': int(scores.min()),
        'max_score': int(scores.max())
    }

    logger.info(f"Confidence distribution: {high} high, {medium} medium, {low} low (avg: {result['average_score']})")
    return result


def get_top_roles(contacts_df: pd.DataFrame, top_n: int = 10) -> List[Dict[str, Any]]:
    """
    Get most common job titles/roles.

    Args:
        contacts_df: DataFrame with 'matched_role' or 'title' column
        top_n: Number of top roles to return (default: 10)

    Returns:
        List of dictionaries with role name and count
        Example: [
            {'role': 'Library Director', 'count': 45},
            {'role': 'Associate Dean', 'count': 38},
            ...
        ]
    """
    if contacts_df.empty:
        return []

    # Prefer matched_role over title (matched_role is standardized)
    role_column = 'matched_role' if 'matched_role' in contacts_df.columns else 'title'

    if role_column not in contacts_df.columns:
        logger.warning(f"No role column found in contacts DataFrame")
        return []

    # Filter out NaN values
    roles = contacts_df[contacts_df[role_column].notna()][role_column]

    if roles.empty:
        return []

    role_counts = roles.value_counts().head(top_n)

    result = [
        {'role': role, 'count': int(count)}
        for role, count in role_counts.items()
    ]

    logger.info(f"Top {len(result)} roles identified (out of {len(roles.unique())} unique roles)")
    return result


def calculate_scraping_success_rate(
    contacts_df: pd.DataFrame,
    targets_df: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Calculate scraping success/failure rates per institution.

    Args:
        contacts_df: DataFrame with scraped contacts
        targets_df: DataFrame with target institutions (optional)

    Returns:
        Dictionary with success rate statistics
        Example: {
            'total_institutions_attempted': 50,
            'successful_extractions': 35,
            'failed_extractions': 15,
            'success_rate_pct': 70.0,
            'avg_contacts_per_institution': 3.2,
            'institutions_by_contact_count': {
                '0 contacts': 15,
                '1-2 contacts': 12,
                '3-5 contacts': 18,
                '6+ contacts': 5
            }
        }
    """
    if contacts_df.empty:
        return {
            'total_institutions_attempted': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'success_rate_pct': 0.0
        }

    # Count unique institutions from contacts
    if 'institution_name' in contacts_df.columns:
        institution_counts = contacts_df['institution_name'].value_counts()
        successful_institutions = len(institution_counts)
        avg_contacts = round(institution_counts.mean(), 1)

        # Categorize institutions by contact count
        contact_buckets = {
            '1-2 contacts': ((institution_counts >= 1) & (institution_counts <= 2)).sum(),
            '3-5 contacts': ((institution_counts >= 3) & (institution_counts <= 5)).sum(),
            '6-10 contacts': ((institution_counts >= 6) & (institution_counts <= 10)).sum(),
            '11+ contacts': (institution_counts >= 11).sum()
        }
    else:
        successful_institutions = 0
        avg_contacts = 0.0
        contact_buckets = {}

    # If targets_df provided, calculate failure rate
    total_attempted = len(targets_df) if targets_df is not None and not targets_df.empty else successful_institutions
    failed = total_attempted - successful_institutions
    success_rate = round((successful_institutions / total_attempted) * 100, 1) if total_attempted > 0 else 0.0

    result = {
        'total_institutions_attempted': total_attempted,
        'successful_extractions': successful_institutions,
        'failed_extractions': failed,
        'success_rate_pct': success_rate,
        'avg_contacts_per_institution': avg_contacts,
        'institutions_by_contact_count': contact_buckets
    }

    logger.info(f"Scraping success rate: {success_rate}% ({successful_institutions}/{total_attempted})")
    return result


def calculate_contact_statistics(
    contacts_df: pd.DataFrame,
    targets_df: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Main orchestrator function to calculate all statistics.

    Args:
        contacts_df: DataFrame with scraped and enriched contacts
        targets_df: DataFrame with target institutions (optional)

    Returns:
        Comprehensive dictionary with all statistics
        Example: {
            'summary': {
                'total_contacts': 420,
                'total_institutions': 50,
                'avg_contacts_per_institution': 8.4
            },
            'by_state': {...},
            'by_program_type': {...},
            'email_quality': {...},
            'confidence_distribution': {...},
            'top_roles': [...],
            'scraping_success': {...}
        }
    """
    logger.info("Calculating comprehensive contact statistics...")

    if contacts_df.empty:
        logger.warning("Empty contacts DataFrame provided")
        return {
            'summary': {
                'total_contacts': 0,
                'total_institutions': 0,
                'avg_contacts_per_institution': 0.0
            }
        }

    # Summary statistics
    total_contacts = len(contacts_df)
    total_institutions = contacts_df['institution_name'].nunique() if 'institution_name' in contacts_df.columns else 0
    avg_contacts = round(total_contacts / total_institutions, 1) if total_institutions > 0 else 0.0

    summary = {
        'total_contacts': total_contacts,
        'total_institutions': total_institutions,
        'avg_contacts_per_institution': avg_contacts
    }

    # Calculate all statistics
    statistics = {
        'summary': summary,
        'by_state': get_state_breakdown(contacts_df),
        'by_program_type': get_program_type_breakdown(contacts_df),
        'email_quality': get_email_quality_summary(contacts_df),
        'confidence_distribution': get_confidence_distribution(contacts_df),
        'top_roles': get_top_roles(contacts_df, top_n=10),
        'scraping_success': calculate_scraping_success_rate(contacts_df, targets_df)
    }

    logger.info(f"Statistics calculation complete: {total_contacts} contacts from {total_institutions} institutions")
    return statistics
