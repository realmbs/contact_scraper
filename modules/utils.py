"""
Utility functions for Legal Education Contact Scraper.

Provides logging setup, caching, rate limiting, and common helper functions.
"""

import time
import re
import sys
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
from typing import Optional, Callable, Any
from urllib.parse import urlparse, urljoin

import pandas as pd
from loguru import logger

from config.settings import (
    LOGS_DIR,
    OUTPUT_DIR,
    CACHE_DIR,
    LOG_LEVEL,
    LOG_MAX_SIZE,
    LOG_BACKUP_COUNT,
    ENABLE_CACHING,
    CACHE_EXPIRATION_HOURS,
)


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logger(name: str = "scraper", log_file: Optional[str] = None) -> logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name
        log_file: Optional custom log file name (default: scraper_YYYYMMDD.log)

    Returns:
        Configured logger instance
    """
    # Remove default logger
    logger.remove()

    # Console handler with colored output (only colorize if stdout is a TTY)
    # This prevents ANSI escape codes from polluting piped output (e.g., tee, redirects)
    is_tty = sys.stdout.isatty()

    logger.add(
        sink=lambda msg: print(msg, end=''),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=LOG_LEVEL,
        colorize=is_tty,  # Only colorize for interactive terminals
    )

    # File handler with rotation
    if log_file is None:
        log_file = f"scraper_{datetime.now().strftime('%Y%m%d')}.log"

    log_path = LOGS_DIR / log_file

    logger.add(
        sink=log_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level=LOG_LEVEL,
        rotation=LOG_MAX_SIZE,
        retention=LOG_BACKUP_COUNT,
        compression="zip",
    )

    logger.info(f"Logger initialized: {name}")
    logger.info(f"Log file: {log_path}")
    logger.info(f"Log level: {LOG_LEVEL}")

    return logger


# =============================================================================
# Rate Limiting
# =============================================================================

def rate_limit(calls: int = 1, period: float = 1.0):
    """
    Decorator to rate limit function calls.

    Args:
        calls: Number of calls allowed
        period: Time period in seconds

    Example:
        @rate_limit(calls=5, period=1.0)  # Max 5 calls per second
        def scrape_page(url):
            ...
    """
    min_interval = period / calls
    last_called = [0.0]

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            wait_time = min_interval - elapsed

            if wait_time > 0:
                logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
                time.sleep(wait_time)

            last_called[0] = time.time()
            return func(*args, **kwargs)

        return wrapper
    return decorator


def adaptive_delay(
    base_delay: float,
    success_rate: float,
    avg_response_time: float,
    min_delay: float = 2.0,
    max_delay: float = 10.0
) -> float:
    """
    Calculate adaptive delay based on success rate and response time.

    Args:
        base_delay: Current delay in seconds
        success_rate: Success rate (0.0 to 1.0)
        avg_response_time: Average response time in seconds
        min_delay: Minimum delay
        max_delay: Maximum delay

    Returns:
        Adjusted delay in seconds
    """
    if success_rate > 0.95 and avg_response_time < 2.0:
        # Speed up if performing well
        new_delay = max(min_delay, base_delay * 0.8)
        logger.debug(f"Adaptive delay: speeding up to {new_delay:.2f}s")
    elif success_rate < 0.8 or avg_response_time > 5.0:
        # Slow down if encountering issues
        new_delay = min(max_delay, base_delay * 1.5)
        logger.warning(f"Adaptive delay: slowing down to {new_delay:.2f}s")
    else:
        new_delay = base_delay

    return new_delay


# =============================================================================
# Caching
# =============================================================================

def cache_to_file(data: pd.DataFrame, filename: str, output_dir: Path = CACHE_DIR) -> Path:
    """
    Cache DataFrame to CSV file.

    Args:
        data: DataFrame to cache
        filename: Output filename (without path)
        output_dir: Directory to save file (default: CACHE_DIR)

    Returns:
        Path to cached file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / filename

    data.to_csv(file_path, index=False)
    logger.info(f"Cached {len(data)} records to {file_path}")

    return file_path


def load_cached_file(
    filename: str,
    cache_dir: Path = CACHE_DIR,
    max_age_hours: Optional[int] = None
) -> Optional[pd.DataFrame]:
    """
    Load cached CSV file if it exists and is not too old.

    Args:
        filename: Filename to load
        cache_dir: Directory containing cache
        max_age_hours: Maximum age in hours (None = use config default)

    Returns:
        DataFrame if cache is valid, None otherwise
    """
    if not ENABLE_CACHING:
        logger.debug("Caching disabled in config")
        return None

    file_path = cache_dir / filename

    if not file_path.exists():
        logger.debug(f"Cache miss: {filename}")
        return None

    # Check file age
    file_age = datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)
    max_age = timedelta(hours=max_age_hours or CACHE_EXPIRATION_HOURS)

    if file_age >= max_age:
        logger.info(f"Cache expired: {filename} (age: {file_age})")
        return None

    try:
        data = pd.read_csv(file_path)
        logger.success(f"Cache hit: {filename} ({len(data)} records)")
        return data
    except Exception as e:
        logger.error(f"Failed to load cache {filename}: {e}")
        return None


