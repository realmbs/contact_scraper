"""
Tests for configuration system.
"""

import pytest
from pathlib import Path


def test_config_loads_without_error():
    """Test that configuration loads without errors."""
    from config import settings
    assert settings.BASE_DIR.exists()
    assert settings.OUTPUT_DIR.exists()
    assert settings.LOGS_DIR.exists()
    assert settings.CACHE_DIR.exists()


def test_directories_exist():
    """Test that required directories were created."""
    from config.settings import OUTPUT_DIR, LOGS_DIR, CACHE_DIR
    assert OUTPUT_DIR.is_dir()
    assert LOGS_DIR.is_dir()
    assert CACHE_DIR.is_dir()


def test_api_availability_dict():
    """Test that APIS_AVAILABLE is properly structured."""
    from config.settings import APIS_AVAILABLE
    assert isinstance(APIS_AVAILABLE, dict)
    assert 'hunter' in APIS_AVAILABLE
    assert 'zerobounce' in APIS_AVAILABLE
    assert 'neverbounce' in APIS_AVAILABLE
    assert 'proxycurl' in APIS_AVAILABLE


def test_scraping_config_values():
    """Test that scraping configuration has valid values."""
    from config.settings import (
        RATE_LIMIT_DELAY,
        MIN_DELAY,
        MAX_DELAY,
        MAX_CONCURRENT_REQUESTS,
        REQUEST_TIMEOUT,
    )
    assert RATE_LIMIT_DELAY > 0
    assert MIN_DELAY > 0
    assert MAX_DELAY > MIN_DELAY
    assert MAX_CONCURRENT_REQUESTS > 0
    assert REQUEST_TIMEOUT > 0


def test_confidence_scores():
    """Test that confidence score thresholds are valid."""
    from config.settings import MIN_CONFIDENCE_SCORE, MIN_EMAIL_SCORE
    assert 0 <= MIN_CONFIDENCE_SCORE <= 100
    assert 0 <= MIN_EMAIL_SCORE <= 100


def test_target_roles_defined():
    """Test that target roles are properly defined."""
    from config.settings import LAW_SCHOOL_ROLES, PARALEGAL_PROGRAM_ROLES, ALL_TARGET_ROLES
    assert len(LAW_SCHOOL_ROLES) > 0
    assert len(PARALEGAL_PROGRAM_ROLES) > 0
    assert len(ALL_TARGET_ROLES) == len(LAW_SCHOOL_ROLES) + len(PARALEGAL_PROGRAM_ROLES)


def test_validate_config_runs():
    """Test that validate_config() runs without errors."""
    from config.settings import validate_config
    assert validate_config() is True


def test_api_clients_module_loads():
    """Test that API clients module loads without errors."""
    from config import api_clients
    assert hasattr(api_clients, 'get_hunter_client')
    assert hasattr(api_clients, 'get_api_status')


def test_api_status_function():
    """Test that get_api_status returns proper structure."""
    from config.api_clients import get_api_status
    status = get_api_status()
    assert isinstance(status, dict)
    assert 'hunter' in status
    assert isinstance(status['hunter'], bool)
