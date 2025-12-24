"""
Unit tests for statistics module.

Tests all statistics calculation functions with various scenarios.
"""

import pytest
import pandas as pd
from modules.statistics import (
    get_state_breakdown,
    get_program_type_breakdown,
    get_email_quality_summary,
    get_confidence_distribution,
    get_top_roles,
    calculate_scraping_success_rate,
    calculate_contact_statistics
)


@pytest.fixture
def sample_contacts():
    """Create sample contacts DataFrame for testing."""
    return pd.DataFrame([
        {
            'institution_name': 'Stanford Law School',
            'state': 'CA',
            'program_type': 'Law School',
            'full_name': 'John Doe',
            'title': 'Library Director',
            'matched_role': 'Library Director',
            'email': 'john@stanford.edu',
            'phone': '555-1234',
            'confidence_score': 80,
            'email_status': 'valid',
            'email_is_catchall': False,
            'email_validation_service': 'neverbounce',
            'email_source': 'website_scrape'
        },
        {
            'institution_name': 'Stanford Law School',
            'state': 'CA',
            'program_type': 'Law School',
            'full_name': 'Jane Smith',
            'title': 'Associate Dean',
            'matched_role': 'Associate Dean',
            'email': 'jane@stanford.edu',
            'phone': '555-5678',
            'confidence_score': 75,
            'email_status': 'valid',
            'email_is_catchall': False,
            'email_validation_service': 'zerobounce',
            'email_source': 'website_scrape'
        },
        {
            'institution_name': 'UCLA Law School',
            'state': 'CA',
            'program_type': 'Law School',
            'full_name': 'Bob Johnson',
            'title': 'Professor',
            'matched_role': 'Legal Writing Director',
            'email': 'bob@ucla.edu',
            'phone': '',
            'confidence_score': 60,
            'email_status': 'catch-all',
            'email_is_catchall': True,
            'email_validation_service': 'neverbounce',
            'email_source': 'website_scrape'
        },
        {
            'institution_name': 'NYU Law School',
            'state': 'NY',
            'program_type': 'Law School',
            'full_name': 'Alice Brown',
            'title': 'Coordinator',
            'matched_role': 'Program Coordinator',
            'email': 'alice@nyu.edu',
            'phone': '555-9999',
            'confidence_score': 45,
            'email_status': 'invalid',
            'email_is_catchall': False,
            'email_validation_service': 'zerobounce',
            'email_source': 'website_scrape'
        },
        {
            'institution_name': 'Texas Paralegal Program',
            'state': 'TX',
            'program_type': 'Paralegal Program',
            'full_name': 'Carlos Garcia',
            'title': 'Director',
            'matched_role': 'Program Director',
            'email': '',
            'phone': '555-7777',
            'confidence_score': 50,
            'email_status': 'no_email',
            'email_is_catchall': False,
            'email_validation_service': 'none',
            'email_source': 'none'
        },
        {
            'institution_name': 'California Paralegal Institute',
            'state': 'CA',
            'program_type': 'Paralegal Program',
            'full_name': 'Diana Lee',
            'title': 'Dean',
            'matched_role': 'Program Director',
            'email': 'diana@cpi.edu',
            'phone': '555-3333',
            'confidence_score': 90,
            'email_status': 'valid',
            'email_is_catchall': False,
            'email_validation_service': 'hunter',
            'email_source': 'hunter_io'
        }
    ])


@pytest.fixture
def sample_targets():
    """Create sample targets DataFrame for testing."""
    return pd.DataFrame([
        {'name': 'Stanford Law School', 'state': 'CA', 'type': 'Law School', 'url': 'https://law.stanford.edu'},
        {'name': 'UCLA Law School', 'state': 'CA', 'type': 'Law School', 'url': 'https://law.ucla.edu'},
        {'name': 'NYU Law School', 'state': 'NY', 'type': 'Law School', 'url': 'https://law.nyu.edu'},
        {'name': 'Texas Paralegal Program', 'state': 'TX', 'type': 'Paralegal Program', 'url': 'https://tx.para.edu'},
        {'name': 'California Paralegal Institute', 'state': 'CA', 'type': 'Paralegal Program', 'url': 'https://cpi.edu'},
        {'name': 'Failed Institution', 'state': 'CA', 'type': 'Law School', 'url': 'https://failed.edu'}  # No contacts
    ])


