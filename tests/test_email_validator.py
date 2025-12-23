"""
Unit tests for email validation and enrichment module.

Test Coverage:
- Email validation (ZeroBounce, NeverBounce, Hunter)
- Email finding (Hunter.io, pattern construction)
- Catch-all detection
- Batch processing
- Graceful degradation without API keys
- Error handling and retries
- Score mapping and status normalization
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
import requests

from modules.email_validator import (
    validate_email_zerobounce,
    validate_email_neverbounce,
    validate_email_auto,
    batch_validate_emails,
    find_missing_emails,
    enrich_contact_data,
    is_catchall_domain,
    check_zerobounce_credits,
    _map_zerobounce_score,
    _map_neverbounce_status,
    _map_neverbounce_score,
)


# ============================================================================
# Test Fixtures - Mock API Responses
# ============================================================================

@pytest.fixture
def mock_zerobounce_valid():
    """Mock ZeroBounce API response for valid email."""
    return {
        'status': 'valid',
        'sub_status': '',
        'free_email': False,
        'mx_found': True,
        'smtp_provider': 'google',
        'firstname': 'John',
        'lastname': 'Doe',
    }


@pytest.fixture
def mock_zerobounce_invalid():
    """Mock ZeroBounce API response for invalid email."""
    return {
        'status': 'invalid',
        'sub_status': 'mailbox_not_found',
        'free_email': False,
        'mx_found': False,
    }


@pytest.fixture
def mock_zerobounce_catchall():
    """Mock ZeroBounce API response for catch-all domain."""
    return {
        'status': 'catch-all',
        'sub_status': '',
        'free_email': False,
        'mx_found': True,
    }


@pytest.fixture
def mock_neverbounce_valid():
    """Mock NeverBounce API response for valid email."""
    return {
        'status': 'success',
        'result': 0,  # Valid
        'address_info': {
            'free_email_host': False
        },
        'credits_info': {
            'free_credits_remaining': 950
        }
    }


@pytest.fixture
def mock_neverbounce_invalid():
    """Mock NeverBounce API response for invalid email."""
    return {
        'status': 'success',
        'result': 1,  # Invalid
        'address_info': {
            'free_email_host': False
        },
        'credits_info': {
            'free_credits_remaining': 949
        }
    }


@pytest.fixture
def mock_neverbounce_catchall():
    """Mock NeverBounce API response for catch-all domain."""
    return {
        'status': 'success',
        'result': 3,  # Catch-all
        'address_info': {
            'free_email_host': False
        },
        'credits_info': {
            'free_credits_remaining': 948
        }
    }


@pytest.fixture
def sample_contacts_no_emails():
    """Contacts missing emails for testing email finding."""
    return pd.DataFrame([
        {
            'first_name': 'John',
            'last_name': 'Doe',
            'title': 'Professor of Law',
            'institution_url': 'https://law.stanford.edu',
            'email': '',
            'confidence_score': 50
        },
        {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'title': 'Associate Dean',
            'institution_url': 'https://law.stanford.edu',
            'email': '',
            'confidence_score': 50
        },
    ])


@pytest.fixture
def sample_contacts_with_emails():
    """Contacts with emails for testing validation."""
    return pd.DataFrame([
        {
            'first_name': 'John',
            'last_name': 'Doe',
            'title': 'Professor of Law',
            'institution_url': 'https://law.stanford.edu',
            'email': 'jdoe@stanford.edu',
            'confidence_score': 50
        },
        {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'title': 'Associate Dean',
            'institution_url': 'https://law.stanford.edu',
            'email': 'jsmith@stanford.edu',
            'confidence_score': 50
        },
    ])


# ============================================================================
# Test Score Mapping Functions
# ============================================================================

class TestScoreMapping:
    """Test validation score mapping functions."""

    def test_zerobounce_valid_score(self, mock_zerobounce_valid):
        """Test ZeroBounce valid email scores 100."""
        score = _map_zerobounce_score(mock_zerobounce_valid)
        assert score == 100

    def test_zerobounce_invalid_score(self, mock_zerobounce_invalid):
        """Test ZeroBounce invalid email scores 0."""
        score = _map_zerobounce_score(mock_zerobounce_invalid)
        assert score == 0

    def test_zerobounce_catchall_score(self, mock_zerobounce_catchall):
        """Test ZeroBounce catch-all email scores 70."""
        score = _map_zerobounce_score(mock_zerobounce_catchall)
        assert score == 70

    def test_neverbounce_status_mapping(self):
        """Test NeverBounce result code to status mapping."""
        assert _map_neverbounce_status(0) == 'valid'
        assert _map_neverbounce_status(1) == 'invalid'
        assert _map_neverbounce_status(2) == 'disposable'
        assert _map_neverbounce_status(3) == 'catch-all'
        assert _map_neverbounce_status(4) == 'unknown'

    def test_neverbounce_valid_score(self, mock_neverbounce_valid):
        """Test NeverBounce valid email scores 100."""
        score = _map_neverbounce_score(mock_neverbounce_valid)
        assert score == 100

    def test_neverbounce_invalid_score(self, mock_neverbounce_invalid):
        """Test NeverBounce invalid email scores 0."""
        score = _map_neverbounce_score(mock_neverbounce_invalid)
        assert score == 0

    def test_neverbounce_catchall_score(self, mock_neverbounce_catchall):
        """Test NeverBounce catch-all email scores 70."""
        score = _map_neverbounce_score(mock_neverbounce_catchall)
        assert score == 70


# ============================================================================
# Test ZeroBounce Validation
# ============================================================================

class TestZeroBounceValidation:
    """Test ZeroBounce email validation."""

    @patch('modules.email_validator.requests.get')
    def test_validate_valid_email(self, mock_get, mock_zerobounce_valid):
        """Test validating a valid email with ZeroBounce."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = mock_zerobounce_valid
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test validation
        result = validate_email_zerobounce('test@example.com', api_key='test_key')

        assert result is not None
        assert result['email'] == 'test@example.com'
        assert result['status'] == 'valid'
        assert result['score'] == 100
        assert result['is_catchall'] is False
        assert result['service'] == 'zerobounce'

    @patch('modules.email_validator.requests.get')
    def test_validate_invalid_email(self, mock_get, mock_zerobounce_invalid):
        """Test validating an invalid email with ZeroBounce."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = mock_zerobounce_invalid
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test validation
        result = validate_email_zerobounce('invalid@example.com', api_key='test_key')

        assert result is not None
        assert result['status'] == 'invalid'
        assert result['score'] == 0

    @patch('modules.email_validator.requests.get')
    def test_validate_catchall_email(self, mock_get, mock_zerobounce_catchall):
        """Test validating a catch-all domain with ZeroBounce."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = mock_zerobounce_catchall
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Test validation
        result = validate_email_zerobounce('anything@catchall.com', api_key='test_key')

        assert result is not None
        assert result['status'] == 'catch-all'
        assert result['score'] == 70
        assert result['is_catchall'] is True

    def test_validate_without_api_key(self):
        """Test graceful degradation when API key not configured."""
        result = validate_email_zerobounce('test@example.com', api_key=None)
        assert result is None

    @patch('modules.email_validator.requests.get')
    def test_validate_api_timeout(self, mock_get):
        """Test handling of API timeout."""
        mock_get.side_effect = requests.exceptions.Timeout()

        result = validate_email_zerobounce('test@example.com', api_key='test_key')
        assert result is None

    @patch('modules.email_validator.requests.get')
    def test_validate_api_error(self, mock_get):
        """Test handling of API error response."""
        mock_response = Mock()
        mock_response.json.return_value = {'error': 'Invalid API key'}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = validate_email_zerobounce('test@example.com', api_key='test_key')
        assert result is None


