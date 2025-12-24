"""
Unit tests for deduplication module.

Tests deduplication strategies, database comparison, and record merging.
"""

import pytest
import pandas as pd
import tempfile
from pathlib import Path
from modules.deduplication import (
    normalize_name,
    normalize_email,
    deduplicate_by_email,
    deduplicate_by_name_institution,
    deduplicate_contacts,
    load_existing_database,
    find_matching_contact,
    merge_contact_records,
    compare_with_existing
)


class TestNormalizeFunctions:
    """Test normalization utility functions."""

    def test_normalize_name(self):
        """Test name normalization."""
        assert normalize_name("John Doe") == "john doe"
        assert normalize_name("  JOHN   DOE  ") == "john doe"
        assert normalize_name("john-doe") == "john-doe"
        assert normalize_name("") == ""
        assert normalize_name(None) == ""

    def test_normalize_email(self):
        """Test email normalization."""
        assert normalize_email("JOHN@EXAMPLE.COM") == "john@example.com"
        assert normalize_email("  john@example.com  ") == "john@example.com"
        assert normalize_email("") == ""
        assert normalize_email(None) == ""


class TestDeduplicateByEmail:
    """Test email-based deduplication."""

    def test_remove_exact_duplicates(self):
        """Test removing exact duplicate emails."""
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'email': 'john@example.com', 'title': 'Director'},
            {'full_name': 'Jane Doe', 'email': 'john@example.com', 'title': 'Manager'},  # Duplicate email
            {'full_name': 'Bob Smith', 'email': 'bob@example.com', 'title': 'Professor'}
        ])

        result = deduplicate_by_email(df)

        assert len(result) == 2  # Should remove 1 duplicate
        assert 'john@example.com' in result['email'].values
        assert 'bob@example.com' in result['email'].values

    def test_case_insensitive_matching(self):
        """Test case-insensitive email matching."""
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'email': 'JOHN@EXAMPLE.COM', 'title': 'Director'},
            {'full_name': 'Jane Doe', 'email': 'john@example.com', 'title': 'Manager'},  # Same email, different case
        ])

        result = deduplicate_by_email(df)

        assert len(result) == 1  # Should recognize as duplicate despite case difference

    def test_preserve_contacts_without_email(self):
        """Test that contacts without emails are preserved."""
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'email': 'john@example.com', 'title': 'Director'},
            {'full_name': 'Jane Doe', 'email': None, 'title': 'Manager'},
            {'full_name': 'Bob Smith', 'email': '', 'title': 'Professor'}
        ])

        result = deduplicate_by_email(df)

        assert len(result) == 3  # All should be preserved
        assert result[result['email'].isna()].shape[0] == 1  # One with None
        assert result[result['email'] == ''].shape[0] == 1  # One with empty string

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pd.DataFrame()
        result = deduplicate_by_email(df)
        assert result.empty


class TestDeduplicateByNameInstitution:
    """Test name+institution based deduplication."""

    def test_remove_name_institution_duplicates(self):
        """Test removing duplicates by name+institution."""
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': None, 'title': 'Director'},
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': None, 'title': 'Manager'},  # Duplicate
            {'full_name': 'Jane Smith', 'institution_name': 'UCLA', 'email': None, 'title': 'Professor'}
        ])

        result = deduplicate_by_name_institution(df)

        assert len(result) == 2  # Should remove 1 duplicate

    def test_same_name_different_institution(self):
        """Test that same name at different institutions is not a duplicate."""
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': None, 'title': 'Director'},
            {'full_name': 'John Doe', 'institution_name': 'UCLA', 'email': None, 'title': 'Director'}
        ])

        result = deduplicate_by_name_institution(df)

        assert len(result) == 2  # Should keep both (different institutions)

    def test_only_applies_to_contacts_without_email(self):
        """Test that only contacts without email are deduplicated by name+institution."""
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': 'john@stanford.edu', 'title': 'Director'},
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': 'john2@stanford.edu', 'title': 'Manager'},
            {'full_name': 'Jane Smith', 'institution_name': 'UCLA', 'email': None, 'title': 'Professor'}
        ])

        result = deduplicate_by_name_institution(df)

        # Both contacts with emails should be preserved (deduplicated by email in previous step)
        assert len(result) == 3


