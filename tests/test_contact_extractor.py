"""
Unit tests for Contact Extraction Module.

Tests title matching, confidence scoring, email pattern detection,
and contact extraction logic.
"""

import pytest
import pandas as pd
from bs4 import BeautifulSoup

from modules.contact_extractor import (
    match_title_to_role,
    calculate_contact_confidence,
    detect_email_pattern,
    construct_email,
    find_directory_pages,
    extract_contact_from_section,
    deduplicate_contacts,
)
from config.settings import LAW_SCHOOL_ROLES, PARALEGAL_PROGRAM_ROLES


# =============================================================================
# Title Matching Tests
# =============================================================================

class TestTitleMatching:
    """Tests for fuzzy title matching."""

    def test_exact_match(self):
        """Test exact title match."""
        title = "Library Director"
        matched, confidence, score = match_title_to_role(title, LAW_SCHOOL_ROLES)

        assert matched == "Library Director"
        assert confidence == 20  # Exact match
        assert score >= 90

    def test_partial_match(self):
        """Test partial title match."""
        title = "Director of Law Library Services"
        matched, confidence, score = match_title_to_role(title, LAW_SCHOOL_ROLES)

        assert matched in LAW_SCHOOL_ROLES
        assert confidence in [10, 20]  # Good match
        assert score >= 70

    def test_word_order_variation(self):
        """Test title with different word order."""
        title = "Law Library Director"
        matched, confidence, score = match_title_to_role(title, LAW_SCHOOL_ROLES)

        assert matched in LAW_SCHOOL_ROLES
        assert score >= 70

    def test_no_match(self):
        """Test title that doesn't match any role."""
        title = "Professor of Economics"
        matched, confidence, score = match_title_to_role(title, LAW_SCHOOL_ROLES)

        assert matched is None
        assert confidence == 0
        assert score < 70

    def test_paralegal_roles(self):
        """Test matching for paralegal program roles."""
        title = "Paralegal Program Director"
        matched, confidence, score = match_title_to_role(title, PARALEGAL_PROGRAM_ROLES)

        assert matched == "Paralegal Program Director"
        assert confidence == 20
        assert score >= 90

    def test_fuzzy_match_with_typo(self):
        """Test fuzzy matching handles minor typos."""
        title = "Libary Director"  # Typo: Libary instead of Library
        matched, confidence, score = match_title_to_role(title, LAW_SCHOOL_ROLES)

        # Should still match due to fuzzy logic
        assert score > 60  # Not perfect but should score reasonably

    def test_empty_title(self):
        """Test empty title."""
        matched, confidence, score = match_title_to_role("", LAW_SCHOOL_ROLES)

        assert matched is None
        assert confidence == 0
        assert score == 0

    def test_case_insensitive(self):
        """Test matching is case insensitive."""
        title = "LIBRARY DIRECTOR"
        matched, confidence, score = match_title_to_role(title, LAW_SCHOOL_ROLES)

        assert matched == "Library Director"
        assert score >= 90


# =============================================================================
# Confidence Scoring Tests
# =============================================================================

class TestConfidenceScoring:
    """Tests for contact confidence scoring."""

    def test_maximum_score(self):
        """Test maximum possible confidence score."""
        score = calculate_contact_confidence(
            has_email=True,
            email_on_site=True,
            email_validated=True,
            email_is_catchall=False,
            title_match_score=95,
            has_phone=True,
            linkedin_verified=True
        )

        # 40 (email on site) + 30 (validated) + 20 (title exact) + 10 (phone) + 10 (linkedin)
        assert score == 100  # Capped at 100

    def test_minimum_score(self):
        """Test low confidence score."""
        score = calculate_contact_confidence(
            has_email=True,
            email_on_site=False,  # Constructed email: -30
            email_validated=False,
            email_is_catchall=True,  # -20
            title_match_score=50,  # No title match points
            has_phone=False,
            linkedin_verified=False
        )

        # -30 (constructed) -20 (catchall) = -50, but minimum is 0
        assert score == 0

    def test_good_score(self):
        """Test typical good contact score."""
        score = calculate_contact_confidence(
            has_email=True,
            email_on_site=True,  # +40
            email_validated=False,
            email_is_catchall=False,
            title_match_score=85,  # +10 (good match)
            has_phone=True,  # +10
            linkedin_verified=False
        )

        # 40 + 10 + 10 = 60
        assert score == 60

    def test_no_email(self):
        """Test scoring when no email present."""
        score = calculate_contact_confidence(
            has_email=False,
            email_on_site=False,
            email_validated=False,
            email_is_catchall=False,
            title_match_score=95,  # +20
            has_phone=True,  # +10
            linkedin_verified=False
        )

        # Only title and phone: 20 + 10 = 30
        assert score == 30