# ============================================================================
# Test NeverBounce Validation
# ============================================================================

class TestNeverBounceValidation:
    """Test NeverBounce email validation."""

    @patch('modules.email_validator.requests.post')
    def test_validate_valid_email(self, mock_post, mock_neverbounce_valid):
        """Test validating a valid email with NeverBounce."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = mock_neverbounce_valid
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Test validation
        result = validate_email_neverbounce('test@example.com', api_key='test_key')

        assert result is not None
        assert result['email'] == 'test@example.com'
        assert result['status'] == 'valid'
        assert result['score'] == 100
        assert result['is_catchall'] is False
        assert result['service'] == 'neverbounce'

    @patch('modules.email_validator.requests.post')
    def test_validate_invalid_email(self, mock_post, mock_neverbounce_invalid):
        """Test validating an invalid email with NeverBounce."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = mock_neverbounce_invalid
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Test validation
        result = validate_email_neverbounce('invalid@example.com', api_key='test_key')

        assert result is not None
        assert result['status'] == 'invalid'
        assert result['score'] == 0

    @patch('modules.email_validator.requests.post')
    def test_validate_catchall_email(self, mock_post, mock_neverbounce_catchall):
        """Test validating a catch-all domain with NeverBounce."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = mock_neverbounce_catchall
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Test validation
        result = validate_email_neverbounce('anything@catchall.com', api_key='test_key')

        assert result is not None
        assert result['status'] == 'catch-all'
        assert result['score'] == 70
        assert result['is_catchall'] is True

    def test_validate_without_api_key(self):
        """Test graceful degradation when API key not configured."""
        result = validate_email_neverbounce('test@example.com', api_key=None)
        assert result is None

    @patch('modules.email_validator.requests.post')
    def test_validate_api_failed_status(self, mock_post):
        """Test handling of failed API status."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'status': 'failed',
            'message': 'Invalid API key'
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = validate_email_neverbounce('test@example.com', api_key='test_key')
        assert result is None


