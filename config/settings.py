"""
Configuration settings for Legal Education Contact Scraper.

Loads environment variables and provides configuration constants
with sensible defaults and validation.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / '.env'

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
    logger.info(f"Loaded configuration from {ENV_FILE}")
else:
    logger.warning(f".env file not found at {ENV_FILE}. Using defaults.")

# =============================================================================
# API Keys (Optional - None if not provided)
# =============================================================================

HUNTER_API_KEY = os.getenv('HUNTER_API_KEY', '').strip() or None
ZEROBOUNCE_API_KEY = os.getenv('ZEROBOUNCE_API_KEY', '').strip() or None
NEVERBOUNCE_API_KEY = os.getenv('NEVERBOUNCE_API_KEY', '').strip() or None
PROXYCURL_API_KEY = os.getenv('PROXYCURL_API_KEY', '').strip() or None

# Check which APIs are available
APIS_AVAILABLE = {
    'hunter': HUNTER_API_KEY is not None,
    'zerobounce': ZEROBOUNCE_API_KEY is not None,
    'neverbounce': NEVERBOUNCE_API_KEY is not None,
    'proxycurl': PROXYCURL_API_KEY is not None,
}

# =============================================================================
# Directory Paths
# =============================================================================

MODULES_DIR = BASE_DIR / 'modules'
CONFIG_DIR = BASE_DIR / 'config'
OUTPUT_DIR = BASE_DIR / 'output'
LOGS_DIR = BASE_DIR / 'logs'
TESTS_DIR = BASE_DIR / 'tests'
CACHE_DIR = OUTPUT_DIR / 'cache'

# Create directories if they don't exist
for directory in [OUTPUT_DIR, LOGS_DIR, CACHE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# =============================================================================
# Scraping Configuration
# =============================================================================

def _get_float(key: str, default: float) -> float:
    """Get float value from environment variable."""
    try:
        return float(os.getenv(key, default))
    except ValueError:
        logger.warning(f"Invalid value for {key}, using default: {default}")
        return default

def _get_int(key: str, default: int) -> int:
    """Get integer value from environment variable."""
    try:
        return int(os.getenv(key, default))
    except ValueError:
        logger.warning(f"Invalid value for {key}, using default: {default}")
        return default

def _get_bool(key: str, default: bool) -> bool:
    """Get boolean value from environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')

# Rate limiting
RATE_LIMIT_DELAY = _get_float('RATE_LIMIT_DELAY', 5.0)
MIN_DELAY = _get_float('MIN_DELAY', 2.0)
MAX_DELAY = _get_float('MAX_DELAY', 10.0)

# User agent rotation
USE_RANDOM_USER_AGENT = _get_bool('USE_RANDOM_USER_AGENT', True)

# Browser settings
HEADLESS_BROWSER = _get_bool('HEADLESS_BROWSER', True)

# Playwright settings
ENABLE_PLAYWRIGHT = _get_bool('ENABLE_PLAYWRIGHT', True)
PLAYWRIGHT_TIMEOUT = _get_int('PLAYWRIGHT_TIMEOUT', 30000)  # milliseconds
SAVE_SCREENSHOTS = _get_bool('SAVE_SCREENSHOTS', False)
SCREENSHOTS_DIR = OUTPUT_DIR / 'screenshots'

# Create screenshots directory if enabled
if SAVE_SCREENSHOTS:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Concurrent requests
MAX_CONCURRENT_REQUESTS = _get_int('MAX_CONCURRENT_REQUESTS', 5)

# Timeouts
REQUEST_TIMEOUT = _get_int('REQUEST_TIMEOUT', 30)

# =============================================================================
# Logging Configuration
# =============================================================================

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_MAX_SIZE = _get_int('LOG_MAX_SIZE', 10) * 1024 * 1024  # Convert MB to bytes
LOG_BACKUP_COUNT = _get_int('LOG_BACKUP_COUNT', 5)

# =============================================================================
# Data Processing Configuration
# =============================================================================

MIN_CONFIDENCE_SCORE = _get_int('MIN_CONFIDENCE_SCORE', 50)
MIN_EMAIL_SCORE = _get_int('MIN_EMAIL_SCORE', 70)
ENABLE_CACHING = _get_bool('ENABLE_CACHING', True)
CACHE_EXPIRATION_HOURS = _get_int('CACHE_EXPIRATION_HOURS', 24)