class TestGetStateBreakdown:
    """Test get_state_breakdown function."""

    def test_basic_state_counts(self, sample_contacts):
        """Test basic state breakdown."""
        result = get_state_breakdown(sample_contacts)

        # Check counts: Stanford (2) + UCLA (1) + CA Paralegal (1) = 4 for CA
        assert result['CA'] == 4
        assert result['NY'] == 1
        assert result['TX'] == 1
        # Most common should be first
        assert list(result.keys())[0] == 'CA'

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        result = get_state_breakdown(pd.DataFrame())
        assert result == {}

    def test_missing_state_column(self):
        """Test with DataFrame missing state column."""
        df = pd.DataFrame([{'name': 'John'}])
        result = get_state_breakdown(df)
        assert result == {}


class TestGetProgramTypeBreakdown:
    """Test get_program_type_breakdown function."""

    def test_basic_program_counts(self, sample_contacts):
        """Test basic program type breakdown."""
        result = get_program_type_breakdown(sample_contacts)

        assert 'Law School' in result
        assert 'Paralegal Program' in result
        assert result['Law School']['count'] == 4
        assert result['Paralegal Program']['count'] == 2
        assert result['Law School']['percentage'] == 66.7  # 4/6 * 100
        assert result['Paralegal Program']['percentage'] == 33.3  # 2/6 * 100

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        result = get_program_type_breakdown(pd.DataFrame())
        assert result == {}

    def test_missing_program_type_column(self):
        """Test with DataFrame missing program_type column."""
        df = pd.DataFrame([{'name': 'John'}])
        result = get_program_type_breakdown(df)
        assert result == {}


class TestGetEmailQualitySummary:
    """Test get_email_quality_summary function."""

    def test_comprehensive_email_stats(self, sample_contacts):
        """Test comprehensive email quality metrics."""
        result = get_email_quality_summary(sample_contacts)

        assert result['total_contacts'] == 6
        # All 6 contacts have email field (though one is empty string '')
        assert result['with_email'] == 6
        # Allow small rounding differences
        assert abs(result['email_coverage_pct'] - 100.0) < 0.2
        assert result['valid_deliverable'] == 3
        assert abs(result['valid_pct'] - 50.0) < 0.2  # 3/6 * 100
        assert result['catch_all'] == 1
        assert result['invalid'] == 1
        assert result.get('unknown', 0) == 0

    def test_validation_service_breakdown(self, sample_contacts):
        """Test validation service usage counts."""
        result = get_email_quality_summary(sample_contacts)

        services = result['validation_services']
        assert 'neverbounce' in services
        assert 'zerobounce' in services
        assert 'hunter' in services
        assert services['neverbounce'] == 2
        assert services['zerobounce'] == 2
        assert services['hunter'] == 1

    def test_email_source_breakdown(self, sample_contacts):
        """Test email source counts."""
        result = get_email_quality_summary(sample_contacts)

        sources = result['email_sources']
        assert 'website_scrape' in sources
        assert 'hunter_io' in sources
        assert sources['website_scrape'] == 4
        assert sources['hunter_io'] == 1

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        result = get_email_quality_summary(pd.DataFrame())
        assert result['total_contacts'] == 0
        assert result['with_email'] == 0
        assert result['email_coverage_pct'] == 0.0


class TestGetConfidenceDistribution:
    """Test get_confidence_distribution function."""

    def test_confidence_buckets(self, sample_contacts):
        """Test confidence score distribution buckets."""
        result = get_confidence_distribution(sample_contacts)

        assert result['high']['count'] == 3  # 90, 80, 75
        assert result['high']['percentage'] == 50.0  # 3/6 * 100
        assert result['medium']['count'] == 2  # 60, 50
        assert result['medium']['percentage'] == 33.3  # 2/6 * 100
        assert result['low']['count'] == 1  # 45
        assert result['low']['percentage'] == 16.7  # 1/6 * 100

    def test_confidence_statistics(self, sample_contacts):
        """Test confidence score statistics."""
        result = get_confidence_distribution(sample_contacts)

        # Scores: 80, 75, 60, 45, 50, 90
        assert result['average_score'] == 66.7  # (80+75+60+45+50+90)/6
        assert result['median_score'] == 67  # Median of [45, 50, 60, 75, 80, 90]
        assert result['min_score'] == 45
        assert result['max_score'] == 90

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        result = get_confidence_distribution(pd.DataFrame())

        assert result['high']['count'] == 0
        assert result['medium']['count'] == 0
        assert result['low']['count'] == 0


