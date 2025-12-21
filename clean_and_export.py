#!/usr/bin/env python3
"""
clean_and_export.py - Data cleaning and export pipeline for contact scraper

Transforms raw scraped contacts into high-quality, actionable contact lists.
Implements comprehensive validation, deduplication, quality scoring, and export.
"""

import pandas as pd
import re
import sys
import logging
from datetime import datetime
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional
from config import CLIENT_TYPES, get_priority_score

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clean_and_export.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    # Quality thresholds
    'min_quality_score_all': 40,        # Tier C+
    'min_quality_score_high': 60,       # Tier B+
    'min_quality_score_decision': 70,   # Tier A

    # Deduplication
    'fuzzy_match_threshold': 0.85,      # Name similarity %
    'merge_cross_institution': True,    # Merge duplicates across institutions

    # Email filtering
    'exclude_generic_emails': False,    # Don't exclude generics in 'all' export
    'require_personal_email': False,    # Only personal emails

    # Export options
    'create_client_type_files': True,   # Separate files per type
    'min_contacts_per_file': 1,         # Min contacts to create file
    'export_formats': ['csv'],          # Future: ['csv', 'xlsx', 'json']
}

# Generic email patterns (departmental/generic addresses)
GENERIC_EMAIL_PATTERNS = [
    'info@', 'contact@', 'webmaster@', 'admin@', 'admissions@',
    'registrar@', 'studentservice', 'office@', 'general@', 'support@',
    'help@', 'service@', 'enquiries@', 'enquiry@', 'reception@'
]

# Junk text patterns to detect in name field
JUNK_NAME_PATTERNS = [
    r'\d{3,5}\s+(?:Ave|Avenue|Blvd|Boulevard|Street|St|Road|Rd|Drive|Dr|Lane|Ln)',  # Addresses
    r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',  # Dates
    r'https?://',  # URLs
    r'Agenda:',  # Meeting agendas
    r'Meeting\s+Video',  # Meeting references
]

# Title normalization mapping
TITLE_NORMALIZATION = {
    r'\bDir\b': 'Director',
    r'\bAssoc\b': 'Associate',
    r'\bAsst\b': 'Assistant',
    r'\bVP\b': 'Vice President',
    r'\bSVP\b': 'Senior Vice President',
    r'\bEVP\b': 'Executive Vice President',
    r'\bMgr\b': 'Manager',
    r'\bCoord\b': 'Coordinator',
    r'\bDept\b': 'Department',
    r'\bProf\b': 'Professor',
}