# =============================================================================
# Target Roles (for title matching)
# =============================================================================

LAW_SCHOOL_ROLES = [
    'Library Director',
    'Law Library Director',
    'Director of the Law Library',
    'Associate Dean for Academic Affairs',
    'Associate Dean for Information Services',
    'Legal Writing Director',
    'Director of Legal Writing',
    'Experiential Learning Director',
    'Director of Experiential Learning',
    'Clinical Programs Director',
    'Instructional Technology Librarian',
    'Head of Reference',
    'Assistant Dean for Information Services',
]

PARALEGAL_PROGRAM_ROLES = [
    'Paralegal Program Director',
    'Director of Paralegal Studies',
    'Paralegal Studies Coordinator',
    'Dean of Workforce Programs',
    'Dean of Career and Technical Education',
    'Legal Studies Faculty',
    'Legal Studies Instructor',
    'Program Chair',
    'Department Chair',
]

# Combined list for "both" option
ALL_TARGET_ROLES = LAW_SCHOOL_ROLES + PARALEGAL_PROGRAM_ROLES

# =============================================================================
# Validation & Reporting
# =============================================================================

def validate_config():
    """Validate configuration and log status."""
    logger.info("=" * 70)
    logger.info("Legal Education Contact Scraper - Configuration Status")
    logger.info("=" * 70)

    # API status
    logger.info("API Integrations:")
    for api_name, available in APIS_AVAILABLE.items():
        status = "✓ Enabled" if available else "✗ Disabled (optional)"
        logger.info(f"  {api_name.capitalize():15} {status}")

    # Scraping settings
    logger.info(f"\nScraping Settings:")
    logger.info(f"  Rate Limit Delay:  {RATE_LIMIT_DELAY}s")
    logger.info(f"  Headless Browser:  {HEADLESS_BROWSER}")
    logger.info(f"  Max Concurrent:    {MAX_CONCURRENT_REQUESTS}")
    logger.info(f"  Request Timeout:   {REQUEST_TIMEOUT}s")

    # Data settings
    logger.info(f"\nData Processing:")
    logger.info(f"  Min Confidence:    {MIN_CONFIDENCE_SCORE}")
    logger.info(f"  Caching Enabled:   {ENABLE_CACHING}")
    logger.info(f"  Cache Expiration:  {CACHE_EXPIRATION_HOURS}h")

    # Directories
    logger.info(f"\nDirectories:")
    logger.info(f"  Output: {OUTPUT_DIR}")
    logger.info(f"  Logs:   {LOGS_DIR}")
    logger.info(f"  Cache:  {CACHE_DIR}")

    logger.info("=" * 70)

    # Warnings
    if not any(APIS_AVAILABLE.values()):
        logger.warning("No API keys configured. Email finding and validation will be limited.")

    return True

# =============================================================================
# Export configuration
# =============================================================================

__all__ = [
    'HUNTER_API_KEY',
    'ZEROBOUNCE_API_KEY',
    'NEVERBOUNCE_API_KEY',
    'PROXYCURL_API_KEY',
    'APIS_AVAILABLE',
    'BASE_DIR',
    'OUTPUT_DIR',
    'LOGS_DIR',
    'CACHE_DIR',
    'RATE_LIMIT_DELAY',
    'MIN_DELAY',
    'MAX_DELAY',
    'USE_RANDOM_USER_AGENT',
    'HEADLESS_BROWSER',
    'ENABLE_PLAYWRIGHT',
    'PLAYWRIGHT_TIMEOUT',
    'SAVE_SCREENSHOTS',
    'SCREENSHOTS_DIR',
    'MAX_CONCURRENT_REQUESTS',
    'REQUEST_TIMEOUT',
    'LOG_LEVEL',
    'LOG_MAX_SIZE',
    'LOG_BACKUP_COUNT',
    'MIN_CONFIDENCE_SCORE',
    'MIN_EMAIL_SCORE',
    'ENABLE_CACHING',
    'CACHE_EXPIRATION_HOURS',
    'LAW_SCHOOL_ROLES',
    'PARALEGAL_PROGRAM_ROLES',
    'ALL_TARGET_ROLES',
    'validate_config',
]