class TestDeduplicateContacts:
    """Test main deduplication orchestrator."""

    def test_hierarchical_deduplication(self):
        """Test hierarchical strategy: email first, then name+institution."""
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': 'john@stanford.edu', 'title': 'Director'},
            {'full_name': 'Jane Doe', 'institution_name': 'Stanford', 'email': 'john@stanford.edu', 'title': 'Manager'},  # Duplicate by email
            {'full_name': 'Bob Smith', 'institution_name': 'UCLA', 'email': None, 'title': 'Professor'},
            {'full_name': 'Bob Smith', 'institution_name': 'UCLA', 'email': None, 'title': 'Dean'},  # Duplicate by name+institution
            {'full_name': 'Alice Brown', 'institution_name': 'NYU', 'email': 'alice@nyu.edu', 'title': 'Librarian'}
        ])

        result = deduplicate_contacts(df)

        assert len(result) == 3  # Should remove 2 duplicates (1 by email, 1 by name+institution)

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pd.DataFrame()
        result = deduplicate_contacts(df)
        assert result.empty


class TestLoadExistingDatabase:
    """Test loading existing contacts database."""

    def test_load_csv_file(self):
        """Test loading existing database from CSV."""
        # Create temporary CSV file
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'email': 'john@example.com', 'title': 'Director'}
        ])

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            df.to_csv(f.name, index=False)
            temp_path = f.name

        try:
            result = load_existing_database(temp_path)
            assert result is not None
            assert len(result) == 1
            assert result['full_name'].iloc[0] == 'John Doe'
        finally:
            Path(temp_path).unlink()

    def test_load_excel_file(self):
        """Test loading existing database from Excel."""
        # Create temporary Excel file
        df = pd.DataFrame([
            {'full_name': 'John Doe', 'email': 'john@example.com', 'title': 'Director'}
        ])

        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            df.to_excel(f.name, index=False, sheet_name='All Contacts')
            temp_path = f.name

        try:
            result = load_existing_database(temp_path)
            assert result is not None
            assert len(result) == 1
        finally:
            Path(temp_path).unlink()

    def test_file_not_found(self):
        """Test with non-existent file."""
        result = load_existing_database('/nonexistent/file.csv')
        assert result is None

    def test_unsupported_format(self):
        """Test with unsupported file format."""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            temp_path = f.name

        try:
            result = load_existing_database(temp_path)
            assert result is None
        finally:
            Path(temp_path).unlink()


class TestFindMatchingContact:
    """Test finding matching contacts in existing database."""

    def test_match_by_email(self):
        """Test matching by email address."""
        existing_df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': 'john@stanford.edu', 'title': 'Director'},
            {'full_name': 'Jane Smith', 'institution_name': 'UCLA', 'email': 'jane@ucla.edu', 'title': 'Professor'}
        ])

        new_contact = pd.Series({
            'full_name': 'John Doe Updated',  # Different name
            'institution_name': 'Stanford',
            'email': 'john@stanford.edu',  # Same email
            'title': 'Associate Director'
        })

        match = find_matching_contact(new_contact, existing_df)

        assert match is not None
        assert match['email'] == 'john@stanford.edu'
        assert match['full_name'] == 'John Doe'  # Original record

    def test_match_by_name_institution(self):
        """Test matching by name+institution (fallback)."""
        existing_df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': '', 'title': 'Director'},
            {'full_name': 'Jane Smith', 'institution_name': 'UCLA', 'email': '', 'title': 'Professor'}
        ])

        new_contact = pd.Series({
            'full_name': 'John Doe',
            'institution_name': 'Stanford',
            'email': '',  # No email
            'title': 'Associate Director'
        })

        match = find_matching_contact(new_contact, existing_df)

        assert match is not None
        assert match['full_name'] == 'John Doe'
        assert match['institution_name'] == 'Stanford'

    def test_no_match_found(self):
        """Test when no match exists."""
        existing_df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': 'john@stanford.edu', 'title': 'Director'}
        ])

        new_contact = pd.Series({
            'full_name': 'Alice Brown',
            'institution_name': 'NYU',
            'email': 'alice@nyu.edu',
            'title': 'Librarian'
        })

        match = find_matching_contact(new_contact, existing_df)

        assert match is None


