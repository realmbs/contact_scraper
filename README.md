# Legal Education Contact Scraper

An intelligent web scraper to discover contacts at Law Schools and Paralegal Programs with minimal manual review required.

**Current Status**: Phase 1 Complete (Target Discovery)

## Features

- **Target Discovery**: Automatically finds ABA-accredited law schools and paralegal programs
- **Intelligent Filtering**: Smart title matching and confidence scoring
- **Email Intelligence**: API integration for email finding and validation (optional)
- **Quality Controls**: Deduplication, validation, and confidence scoring
- **Excel Output**: Comprehensive multi-sheet reports with statistics
- **Graceful Degradation**: Works without API keys using sample data

## Project Status

### Phase 1: Foundation COMPLETE
Configuration system with graceful API handling
Core utilities (logging, caching, rate limiting)
Target discovery for law schools and paralegal programs
CLI interface for target discovery
All tests passing (22/22)

### Phase 2-5: Coming Soon
Contact Extraction Engine
Email Enrichment & Validation
Deduplication & Matching
Excel Output with Statistics

## Installation

### Requirements
- Python 3.10 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Step 1: Clone the Repository
```bash
git clone https://github.com/realmbs/contact_scraper.git
cd contact_scraper
```

### Step 2: Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
playwright install
```

This will install:
- **Scraping**: Scrapy, Playwright, BeautifulSoup, Selenium
- **Data Processing**: Pandas, openpyxl
- **Utilities**: loguru, tqdm, fuzzywuzzy, fake-useragent
- **Testing**: pytest

### Step 4: Configure Environment (Optional)
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env to add your API keys (all optional)
# nano .env  # or use your preferred editor
```

**API Keys (All Optional)**:
- `HUNTER_API_KEY`: Email finding (50 free searches/month)
- `ZEROBOUNCE_API_KEY`: Email validation (100 free validations)
- `NEVERBOUNCE_API_KEY`: Email validation (1,000 free validations)
- `PROXYCURL_API_KEY`: LinkedIn enrichment (~$0.08/profile)

**Note**: The system works perfectly fine without any API keys using sample data.

## Usage

### Quick Start

Run the scraper:
```bash
python main.py
```

Follow the prompts:
1. **Select States**: Enter state abbreviations (e.g., `CA, NY, TX`) or `ALL` for all states
2. **Select Program Type**: Choose law schools, paralegal programs, or both
3. **Confirm**: Review settings and confirm to start discovery

### Example Session
```
LEGAL EDUCATION CONTACT SCRAPER
Phase 1: Target Discovery

Which states would you like to target?
  - Enter state abbreviations separated by commas (e.g., CA, NY, TX)
  - Enter 'ALL' for all states
  - Press Enter for sample states (CA, NY, TX)

States: CA, NY

Which type of programs would you like to discover?
  1. Law Schools only
  2. Paralegal Programs only
  3. Both (default)

Choice [1-3]: 3

CONFIGURATION SUMMARY
States: CA, NY
Program Type: BOTH

Proceed with target discovery? [Y/n]: Y

... [Discovery process runs] ...

PHASE 1 COMPLETE
Results saved to: output/targets_discovered_20251223_130913.csv
```

### Output Files

The scraper creates several directories:
- **`output/`**: Main results (CSV files with discovered targets)
- **`output/cache/`**: Cached institution lists (speeds up re-runs)
- **`logs/`**: Detailed execution logs

### Advanced Usage

#### Using from Python

```python
from modules.target_discovery import get_all_targets

# Discover targets for specific states
targets = get_all_targets(
    states=['CA', 'NY', 'TX'],
    program_type='both'  # 'law', 'paralegal', or 'both'
)

print(f"Found {len(targets)} targets")
print(targets.head())
```

#### Configuration Options

Edit `.env` to customize behavior:

```bash
# Rate limiting (seconds between requests)
RATE_LIMIT_DELAY=5.0
MIN_DELAY=2.0
MAX_DELAY=10.0

# Logging level
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# Caching
ENABLE_CACHING=true
CACHE_EXPIRATION_HOURS=24

# Confidence scoring
MIN_CONFIDENCE_SCORE=50
MIN_EMAIL_SCORE=70
```

## Testing

Run the test suite:
```bash
# Run all tests
PYTHONPATH=. venv/bin/pytest

# Run specific test file
PYTHONPATH=. venv/bin/pytest tests/test_config.py -v

# Run with coverage
PYTHONPATH=. venv/bin/pytest --cov=modules --cov=config
```

Current test status: **22/22 passing** 

## Project Structure