# ============================================================================
# Test Batch Validation
# ============================================================================

class TestBatchValidation:
    """Test batch email validation."""

    @patch('modules.email_validator.validate_email_auto')
    def test_batch_validate_multiple_emails(self, mock_validate):
        """Test batch validation of multiple emails."""
        # Mock validation results
        mock_validate.side_effect = [
            {'email': 'test1@example.com', 'status': 'valid', 'score': 100, 'is_catchall': False, 'is_disposable': False, 'service': 'neverbounce'},
            {'email': 'test2@example.com', 'status': 'invalid', 'score': 0, 'is_catchall': False, 'is_disposable': False, 'service': 'neverbounce'},
            {'email': 'test3@example.com', 'status': 'catch-all', 'score': 70, 'is_catchall': True, 'is_disposable': False, 'service': 'zerobounce'},
        ]

        emails = ['test1@example.com', 'test2@example.com', 'test3@example.com']
        result_df = batch_validate_emails(emails, service='auto')

        assert len(result_df) == 3
        assert result_df.iloc[0]['status'] == 'valid'
        assert result_df.iloc[1]['status'] == 'invalid'
        assert result_df.iloc[2]['is_catchall'] == True

    def test_batch_validate_empty_list(self):
        """Test batch validation with empty email list."""
        result_df = batch_validate_emails([])
        assert result_df.empty

    @patch('modules.email_validator.validate_email_auto')
    def test_batch_validate_with_none_values(self, mock_validate):
        """Test batch validation handles None/empty values gracefully."""
        emails = ['test@example.com', None, '', 'test2@example.com']

        mock_validate.side_effect = [
            {'email': 'test@example.com', 'status': 'valid', 'score': 100, 'is_catchall': False, 'is_disposable': False, 'service': 'neverbounce'},
            {'email': 'test2@example.com', 'status': 'valid', 'score': 100, 'is_catchall': False, 'is_disposable': False, 'service': 'neverbounce'},
        ]

        result_df = batch_validate_emails(emails)

        # Should only validate non-empty emails
        assert len(result_df) == 2


# ============================================================================
# Test Catch-all Detection
# ============================================================================

class TestCatchallDetection:
    """Test catch-all domain detection."""

    def test_catchall_from_validation_result(self):
        """Test catch-all detection from validation result."""
        validation_result = {
            'is_catchall': True,
            'status': 'catch-all'
        }
        assert is_catchall_domain('example.com', validation_result) is True

    def test_non_catchall_from_validation_result(self):
        """Test non-catch-all domain from validation result."""
        validation_result = {
            'is_catchall': False,
            'status': 'valid'
        }
        assert is_catchall_domain('example.com', validation_result) is False

    def test_catchall_without_validation_result(self):
        """Test catch-all detection without validation result."""
        # Without testing (to avoid API calls), should return False
        assert is_catchall_domain('example.com', None) is False


# ============================================================================
# Test Email Finding
# ============================================================================