class ContactCleaner:
    def __init__(self, config: Dict = CONFIG):
        self.config = config
        self.stats = {
            'total_raw': 0,
            'duplicates_removed': 0,
            'invalid_emails': 0,
            'junk_names_cleaned': 0,
            'valid_contacts': 0,
            'quality_tiers': Counter(),
            'client_type_counts': Counter(),
        }

    def load_data(self, input_file: str) -> pd.DataFrame:
        """Phase 1: Load and initial cleaning"""
        logger.info("="*80)
        logger.info("PHASE 1: Data Loading & Initial Cleaning")
        logger.info("="*80)

        try:
            df = pd.read_csv(input_file, encoding='utf-8-sig')
            # Strip BOM from column names
            df.columns = df.columns.str.replace('\ufeff', '', regex=False)
            df.columns = df.columns.str.replace('﻿', '', regex=False)

            self.stats['total_raw'] = len(df)
            logger.info(f"Loaded {len(df)} raw contacts from {input_file}")

            # Strip whitespace from all string columns
            for col in df.select_dtypes(include=['object']).columns:
                df[col] = df[col].str.strip() if hasattr(df[col], 'str') else df[col]

            # Convert emails to lowercase
            if 'email' in df.columns:
                df['email'] = df['email'].str.lower()

            # Parse scraped_date
            if 'scraped_date' in df.columns:
                df['scraped_date'] = pd.to_datetime(df['scraped_date'], errors='coerce')

            logger.info(f"Institutions: {df['INSTNM'].nunique() if 'INSTNM' in df.columns else 'N/A'}")
            logger.info(f"Client types: {df['CLIENT_TYPE'].nunique() if 'CLIENT_TYPE' in df.columns else 'N/A'}")

            return df

        except Exception as e:
            logger.error(f"Failed to load {input_file}: {e}")
            sys.exit(1)

    def validate_email(self, email: str) -> bool:
        """Validate email format"""
        if not email or pd.isna(email):
            return False
        pattern = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        return bool(re.match(pattern, str(email).lower()))

    def categorize_email(self, email: str) -> str:
        """Categorize email as personal, departmental, or generic"""
        if not email or pd.isna(email):
            return 'unknown'

        email_lower = str(email).lower()

        # Check for generic patterns
        for pattern in GENERIC_EMAIL_PATTERNS:
            if pattern in email_lower:
                return 'generic'

        # Departmental indicators (no personal name in local part)
        local_part = email_lower.split('@')[0]
        departmental_keywords = ['student', 'faculty', 'library', 'career', 'academic',
                                'housing', 'financial', 'graduate', 'undergraduate']

        if any(keyword in local_part for keyword in departmental_keywords):
            return 'departmental'

        # Personal email indicators (has name-like structure)
        if '.' in local_part or len(local_part.split('.')) > 1:
            # Likely firstname.lastname@
            return 'personal'

        return 'departmental'

    def process_emails(self, df: pd.DataFrame) -> pd.DataFrame:
        """Phase 2: Email processing and validation"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 2: Email Processing & Validation")
        logger.info("="*80)

        # Validate emails
        df['email_valid'] = df['email'].apply(self.validate_email)
        invalid_count = (~df['email_valid']).sum()
        self.stats['invalid_emails'] = invalid_count
        logger.info(f"Valid emails: {df['email_valid'].sum()} / {len(df)}")
        logger.info(f"Invalid emails: {invalid_count}")

        # Categorize emails
        df['email_type'] = df['email'].apply(self.categorize_email)
        logger.info(f"\nEmail type distribution:")
        for email_type, count in df['email_type'].value_counts().items():
            logger.info(f"  {email_type}: {count}")

        # Extract domain
        df['email_domain'] = df['email'].apply(
            lambda x: x.split('@')[1] if pd.notna(x) and '@' in str(x) else None
        )

        return df

    def is_junk_name(self, name: str) -> bool:
        """Detect if name field contains junk text"""
        if not name or pd.isna(name):
            return True

        name_str = str(name)

        # Too long (likely concatenated text)
        if len(name_str) > 200:
            return True

        # Check for junk patterns
        for pattern in JUNK_NAME_PATTERNS:
            if re.search(pattern, name_str, re.IGNORECASE):
                return True

        # All uppercase (likely header/label)
        if name_str.isupper() and len(name_str) > 10:
            return True

        # Contains too many numbers (likely address/phone)
        digit_ratio = sum(c.isdigit() for c in name_str) / len(name_str)
        if digit_ratio > 0.3:
            return True

        return False

    def extract_person_name(self, name: str, email: str = None) -> Optional[str]:
        """Extract person name from text or email"""
        if not name or pd.isna(name) or self.is_junk_name(name):
            # Try to extract from email
            if email and pd.notna(email):
                local_part = email.split('@')[0]
                # firstname.lastname pattern
                if '.' in local_part:
                    parts = local_part.split('.')
                    if len(parts) == 2:
                        return f"{parts[0].capitalize()} {parts[1].capitalize()}"
            return None

        # Extract name pattern: Title? FirstName LastName
        name_pattern = r'(?:Dr\.|Prof\.|Mr\.|Ms\.|Mrs\.)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'
        match = re.search(name_pattern, str(name))
        if match:
            return match.group(1).strip()

        # Just return cleaned name if it looks reasonable
        name_str = str(name).strip()
        if 2 < len(name_str) < 100 and not self.is_junk_name(name_str):
            return name_str

        return None

    def normalize_title(self, title: str) -> Optional[str]:
        """Normalize and clean title"""
        if not title or pd.isna(title):
            return None

        title_str = str(title).strip()

        # Apply normalization mapping
        for pattern, replacement in TITLE_NORMALIZATION.items():
            title_str = re.sub(pattern, replacement, title_str, flags=re.IGNORECASE)

        # Title case
        title_str = title_str.title()

        # Remove extra whitespace
        title_str = ' '.join(title_str.split())

        if len(title_str) > 3:
            return title_str

        return None

    def process_names_titles(self, df: pd.DataFrame) -> pd.DataFrame:
        """Phase 3: Name and title extraction enhancement"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 3: Name & Title Extraction Enhancement")
        logger.info("="*80)

        # Clean names
        df['name_cleaned'] = df.apply(
            lambda row: self.extract_person_name(row.get('name'), row.get('email')),
            axis=1
        )

        junk_count = df['name'].notna().sum() - df['name_cleaned'].notna().sum()
        self.stats['junk_names_cleaned'] = junk_count
        logger.info(f"Junk names cleaned: {junk_count}")
        logger.info(f"Valid names extracted: {df['name_cleaned'].notna().sum()}")

        # Clean titles
        df['title_cleaned'] = df['title'].apply(self.normalize_title)
        logger.info(f"Valid titles: {df['title_cleaned'].notna().sum()}")

        # Flag if has person name
        df['has_person_name'] = df['name_cleaned'].notna()

        return df

    def normalize_phone(self, phone: str) -> Optional[str]:
        """Normalize phone number to (XXX) XXX-XXXX format"""
        if not phone or pd.isna(phone):
            return None

        # Extract digits only
        digits = re.sub(r'\D', '', str(phone))

        # Validate length (10 digits for US)
        if len(digits) != 10:
            return None

        # Check for invalid patterns
        if digits[0] == '0' or digits == '0' * 10 or len(set(digits)) == 1:
            return None

        # Format
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"

    def process_phones(self, df: pd.DataFrame) -> pd.DataFrame:
        """Phase 4: Phone number normalization"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 4: Phone Number Normalization")
        logger.info("="*80)

        df['phone_cleaned'] = df['phone'].apply(self.normalize_phone)
        df['phone_valid'] = df['phone_cleaned'].notna()

        logger.info(f"Valid phones: {df['phone_valid'].sum()} / {len(df)}")

        return df

    def similarity_ratio(self, str1: str, str2: str) -> float:
        """Calculate similarity ratio between two strings"""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def deduplicate_contacts(self, df: pd.DataFrame) -> pd.DataFrame:
        """Phase 5: Deduplication strategy"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 5: Deduplication")
        logger.info("="*80)

        initial_count = len(df)

        # Mark duplicates
        df['is_duplicate'] = False
        df['duplicate_of'] = None
        df['source_count'] = 1

        # Group by email (exact matches)
        if 'email' in df.columns:
            email_groups = df[df['email'].notna()].groupby('email')

            for email, group in email_groups:
                if len(group) > 1:
                    # Keep the record with highest quality (most complete data)
                    # Scoring: has name=2, has title=1
                    group = group.copy()
                    group['temp_score'] = (
                        group['name_cleaned'].notna().astype(int) * 2 +
                        group['title_cleaned'].notna().astype(int)
                    )

                    best_idx = group['temp_score'].idxmax()

                    # Mark others as duplicates
                    for idx in group.index:
                        if idx != best_idx:
                            df.at[idx, 'is_duplicate'] = True
                            df.at[idx, 'duplicate_of'] = email

                    # Update source count
                    df.at[best_idx, 'source_count'] = len(group)

        duplicates_count = df['is_duplicate'].sum()
        self.stats['duplicates_removed'] = duplicates_count

        logger.info(f"Duplicate emails found: {duplicates_count}")
        logger.info(f"Unique contacts remaining: {initial_count - duplicates_count}")

        return df

    def calculate_quality_score(self, row: pd.Series) -> int:
        """Calculate quality score (0-100)"""
        score = 0

        # Completeness (50 points)
        if row.get('has_person_name', False):
            score += 20
        if pd.notna(row.get('title_cleaned')):
            score += 25
        if row.get('phone_valid', False):
            score += 5

        # Validity (30 points)
        if row.get('email_valid', False):
            score += 15

        email_type = row.get('email_type', '')
        if email_type == 'personal':
            score += 15
        elif email_type == 'departmental':
            score += 10
        elif email_type == 'generic':
            score += 5

        # Relevance (20 points)
        priority = row.get('priority_score_recalc', 0)
        if priority > 0:
            score += 10
        if priority >= 50:
            score += 10

        return min(score, 100)

    def get_quality_tier(self, score: int) -> str:
        """Convert quality score to tier"""
        if score >= 80:
            return 'A'
        elif score >= 60:
            return 'B'
        elif score >= 40:
            return 'C'
        else:
            return 'D'

    def determine_seniority(self, title: str) -> str:
        """Determine seniority level from title"""
        if not title or pd.isna(title):
            return 'unknown'

        title_lower = str(title).lower()

        if any(word in title_lower for word in ['president', 'ceo', 'coo', 'cfo', 'provost', 'chancellor']):
            return 'executive'
        elif any(word in title_lower for word in ['dean', 'director', 'vp', 'vice president', 'chief']):
            return 'director'
        elif any(word in title_lower for word in ['manager', 'coordinator', 'chair', 'head']):
            return 'manager'
        else:
            return 'staff'

    def reclassify_by_page_context(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reclassify contacts based on page_context from scraping"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 5.5: Reclassification by Page Context")
        logger.info("="*80)

        # Check if page_context column exists
        if 'page_context' not in df.columns:
            logger.info("No page_context column found, skipping reclassification")
            return df

        # Add program_type column for tracking
        df['program_type'] = df.get('page_context', 'General')

        # Count law school and paralegal contacts found
        law_school_contacts = (df['page_context'] == 'Law School').sum()
        paralegal_contacts = (df['page_context'] == 'Paralegal Program').sum()

        logger.info(f"Law School contacts found: {law_school_contacts}")
        logger.info(f"Paralegal Program contacts found: {paralegal_contacts}")

        # Reclassify CLIENT_TYPE based on page_context
        # If a contact came from a law school page, prioritize Law School classification
        for idx, row in df.iterrows():
            page_context = row.get('page_context', 'General')
            current_client_type = str(row.get('CLIENT_TYPE', ''))

            if page_context == 'Law School':
                # Add Law School to CLIENT_TYPE if not already present
                client_types = [ct.strip() for ct in current_client_type.split(',') if ct.strip()]
                if 'Law School' not in client_types:
                    client_types.insert(0, 'Law School')  # Prioritize by placing first
                    df.at[idx, 'CLIENT_TYPE'] = ', '.join(client_types)

            elif page_context == 'Paralegal Program':
                # Add Paralegal Program to CLIENT_TYPE if not already present
                client_types = [ct.strip() for ct in current_client_type.split(',') if ct.strip()]
                if 'Paralegal Program' not in client_types:
                    client_types.insert(0, 'Paralegal Program')  # Prioritize by placing first
                    df.at[idx, 'CLIENT_TYPE'] = ', '.join(client_types)

        # Log institutions with law/paralegal programs found
        law_institutions = df[df['page_context'] == 'Law School']['INSTNM'].unique()
        paralegal_institutions = df[df['page_context'] == 'Paralegal Program']['INSTNM'].unique()

        if len(law_institutions) > 0:
            logger.info(f"\n*** Law School programs detected at {len(law_institutions)} institutions:")
            for inst in sorted(law_institutions)[:10]:  # Show first 10
                count = len(df[(df['INSTNM'] == inst) & (df['page_context'] == 'Law School')])
                logger.info(f"  - {inst} ({count} contacts)")

        if len(paralegal_institutions) > 0:
            logger.info(f"\n*** Paralegal programs detected at {len(paralegal_institutions)} institutions:")
            for inst in sorted(paralegal_institutions)[:10]:  # Show first 10
                count = len(df[(df['INSTNM'] == inst) & (df['page_context'] == 'Paralegal Program')])
                logger.info(f"  - {inst} ({count} contacts)")

        return df

    def enrich_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Phase 6: Data enrichment and quality scoring"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 6: Data Enrichment & Quality Scoring")
        logger.info("="*80)

        # Recalculate priority scores with cleaned titles
        def calc_priority(row):
            title = row.get('title_cleaned', '')
            client_types = str(row.get('CLIENT_TYPE', '')).split(', ')

            max_score = 0
            for client_type in client_types:
                if client_type and client_type != 'Unclassified':
                    score = get_priority_score(title, client_type)
                    max_score = max(max_score, score)

            return max_score

        df['priority_score_recalc'] = df.apply(calc_priority, axis=1)
        logger.info(f"Priority scores recalculated")
        logger.info(f"Contacts with priority > 0: {(df['priority_score_recalc'] > 0).sum()}")

        # Calculate quality scores
        df['quality_score'] = df.apply(self.calculate_quality_score, axis=1)
        df['quality_tier'] = df['quality_score'].apply(self.get_quality_tier)

        # Quality tier distribution
        tier_counts = df['quality_tier'].value_counts().sort_index()
        logger.info(f"\nQuality tier distribution:")
        for tier, count in tier_counts.items():
            pct = count / len(df) * 100
            logger.info(f"  Tier {tier}: {count} ({pct:.1f}%)")
            self.stats['quality_tiers'][tier] = count

        # Flag decision makers
        df['is_decision_maker'] = df.apply(
            lambda row: row.get('priority_score_recalc', 0) >= 100,
            axis=1
        )

        logger.info(f"\nDecision makers identified: {df['is_decision_maker'].sum()}")

        # Determine seniority
        df['seniority_level'] = df['title_cleaned'].apply(self.determine_seniority)

        return df

    def filter_contacts(self, df: pd.DataFrame, min_quality: int = 40) -> pd.DataFrame:
        """Phase 7: Filter contacts by quality criteria"""
        logger.info("\n" + "="*80)
        logger.info(f"PHASE 7: Filtering (min_quality={min_quality})")
        logger.info("="*80)

        initial_count = len(df)

        # Apply filters
        filtered = df[
            (df['email_valid'] == True) &
            (df['quality_score'] >= min_quality) &
            (df['is_duplicate'] == False)
        ].copy()

        logger.info(f"Contacts passing filters: {len(filtered)} / {initial_count}")
        logger.info(f"Removed: {initial_count - len(filtered)}")

        return filtered

    def export_contacts(self, df: pd.DataFrame, output_dir: str = '.'):
        """Phase 8: Export strategy"""
        logger.info("\n" + "="*80)
        logger.info("PHASE 8: Export Strategy")
        logger.info("="*80)

        exports_created = []

        # Define column order for exports
        export_columns = [
            'UNITID', 'INSTNM', 'STABBR', 'CLIENT_TYPE',
            'name_cleaned', 'title_cleaned', 'email', 'phone_cleaned',
            'email_type', 'seniority_level', 'quality_score', 'quality_tier',
            'priority_score_recalc', 'is_decision_maker',
            'source_url', 'source_count', 'scraped_date'
        ]

        # Only include columns that exist
        export_columns = [col for col in export_columns if col in df.columns]

        # 1. Export all contacts (min quality 40)
        all_contacts = self.filter_contacts(df, min_quality=self.config['min_quality_score_all'])
        all_contacts = all_contacts[export_columns].sort_values(
            ['quality_score', 'priority_score_recalc'],
            ascending=[False, False]
        )

        filename = f"{output_dir}/contacts_all.csv"
        all_contacts.to_csv(filename, index=False)
        logger.info(f" Created {filename} ({len(all_contacts)} contacts)")
        exports_created.append(('contacts_all.csv', len(all_contacts)))
        self.stats['valid_contacts'] = len(all_contacts)

        # 2. Export high-quality contacts (min quality 60)
        high_quality = self.filter_contacts(df, min_quality=self.config['min_quality_score_high'])
        high_quality = high_quality[export_columns].sort_values(
            ['quality_score', 'priority_score_recalc'],
            ascending=[False, False]
        )

        filename = f"{output_dir}/contacts_high_quality.csv"
        high_quality.to_csv(filename, index=False)
        logger.info(f" Created {filename} ({len(high_quality)} contacts)")
        exports_created.append(('contacts_high_quality.csv', len(high_quality)))

        # 3. Export decision makers
        decision_makers = df[
            (df['is_decision_maker'] == True) &
            (df['email_valid'] == True) &
            (df['is_duplicate'] == False)
        ][export_columns].sort_values('priority_score_recalc', ascending=False)

        if len(decision_makers) > 0:
            filename = f"{output_dir}/contacts_decision_makers.csv"
            decision_makers.to_csv(filename, index=False)
            logger.info(f" Created {filename} ({len(decision_makers)} contacts)")
            exports_created.append(('contacts_decision_makers.csv', len(decision_makers)))

        # 4. Export by client type
        if self.config['create_client_type_files']:
            logger.info("\nCreating client type files...")

            for client_type in CLIENT_TYPES.keys():
                # Filter contacts for this client type
                type_contacts = high_quality[
                    high_quality['CLIENT_TYPE'].str.contains(client_type, na=False, regex=False)
                ]

                if len(type_contacts) >= self.config['min_contacts_per_file']:
                    # Clean filename
                    safe_name = client_type.replace('/', '_').replace(' ', '_')
                    filename = f"{output_dir}/contacts_{safe_name}.csv"

                    type_contacts.to_csv(filename, index=False)
                    logger.info(f"   {safe_name}: {len(type_contacts)} contacts")
                    exports_created.append((f"contacts_{safe_name}.csv", len(type_contacts)))
                    self.stats['client_type_counts'][client_type] = len(type_contacts)

        return exports_created, all_contacts, high_quality, decision_makers

    def generate_summary_report(self, exports_created: List[Tuple[str, int]],
                                df_all: pd.DataFrame, df_high: pd.DataFrame,
                                df_decision: pd.DataFrame, output_dir: str = '.'):
        """Generate summary report"""
        logger.info("\n" + "="*80)
        logger.info("Generating Summary Report")
        logger.info("="*80)

        report_lines = []
        report_lines.append("="*80)
        report_lines.append("CONTACT EXPORT SUMMARY")
        report_lines.append("="*80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")

        # Input statistics
        report_lines.append("INPUT STATISTICS")
        report_lines.append("-" * 40)
        report_lines.append(f"Total raw contacts: {self.stats['total_raw']}")
        report_lines.append("")

        # Data quality
        report_lines.append("DATA QUALITY")
        report_lines.append("-" * 40)
        report_lines.append(f"Duplicates removed: {self.stats['duplicates_removed']}")
        report_lines.append(f"Invalid emails: {self.stats['invalid_emails']}")
        report_lines.append(f"Junk names cleaned: {self.stats['junk_names_cleaned']}")
        report_lines.append(f"Valid contacts: {self.stats['valid_contacts']}")
        report_lines.append("")

        # Quality tiers
        report_lines.append("QUALITY TIERS (of all raw contacts)")
        report_lines.append("-" * 40)
        total_raw = self.stats['total_raw']
        for tier in ['A', 'B', 'C', 'D']:
            count = self.stats['quality_tiers'].get(tier, 0)
            if total_raw > 0:
                pct = count / total_raw * 100
                report_lines.append(f"Tier {tier} (80-100): {count} ({pct:.1f}%)" if tier == 'A' else
                                  f"Tier {tier} (60-79):  {count} ({pct:.1f}%)" if tier == 'B' else
                                  f"Tier {tier} (40-59):  {count} ({pct:.1f}%)" if tier == 'C' else
                                  f"Tier {tier} (0-39):   {count} ({pct:.1f}%)")
        report_lines.append("")

        # Client type breakdown
        if self.stats['client_type_counts']:
            report_lines.append("CLIENT TYPE BREAKDOWN (High-Quality)")
            report_lines.append("-" * 40)
            for ctype, count in sorted(self.stats['client_type_counts'].items()):
                report_lines.append(f"{ctype}: {count} contacts")
            report_lines.append("")

        # Decision makers
        report_lines.append(f"Decision Makers: {len(df_decision)} contacts")
        report_lines.append("")

        # Exports created
        report_lines.append("EXPORTS CREATED")
        report_lines.append("-" * 40)
        for filename, count in exports_created:
            report_lines.append(f" {filename} ({count} records)")
        report_lines.append("")

        # Sample top contacts
        if len(df_high) > 0:
            report_lines.append("TOP 10 HIGH-QUALITY CONTACTS")
            report_lines.append("-" * 40)
            top10 = df_high.head(10)[['INSTNM', 'name_cleaned', 'title_cleaned',
                                      'email', 'quality_score', 'priority_score_recalc']]
            for idx, row in top10.iterrows():
                name = row['name_cleaned'] or 'N/A'
                title = row['title_cleaned'] or 'N/A'
                report_lines.append(f"• {name} - {title}")
                report_lines.append(f"  {row['INSTNM']}")
                report_lines.append(f"  {row['email']} | Quality: {row['quality_score']} | Priority: {row['priority_score_recalc']}")
                report_lines.append("")

        report_lines.append("="*80)

        # Write to file
        report_filename = f"{output_dir}/export_summary.txt"
        with open(report_filename, 'w') as f:
            f.write('\n'.join(report_lines))

        logger.info(f" Summary report saved to {report_filename}")

        # Also print to console
        print("\n".join(report_lines))

    def run(self, input_file: str = 'raw_contacts.csv', output_dir: str = '.'):
        """Main pipeline execution"""
        logger.info("="*80)
        logger.info("CONTACT CLEANER & EXPORTER")
        logger.info("="*80)
        logger.info(f"Input: {input_file}")
        logger.info(f"Output directory: {output_dir}")
        logger.info("")

        # Execute pipeline
        df = self.load_data(input_file)
        df = self.process_emails(df)
        df = self.process_names_titles(df)
        df = self.process_phones(df)
        df = self.deduplicate_contacts(df)
        df = self.reclassify_by_page_context(df)  # Reclassify based on page context
        df = self.enrich_data(df)

        # Export
        exports, df_all, df_high, df_decision = self.export_contacts(df, output_dir)

        # Generate summary
        self.generate_summary_report(exports, df_all, df_high, df_decision, output_dir)

        logger.info("\n" + "="*80)
        logger.info("PIPELINE COMPLETE!")
        logger.info("="*80)

def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Clean and export contact data')
    parser.add_argument('--input', '-i', default='raw_contacts.csv',
                       help='Input CSV file (default: raw_contacts.csv)')
    parser.add_argument('--output-dir', '-o', default='.',
                       help='Output directory (default: current directory)')

    args = parser.parse_args()

    cleaner = ContactCleaner()
    cleaner.run(input_file=args.input, output_dir=args.output_dir)

if __name__ == "__main__":
    main()