```
contact_scraper/
main.py                 # CLI interface
config/                 # Configuration
settings.py         # Settings and environment variables
api_clients.py      # API client initialization
modules/                # Core modules
utils.py            # Utility functions
target_discovery.py # Target discovery engine
tests/                  # Test suite
test_config.py
test_utils.py
output/                 # Generated files
cache/              # Cached data
logs/                   # Log files
requirements.txt        # Python dependencies
.env.example            # Configuration template
CLAUDE.md              # Implementation plan
```

## Architecture

### Configuration System
- **Environment-based**: All settings configurable via `.env`
- **Graceful API degradation**: Works without any API keys
- **Validation**: Automatic configuration validation on startup

### Utilities
- **Logging**: Structured logging with file rotation (loguru)
- **Caching**: Smart caching with expiration
- **Rate Limiting**: Adaptive delays to respect website limits
- **Text Processing**: Email/phone extraction, name parsing

### Target Discovery
- **Multi-source**: ABA official list, AAfPE directory, state systems
- **Fallback Strategy**: Uses sample data when live scraping fails
- **Caching**: Results cached to avoid re-scraping
- **Filtering**: State-based filtering and deduplication

## Performance

### Expected Metrics (Full Implementation)
- **Email validity**: >90% valid or catch-all
- **Title relevance**: >85% match target roles
- **Manual review**: <10% of contacts
- **Coverage**: 80%+ institutions yield contacts

### Processing Speed (Estimated)
- **Target Discovery**: 5-10 minutes for 25 states
- **Contact Extraction**: 30-60 seconds per institution
- **Total Runtime**: 8-12 hours for full 25-state scrape (with optimizations: ~4-6 hours)

### Expected Yield (25 states)
- **Law Schools**: 150-350 contacts
- **Paralegal Programs**: 400-1200 contacts
- **Total**: 550-1550 high-quality contacts

### Performance Optimizations

**Browser Pooling** (Sprint 2.2 - Available)

Enable browser pooling for 20-30% faster scraping:

```bash
# Enable browser pooling in .env
USE_BROWSER_POOL=true

# Or set environment variable
export USE_BROWSER_POOL=true
python main.py
```

This uses a pool of 3 persistent browsers instead of launching fresh browsers for each page.

**Benefits**:
- 20-30% faster (5.8h → 4.1h for full dataset)
- Saves 10-15s per institution
- Memory efficient (<8GB peak RAM)
- Eliminates browser launch overhead

**Fallback**: Set `USE_BROWSER_POOL=false` to use legacy thread pool mode

**System Requirements for Browser Pooling**:
- 16GB RAM recommended (8GB minimum)
- Modern CPU (4+ cores recommended for 6x parallelization)

## Troubleshooting

### Common Issues

**Issue**: `ModuleNotFoundError: No module named 'config'`
```bash
# Solution: Set PYTHONPATH
PYTHONPATH=. python main.py
```

**Issue**: Playwright browsers not found
```bash
# Solution: Install Playwright browsers
venv/bin/playwright install
```

**Issue**: Permission denied on main.py
```bash
# Solution: Make it executable
chmod +x main.py
```

**Issue**: API showing as "Enabled" but using placeholder keys
- Edit `.env` and replace `your_*_api_key_here` with real API keys
- Or leave as-is to use sample data (no API calls made)

## Development

### Running Tests
```bash
PYTHONPATH=. venv/bin/pytest tests/ -v
```

### Code Style
- Follow PEP 8 guidelines
- Use type hints where appropriate
- Document all public functions

### Adding New Features
See `CLAUDE.md` for detailed implementation plan and roadmap.

## Documentation Guide

The project uses a three-tier documentation system:

### Quick Start
- **README.md** (this file) - Installation, usage, and overview

### Implementation Details
- **CLAUDE.md** - Master implementation plan (source of truth for development)
  - Phases 1-4 complete (foundation, scraping, email validation, quality control)
  - Phase 5 in progress (bulk data collection optimization)
  - Sprint details, benchmarks, and performance metrics
- **SCALING_GUIDE.md** - Performance optimization and scaling strategies

### Historical Reference
- **docs/archive/** - Outdated documentation from earlier phases (reference only)

### Contributing
For implementation details, always refer to CLAUDE.md as the single source of truth.

## Roadmap

See `CLAUDE.md` for the complete implementation roadmap.

**Next up: Phase 2 - Contact Extraction Engine**
- Scrape individual institution websites
- Extract contacts with target titles
- Intelligent title matching with fuzzy logic
- Build email addresses from patterns

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is for educational and research purposes.

## Support

For issues and questions:
- Check the troubleshooting section above
- Review `CLAUDE.md` for detailed documentation
- Open an issue on GitHub

---

**Status**: Phase 1 Complete | **Next**: Phase 2 - Contact Extraction