# =============================================================================
# Email Pattern Detection Tests
# =============================================================================

class TestEmailPatternDetection:
    """Tests for email pattern detection and construction."""

    def test_detect_dot_pattern(self):
        """Test detection of firstname.lastname pattern."""
        emails = [
            "john.smith@example.edu",
            "jane.doe@example.edu",
            "bob.jones@example.edu"
        ]

        pattern = detect_email_pattern(emails, "example.edu")
        assert pattern == '.'

    def test_detect_underscore_pattern(self):
        """Test detection of firstname_lastname pattern."""
        emails = [
            "john_smith@example.edu",
            "jane_doe@example.edu",
            "bob_jones@example.edu"
        ]

        pattern = detect_email_pattern(emails, "example.edu")
        assert pattern == '_'

    def test_insufficient_emails(self):
        """Test pattern detection with too few emails."""
        emails = ["john.smith@example.edu"]

        pattern = detect_email_pattern(emails, "example.edu")
        assert pattern is None  # Need at least 3 emails

    def test_construct_email_dot_pattern(self):
        """Test email construction with dot pattern."""
        email = construct_email("John", "Smith", "example.edu", pattern='.')

        assert email == "john.smith@example.edu"

    def test_construct_email_underscore_pattern(self):
        """Test email construction with underscore pattern."""
        email = construct_email("Jane", "Doe", "example.edu", pattern='_')

        assert email == "jane_doe@example.edu"

    def test_construct_email_no_separator(self):
        """Test email construction with no separator."""
        email = construct_email("Bob", "Jones", "example.edu", pattern='none')

        assert email == "bobjones@example.edu"

    def test_construct_email_empty_name(self):
        """Test email construction with empty name."""
        email = construct_email("", "Smith", "example.edu")

        assert email == ""


# =============================================================================
# Directory Page Discovery Tests
# =============================================================================

class TestDirectoryPageDiscovery:
    """Tests for finding directory pages on websites."""

    def test_find_faculty_page(self):
        """Test finding faculty directory page."""
        html = """
        <html>
            <body>
                <nav>
                    <a href="/about">About</a>
                    <a href="/faculty">Faculty Directory</a>
                    <a href="/students">Students</a>
                </nav>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        base_url = "https://law.example.edu"

        urls = find_directory_pages(base_url, soup, program_type='law')

        assert len(urls) >= 1
        assert any('faculty' in url for url in urls)

    def test_find_staff_page(self):
        """Test finding staff directory page."""
        html = """
        <html>
            <body>
                <a href="/administration/staff">Staff Directory</a>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        base_url = "https://law.example.edu"

        urls = find_directory_pages(base_url, soup, program_type='law')

        assert len(urls) >= 1
        assert any('staff' in url for url in urls)

    def test_relative_url_conversion(self):
        """Test that relative URLs are converted to absolute."""
        html = """
        <html>
            <body>
                <a href="/people">People</a>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        base_url = "https://law.example.edu"

        urls = find_directory_pages(base_url, soup, program_type='law')

        assert len(urls) >= 1
        assert urls[0].startswith('https://')

    def test_no_directory_pages(self):
        """Test when no directory pages found."""
        html = """
        <html>
            <body>
                <a href="/news">News</a>
                <a href="/events">Events</a>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, 'html.parser')
        base_url = "https://law.example.edu"

        urls = find_directory_pages(base_url, soup, program_type='law')

        assert len(urls) == 0