def clear_cache(cache_dir: Path = CACHE_DIR, older_than_hours: Optional[int] = None):
    """
    Clear cached files.

    Args:
        cache_dir: Directory containing cache
        older_than_hours: Only delete files older than this (None = delete all)
    """
    if not cache_dir.exists():
        return

    deleted = 0
    for file_path in cache_dir.glob('*.csv'):
        if older_than_hours:
            file_age = datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)
            if file_age < timedelta(hours=older_than_hours):
                continue

        file_path.unlink()
        deleted += 1

    logger.info(f"Cleared {deleted} cached files from {cache_dir}")


# =============================================================================
# URL Utilities
# =============================================================================

def validate_url(url: str) -> bool:
    """
    Validate that a URL is well-formed.

    Args:
        url: URL to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """
    Normalize URL by ensuring scheme and removing trailing slashes.

    Args:
        url: URL to normalize

    Returns:
        Normalized URL
    """
    url = url.strip()

    # Add scheme if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Remove trailing slashes
    url = url.rstrip('/')

    return url


def extract_domain(url: str) -> str:
    """
    Extract domain from URL.

    Args:
        url: URL to extract domain from

    Returns:
        Domain (e.g., 'example.com')
    """
    parsed = urlparse(normalize_url(url))
    return parsed.netloc


# =============================================================================
# Text Processing
# =============================================================================

def clean_text(text: str) -> str:
    """
    Clean and normalize text.

    Args:
        text: Text to clean

    Returns:
        Cleaned text
    """
    if not text:
        return ''

    # Remove extra whitespace
    text = ' '.join(text.split())

    # Remove non-breaking spaces
    text = text.replace('\xa0', ' ')
    text = text.replace('\u200b', '')  # Zero-width space

    return text.strip()


def extract_email(text: str) -> Optional[str]:
    """
    Extract email address from text.

    Args:
        text: Text containing potential email

    Returns:
        Email address if found, None otherwise
    """
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(email_pattern, text)
    return match.group(0) if match else None


def extract_phone(text: str) -> Optional[str]:
    """
    Extract phone number from text.

    Args:
        text: Text containing potential phone number

    Returns:
        Phone number if found, None otherwise
    """
    # US phone number patterns
    phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
    match = re.search(phone_pattern, text)
    return match.group(0) if match else None


def parse_name(full_name: str) -> dict:
    """
    Parse full name into first and last name.

    Args:
        full_name: Full name to parse

    Returns:
        Dict with 'first_name' and 'last_name'
    """
    parts = clean_text(full_name).split()

    if len(parts) == 0:
        return {'first_name': '', 'last_name': ''}
    elif len(parts) == 1:
        return {'first_name': parts[0], 'last_name': ''}
    else:
        return {'first_name': parts[0], 'last_name': parts[-1]}


# =============================================================================
# File Utilities
# =============================================================================

def save_dataframe(
    df: pd.DataFrame,
    filename: str,
    output_dir: Path = OUTPUT_DIR,
    add_timestamp: bool = True
) -> Path:
    """
    Save DataFrame to CSV with optional timestamping.

    Args:
        df: DataFrame to save
        filename: Base filename
        output_dir: Output directory
        add_timestamp: Whether to add timestamp to filename

    Returns:
        Path to saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if add_timestamp:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = Path(filename).stem
        extension = Path(filename).suffix or '.csv'
        filename = f"{base_name}_{timestamp}{extension}"

    file_path = output_dir / filename
    df.to_csv(file_path, index=False)

    logger.success(f"Saved {len(df)} records to {file_path}")
    return file_path


def get_timestamp() -> str:
    """Get current timestamp string for filenames."""
    return datetime.now().strftime('%Y%m%d_%H%M%S')


# =============================================================================
# Export public API
# =============================================================================

__all__ = [
    'setup_logger',
    'rate_limit',
    'adaptive_delay',
    'cache_to_file',
    'load_cached_file',
    'clear_cache',
    'validate_url',
    'normalize_url',
    'extract_domain',
    'clean_text',
    'extract_email',
    'extract_phone',
    'parse_name',
    'save_dataframe',
    'get_timestamp',
]