class TestEmailFinding:
    """Test email finding functionality."""

    @patch('modules.email_validator.find_email_with_hunter')
    def test_find_missing_emails_with_hunter(self, mock_hunter, sample_contacts_no_emails):
        """Test finding emails via Hunter.io."""
        # Mock Hunter.io responses
        mock_hunter.side_effect = [
            'jdoe@law.stanford.edu',
            'jsmith@law.stanford.edu'
        ]

        result_df = find_missing_emails(sample_contacts_no_emails)

        # Should have found both emails
        assert result_df.iloc[0]['email'] == 'jdoe@law.stanford.edu'
        assert result_df.iloc[1]['email'] == 'jsmith@law.stanford.edu'
        assert result_df.iloc[0]['email_source'] == 'hunter_io'
        assert result_df.iloc[1]['email_source'] == 'hunter_io'

        # Confidence scores should be increased (+20)
        assert result_df.iloc[0]['confidence_score'] == 70
        assert result_df.iloc[1]['confidence_score'] == 70

    @patch('modules.email_validator.find_email_with_hunter')
    def test_find_missing_emails_hunter_not_found(self, mock_hunter, sample_contacts_no_emails):
        """Test handling when Hunter.io doesn't find emails."""
        # Mock Hunter.io returning None
        mock_hunter.return_value = None

        result_df = find_missing_emails(sample_contacts_no_emails)

        # Emails should still be empty
        assert result_df.iloc[0]['email'] == ''
        assert result_df.iloc[1]['email'] == ''

    def test_find_missing_emails_already_have_emails(self, sample_contacts_with_emails):
        """Test that contacts with emails are not modified."""
        original_emails = sample_contacts_with_emails['email'].tolist()
        result_df = find_missing_emails(sample_contacts_with_emails)

        assert result_df['email'].tolist() == original_emails

    def test_find_missing_emails_empty_dataframe(self):
        """Test handling of empty DataFrame."""
        empty_df = pd.DataFrame()
        result_df = find_missing_emails(empty_df)
        assert result_df.empty


# ============================================================================
# Test Contact Enrichment Pipeline
# ============================================================================

class TestContactEnrichment:
    """Test full contact enrichment pipeline."""

    @patch('modules.email_validator.batch_validate_emails')
    @patch('modules.email_validator.find_missing_emails')
    def test_enrich_full_pipeline(self, mock_find, mock_validate, sample_contacts_with_emails):
        """Test complete enrichment pipeline."""
        # Mock find_missing_emails (no changes since emails already present)
        mock_find.return_value = sample_contacts_with_emails

        # Mock batch validation
        mock_validate.return_value = pd.DataFrame([
            {
                'email': 'jdoe@stanford.edu',
                'status': 'valid',
                'score': 100,
                'is_catchall': False,
                'is_disposable': False,
                'service': 'neverbounce'
            },
            {
                'email': 'jsmith@stanford.edu',
                'status': 'valid',
                'score': 100,
                'is_catchall': False,
                'is_disposable': False,
                'service': 'neverbounce'
            },
        ])

        result_df = enrich_contact_data(sample_contacts_with_emails)

        # Should have validation columns
        assert 'email_status' in result_df.columns
        assert 'email_score' in result_df.columns
        assert 'email_is_catchall' in result_df.columns

        # Should have updated confidence scores (+30 for valid emails)
        assert result_df.iloc[0]['confidence_score'] == 80
        assert result_df.iloc[1]['confidence_score'] == 80

    def test_enrich_empty_dataframe(self):
        """Test enrichment with empty DataFrame."""
        empty_df = pd.DataFrame()
        result_df = enrich_contact_data(empty_df)
        assert result_df.empty

    @patch('modules.email_validator.batch_validate_emails')
    @patch('modules.email_validator.find_missing_emails')
    def test_enrich_catchall_penalty(self, mock_find, mock_validate):
        """Test confidence score penalty for catch-all domains."""
        # Create sample contacts
        contacts = pd.DataFrame([
            {
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'jdoe@catchall.edu',
                'confidence_score': 50
            }
        ])

        mock_find.return_value = contacts

        # Mock validation with catch-all result
        mock_validate.return_value = pd.DataFrame([
            {
                'email': 'jdoe@catchall.edu',
                'status': 'catch-all',
                'score': 70,
                'is_catchall': True,
                'is_disposable': False,
                'service': 'zerobounce'
            }
        ])

        result_df = enrich_contact_data(contacts)

        # Confidence score should be reduced (-20 for catch-all)
        assert result_df.iloc[0]['confidence_score'] == 30  # 50 - 20


# ============================================================================
# Test API Credit Management
# ============================================================================

class TestCreditManagement:
    """Test API credit checking."""

    @patch('modules.email_validator.requests.get')
    def test_check_zerobounce_credits(self, mock_get):
        """Test checking ZeroBounce credits."""
        mock_response = Mock()
        mock_response.json.return_value = {'Credits': '1500'}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        credits = check_zerobounce_credits(api_key='test_key')
        assert credits == 1500

    def test_check_credits_without_api_key(self):
        """Test credit check without API key."""
        credits = check_zerobounce_credits(api_key=None)
        assert credits is None

    @patch('modules.email_validator.requests.get')
    def test_check_credits_api_error(self, mock_get):
        """Test handling of API error when checking credits."""
        mock_get.side_effect = requests.exceptions.RequestException()

        credits = check_zerobounce_credits(api_key='test_key')
        assert credits is None