# =============================================================================
# Contact Extraction Tests
# =============================================================================

class TestContactExtraction:
    """Tests for extracting contacts from HTML sections."""

    def test_extract_contact_with_email(self):
        """Test extracting contact with email."""
        html = """
        <div class="profile">
            <h3>Jane Smith</h3>
            <p class="title">Library Director</p>
            <a href="mailto:jane.smith@law.edu">jane.smith@law.edu</a>
            <p>Phone: (555) 123-4567</p>
        </div>
        """
        section = BeautifulSoup(html, 'html.parser')

        contact = extract_contact_from_section(
            section,
            LAW_SCHOOL_ROLES,
            "Example Law School",
            "https://law.example.edu",
            "CA",
            "Law School"
        )

        assert contact is not None
        assert contact['full_name'] == "Jane Smith"
        assert contact['title'] == "Library Director"
        assert contact['email'] == "jane.smith@law.edu"
        assert contact['phone'] == "(555) 123-4567"
        assert contact['confidence_score'] > 50

    def test_skip_irrelevant_title(self):
        """Test skipping contact with irrelevant title."""
        html = """
        <div class="profile">
            <h3>John Doe</h3>
            <p class="title">Professor of Economics</p>
            <a href="mailto:john.doe@law.edu">john.doe@law.edu</a>
        </div>
        """
        section = BeautifulSoup(html, 'html.parser')

        contact = extract_contact_from_section(
            section,
            LAW_SCHOOL_ROLES,
            "Example Law School",
            "https://law.example.edu",
            "CA",
            "Law School"
        )

        # Should skip because title doesn't match
        assert contact is None

    def test_extract_minimal_contact(self):
        """Test extracting contact with minimal information."""
        html = """
        <div class="staff-member">
            <strong>Bob Johnson</strong>
            <span>Associate Dean for Academic Affairs</span>
        </div>
        """
        section = BeautifulSoup(html, 'html.parser')

        contact = extract_contact_from_section(
            section,
            LAW_SCHOOL_ROLES,
            "Example Law School",
            "https://law.example.edu",
            "CA",
            "Law School"
        )

        assert contact is not None
        assert "Bob Johnson" in contact['full_name']
        assert "Dean" in contact['title']


# =============================================================================
# Deduplication Tests
# =============================================================================

class TestDeduplication:
    """Tests for contact deduplication."""

    def test_deduplicate_by_email(self):
        """Test deduplication by email address."""
        contacts = [
            {
                'full_name': 'John Smith',
                'title': 'Director',
                'email': 'john@example.edu'
            },
            {
                'full_name': 'J. Smith',
                'title': 'Library Director',
                'email': 'john@example.edu'  # Same email
            }
        ]

        unique = deduplicate_contacts(contacts)

        assert len(unique) == 1
        assert unique[0]['full_name'] == 'John Smith'

    def test_deduplicate_by_name_title(self):
        """Test deduplication by name and title."""
        contacts = [
            {
                'full_name': 'Jane Doe',
                'title': 'Dean',
                'email': ''
            },
            {
                'full_name': 'Jane Doe',
                'title': 'Dean',
                'email': ''  # Same name and title
            }
        ]

        unique = deduplicate_contacts(contacts)

        assert len(unique) == 1

    def test_keep_different_contacts(self):
        """Test keeping genuinely different contacts."""
        contacts = [
            {
                'full_name': 'John Smith',
                'title': 'Director',
                'email': 'john@example.edu'
            },
            {
                'full_name': 'Jane Doe',
                'title': 'Dean',
                'email': 'jane@example.edu'
            }
        ]

        unique = deduplicate_contacts(contacts)

        assert len(unique) == 2


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
