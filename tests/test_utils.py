"""
Tests for utility functions.
"""

import pytest
import time
import pandas as pd
from pathlib import Path

from modules.utils import (
    validate_url,
    normalize_url,
    extract_domain,
    clean_text,
    extract_email,
    extract_phone,
    parse_name,
    adaptive_delay,
    rate_limit,
)


# =============================================================================
# URL Utilities Tests
# =============================================================================

def test_validate_url():
    """Test URL validation."""
    assert validate_url('https://example.com') is True
    assert validate_url('http://example.com/path') is True
    assert validate_url('not a url') is False
    assert validate_url('') is False


def test_normalize_url():
    """Test URL normalization."""
    assert normalize_url('example.com') == 'https://example.com'
    assert normalize_url('http://example.com/') == 'http://example.com'
    assert normalize_url('https://example.com/path/') == 'https://example.com/path'
    assert normalize_url('  example.com  ') == 'https://example.com'


def test_extract_domain():
    """Test domain extraction."""
    assert extract_domain('https://www.example.com/path') == 'www.example.com'
    assert extract_domain('http://example.com') == 'example.com'
    assert extract_domain('example.com') == 'example.com'


# =============================================================================
# Text Processing Tests
# =============================================================================

def test_clean_text():
    """Test text cleaning."""
    assert clean_text('  hello   world  ') == 'hello world'
    assert clean_text('hello\xa0world') == 'hello world'
    assert clean_text('') == ''
    assert clean_text(None) == ''


def test_extract_email():
    """Test email extraction."""
    assert extract_email('Contact: john@example.com') == 'john@example.com'
    assert extract_email('Email me at test.user+tag@domain.co.uk') == 'test.user+tag@domain.co.uk'
    assert extract_email('No email here') is None
    assert extract_email('') is None


def test_extract_phone():
    """Test phone number extraction."""
    assert extract_phone('Call (555) 123-4567') == '(555) 123-4567'
    assert extract_phone('Phone: 555-123-4567') == '555-123-4567'
    assert extract_phone('555.123.4567') == '555.123.4567'
    assert extract_phone('No phone here') is None


def test_parse_name():
    """Test name parsing."""
    assert parse_name('John Doe') == {'first_name': 'John', 'last_name': 'Doe'}
    assert parse_name('John Q. Public Doe') == {'first_name': 'John', 'last_name': 'Doe'}
    assert parse_name('Madonna') == {'first_name': 'Madonna', 'last_name': ''}
    assert parse_name('') == {'first_name': '', 'last_name': ''}


# =============================================================================
# Rate Limiting Tests
# =============================================================================

def test_rate_limit_decorator():
    """Test rate limiting decorator."""
    call_times = []

    @rate_limit(calls=2, period=1.0)  # Max 2 calls per second (min 0.5s interval)
    def test_function():
        call_times.append(time.time())

    # Make 3 calls
    test_function()
    test_function()
    test_function()

    # Check that calls were rate limited
    assert len(call_times) == 3

    # Each call should be delayed by ~0.5 seconds (1.0 period / 2 calls)
    # Allow some tolerance for execution time
    assert call_times[1] - call_times[0] >= 0.4
    assert call_times[2] - call_times[1] >= 0.4


def test_adaptive_delay():
    """Test adaptive delay calculation."""
    # Good performance - should speed up
    delay1 = adaptive_delay(5.0, success_rate=0.96, avg_response_time=1.5, min_delay=2.0, max_delay=10.0)
    assert delay1 < 5.0
    assert delay1 >= 2.0

    # Poor performance - should slow down
    delay2 = adaptive_delay(5.0, success_rate=0.75, avg_response_time=6.0, min_delay=2.0, max_delay=10.0)
    assert delay2 > 5.0
    assert delay2 <= 10.0

    # Moderate performance - should stay same
    delay3 = adaptive_delay(5.0, success_rate=0.90, avg_response_time=3.0, min_delay=2.0, max_delay=10.0)
    assert delay3 == 5.0


# =============================================================================
# Caching Tests
# =============================================================================

def test_cache_to_file_and_load(tmp_path):
    """Test caching and loading DataFrames."""
    from modules.utils import cache_to_file, load_cached_file

    # Create test DataFrame
    df = pd.DataFrame({
        'name': ['Alice', 'Bob'],
        'email': ['alice@example.com', 'bob@example.com']
    })

    # Cache it
    filename = 'test_cache.csv'
    cache_to_file(df, filename, output_dir=tmp_path)

    # Load it back
    loaded_df = load_cached_file(filename, cache_dir=tmp_path, max_age_hours=24)

    assert loaded_df is not None
    assert len(loaded_df) == 2
    assert list(loaded_df.columns) == ['name', 'email']


def test_cache_miss(tmp_path):
    """Test that missing cache returns None."""
    from modules.utils import load_cached_file

    # Try to load non-existent cache
    loaded_df = load_cached_file('nonexistent.csv', cache_dir=tmp_path)

    # Should return None because cache doesn't exist
    assert loaded_df is None


# =============================================================================
# File Utilities Tests
# =============================================================================

def test_save_dataframe(tmp_path):
    """Test saving DataFrame with timestamp."""
    from modules.utils import save_dataframe

    df = pd.DataFrame({'col1': [1, 2], 'col2': [3, 4]})

    # Save without timestamp
    path1 = save_dataframe(df, 'test.csv', output_dir=tmp_path, add_timestamp=False)
    assert path1.name == 'test.csv'
    assert path1.exists()

    # Save with timestamp
    path2 = save_dataframe(df, 'test.csv', output_dir=tmp_path, add_timestamp=True)
    assert 'test_' in path2.name
    assert path2.name.endswith('.csv')
    assert path2.exists()


def test_get_timestamp():
    """Test timestamp generation."""
    from modules.utils import get_timestamp

    ts = get_timestamp()
    assert len(ts) == 15  # Format: YYYYMMDD_HHMMSS
    assert '_' in ts