class TestMergeContactRecords:
    """Test smart field merging for contact records."""

    def test_merge_with_newest_data(self):
        """Test that newest non-empty values are preferred."""
        existing = pd.Series({
            'full_name': 'John Doe',
            'title': 'Director',
            'email': 'john@stanford.edu',
            'phone': '',
            'confidence_score': 60,
            'email_status': 'unknown',
            'extracted_at': '2024-01-01 10:00:00'
        })

        new = pd.Series({
            'full_name': 'John Doe',
            'title': 'Associate Director',  # Updated title
            'email': 'john@stanford.edu',
            'phone': '555-1234',  # New phone number
            'confidence_score': 70,
            'email_status': 'valid',  # Better validation
            'extracted_at': '2024-12-23 15:00:00'
        })

        merged = merge_contact_records(existing, new)

        assert merged['title'] == 'Associate Director'  # Updated
        assert merged['phone'] == '555-1234'  # Added
        assert merged['email_status'] == 'valid'  # Better validation
        assert merged['last_updated'] == '2024-12-23 15:00:00'
        assert merged['record_source'] == 'merged'

    def test_keep_higher_quality_email_validation(self):
        """Test that higher quality email validation is kept."""
        existing = pd.Series({
            'full_name': 'John Doe',
            'email': 'john@stanford.edu',
            'email_status': 'catch-all',
            'confidence_score': 60
        })

        new = pd.Series({
            'full_name': 'John Doe',
            'email': 'john@stanford.edu',
            'email_status': 'valid',  # Better validation
            'confidence_score': 70
        })

        merged = merge_contact_records(existing, new)

        assert merged['email_status'] == 'valid'  # Should use better validation

    def test_confidence_score_recalculation(self):
        """Test that confidence score is recalculated after merge."""
        existing = pd.Series({
            'full_name': 'John Doe',
            'email': 'john@stanford.edu',
            'phone': '',
            'email_status': 'unknown',
            'confidence_score': 50
        })

        new = pd.Series({
            'full_name': 'John Doe',
            'email': 'john@stanford.edu',
            'phone': '555-1234',  # New phone
            'email_status': 'valid',  # Better validation
            'confidence_score': 60
        })

        merged = merge_contact_records(existing, new)

        # Base 60 + 10 (valid email) + 5 (has phone) = 75
        assert merged['confidence_score'] == 75


class TestCompareWithExisting:
    """Test comparison with existing database."""

    def test_classify_contacts(self):
        """Test classifying contacts into new/duplicate/update categories."""
        existing_df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': 'john@stanford.edu', 'title': 'Director', 'phone': '555-0000'},
            {'full_name': 'Jane Smith', 'institution_name': 'UCLA', 'email': 'jane@ucla.edu', 'title': 'Professor', 'phone': '555-1111'}
        ])

        new_df = pd.DataFrame([
            {'full_name': 'John Doe', 'institution_name': 'Stanford', 'email': 'john@stanford.edu', 'title': 'Associate Director', 'phone': '555-0000'},  # Update (title changed)
            {'full_name': 'Jane Smith', 'institution_name': 'UCLA', 'email': 'jane@ucla.edu', 'title': 'Professor', 'phone': '555-1111'},  # Duplicate (no changes)
            {'full_name': 'Bob Johnson', 'institution_name': 'NYU', 'email': 'bob@nyu.edu', 'title': 'Librarian', 'phone': '555-2222'}  # New
        ])

        new, duplicates, updates = compare_with_existing(new_df, existing_df)

        assert len(new) == 1  # Bob Johnson
        assert len(duplicates) == 1  # Jane Smith
        assert len(updates) == 1  # John Doe
        assert new.iloc[0]['full_name'] == 'Bob Johnson'
        assert duplicates.iloc[0]['full_name'] == 'Jane Smith'
        assert updates.iloc[0]['full_name'] == 'John Doe'

    def test_no_existing_database(self):
        """Test when no existing database is provided."""
        new_df = pd.DataFrame([
            {'full_name': 'John Doe', 'email': 'john@stanford.edu', 'title': 'Director'}
        ])

        new, duplicates, updates = compare_with_existing(new_df, None)

        assert len(new) == 1  # All are new
        assert len(duplicates) == 0
        assert len(updates) == 0

    def test_empty_new_contacts(self):
        """Test with empty new contacts DataFrame."""
        existing_df = pd.DataFrame([
            {'full_name': 'John Doe', 'email': 'john@stanford.edu', 'title': 'Director'}
        ])

        new, duplicates, updates = compare_with_existing(pd.DataFrame(), existing_df)

        assert len(new) == 0
        assert len(duplicates) == 0
        assert len(updates) == 0