class TestGetTopRoles:
    """Test get_top_roles function."""

    def test_basic_role_counts(self, sample_contacts):
        """Test basic top roles counting."""
        result = get_top_roles(sample_contacts, top_n=5)

        assert len(result) == 5  # Should return top 5
        assert result[0]['role'] == 'Program Director'  # Most common (2 occurrences)
        assert result[0]['count'] == 2

    def test_limit_top_n(self, sample_contacts):
        """Test limiting results to top N."""
        result = get_top_roles(sample_contacts, top_n=3)
        assert len(result) == 3

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        result = get_top_roles(pd.DataFrame())
        assert result == []

    def test_uses_matched_role_over_title(self):
        """Test that matched_role is preferred over title."""
        df = pd.DataFrame([
            {'title': 'Professor', 'matched_role': 'Library Director'},
            {'title': 'Dean', 'matched_role': 'Library Director'}
        ])
        result = get_top_roles(df)

        assert len(result) == 1
        assert result[0]['role'] == 'Library Director'
        assert result[0]['count'] == 2


class TestCalculateScrapingSuccessRate:
    """Test calculate_scraping_success_rate function."""

    def test_success_rate_with_targets(self, sample_contacts, sample_targets):
        """Test success rate calculation with targets DataFrame."""
        result = calculate_scraping_success_rate(sample_contacts, sample_targets)

        assert result['total_institutions_attempted'] == 6
        assert result['successful_extractions'] == 5  # 5 unique institutions in contacts
        assert result['failed_extractions'] == 1  # Failed Institution
        assert result['success_rate_pct'] == 83.3  # 5/6 * 100

    def test_contact_count_buckets(self, sample_contacts, sample_targets):
        """Test institution grouping by contact count."""
        result = calculate_scraping_success_rate(sample_contacts, sample_targets)

        buckets = result['institutions_by_contact_count']
        # Stanford has 2 contacts, UCLA has 1, NYU has 1, TX Paralegal has 1, CA Paralegal has 1
        # All institutions have 1-2 contacts
        assert buckets['1-2 contacts'] == 5  # All 5 successful institutions
        assert buckets.get('3-5 contacts', 0) == 0
        assert buckets.get('6-10 contacts', 0) == 0
        assert buckets.get('11+ contacts', 0) == 0

    def test_without_targets(self, sample_contacts):
        """Test success rate without targets DataFrame."""
        result = calculate_scraping_success_rate(sample_contacts, None)

        # Without targets, assumes all institutions in contacts were attempted
        assert result['total_institutions_attempted'] == 5
        assert result['successful_extractions'] == 5
        assert result['failed_extractions'] == 0
        assert result['success_rate_pct'] == 100.0

    def test_empty_contacts(self):
        """Test with empty contacts DataFrame."""
        result = calculate_scraping_success_rate(pd.DataFrame(), None)

        assert result['total_institutions_attempted'] == 0
        assert result['successful_extractions'] == 0
        assert result['failed_extractions'] == 0
        assert result['success_rate_pct'] == 0.0


class TestCalculateContactStatistics:
    """Test calculate_contact_statistics main orchestrator function."""

    def test_comprehensive_statistics(self, sample_contacts, sample_targets):
        """Test that all statistics are calculated."""
        result = calculate_contact_statistics(sample_contacts, sample_targets)

        # Check all expected keys exist
        assert 'summary' in result
        assert 'by_state' in result
        assert 'by_program_type' in result
        assert 'email_quality' in result
        assert 'confidence_distribution' in result
        assert 'top_roles' in result
        assert 'scraping_success' in result

    def test_summary_stats(self, sample_contacts, sample_targets):
        """Test summary statistics."""
        result = calculate_contact_statistics(sample_contacts, sample_targets)

        summary = result['summary']
        assert summary['total_contacts'] == 6
        assert summary['total_institutions'] == 5
        assert summary['avg_contacts_per_institution'] == 1.2  # 6/5

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        result = calculate_contact_statistics(pd.DataFrame(), None)

        assert result['summary']['total_contacts'] == 0
        assert result['summary']['total_institutions'] == 0
        assert result['summary']['avg_contacts_per_institution'] == 0.0
