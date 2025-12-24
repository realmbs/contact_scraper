# Legal Education Contact Scraper - Implementation Plan

**Created**: 2025-12-23
**Last Updated**: 2025-12-23
**Status**: Phases 1-4 Complete ✅ | Phase 5 In Progress ⚠️
**Priority**: Quality data over speed

---

## Project Overview

An intelligent web scraper to discover contacts at Law Schools and Paralegal Programs with minimal manual review required. The system uses modular architecture with intelligent filtering, validation, and confidence scoring throughout the pipeline.

**Key Features**:
- Scrapes ABA-accredited law schools and paralegal programs
- Intelligent title matching with fuzzy logic
- Email validation and enrichment via APIs
- Deduplication and comparison with existing databases
- Confidence scoring system (0-100) for quality assurance
- Excel output with comprehensive statistics

---

## System Architecture

```
[User Input] → [Target Discovery] → [Contact Extraction] → [Enrichment/Validation] → [Deduplication] → [Output]
     ↓              ↓                      ↓                        ↓                      ↓            ↓
  State(s)     Find Programs         Scrape Contacts         Verify Emails          Clean Data     Excel File
  Program Type  Verify Status        Extract Names/Titles    Enrich Data           Match Existing  +Stats
```

---

## Implementation Roadmap

### Phase 1: Foundation (Sprint 1) - Days 1-2
**Status**: ✅ **COMPLETE** (Completed: 2025-12-23)

Tasks:
- [x] Create CLAUDE.md with implementation plan
- [x] Set up project directory structure
  - `/modules/` - Main modules
  - `/config/` - API keys and settings
  - `/output/` - Generated files
  - `/logs/` - Execution logs
  - `/tests/` - Test cases
- [x] Create requirements.txt with all dependencies
- [x] Create config management system (.env, API key handling)
- [x] Build Target Discovery module for ABA law schools
- [x] Build Target Discovery module for paralegal programs
- [x] Create utility functions (logging, caching, rate limiting)
- [x] Test on 2-3 states, verify institution lists

**Deliverable**: ✅ Working target discovery producing accurate institution lists
- 16 targets discovered for CA, NY, TX (6 law schools, 10 paralegal programs)
- All 22 tests passing
- CLI interface complete
- Comprehensive documentation

---

### Phase 2: Core Scraping (Sprint 2) - Days 3-4
**Status**: ✅ **COMPLETE** (Completed: 2025-12-23)

Tasks:
- [x] Build Contact Extraction module
- [x] Implement adaptive scraping strategies (Playwright + static fallback)
- [x] Build title matching logic with test cases
- [x] Test on 5-10 institutions per program type
- [x] Refine HTML parsing for common website structures
- [x] **CRITICAL FIX**: Integrate Playwright to solve JavaScript rendering issues

**Deliverable**: ✅ Extract contacts with titles and emails from test institutions
- 10 contacts successfully extracted from Stanford Law School
- Playwright integration solves "0 contacts extracted" problem
- 29 unit tests passing (100% success rate)
- Full extraction pipeline working end-to-end

---

### Phase 3: Email Intelligence (Sprint 3) - Days 5-6
**Status**: ✅ **COMPLETE** (Completed: 2025-12-23)

Tasks:
- [x] Build Email Validation module (modules/email_validator.py)
- [x] Integrate Hunter.io API for email finding
- [x] Integrate ZeroBounce API (direct API calls, no SDK)
- [x] Integrate NeverBounce API (direct API calls, no SDK)
- [x] Implement batch email validation with smart service selection
- [x] Implement catch-all domain detection
- [x] Implement confidence score updates based on email quality
- [x] Create comprehensive test suite (34 tests, 100% passing)
- [x] Integrate into main.py pipeline as Phase 3 step
- [x] Add email quality statistics to CLI output

**Deliverable**: ✅ 100% email coverage achieved (exceeds 80% target!)
- 708 lines: modules/email_validator.py
- 617 lines: tests/test_email_validator.py
- All 85 tests passing (22 foundation + 29 extraction + 34 validation)
- Direct API integration (avoiding SDK dependency issues)
- Graceful degradation when API keys unavailable
- Smart service selection (NeverBounce → ZeroBounce → Hunter.io)

---

### Phase 4: Quality & Integration (Sprint 4) - Days 7-8

**Status**: ✅ **COMPLETE** (Completed: 2025-12-23)

Tasks:
- [x] Build Deduplication module
- [x] Implement confidence scoring system
- [x] Build comparison with existing database
- [x] Create main orchestrator with user input
- [x] Build output formatting (match existing Excel structure)
- [x] Create comprehensive test suite (59 tests, 100% passing)
- [x] Integrate all Phase 4 modules into main.py pipeline
- [x] Generate 8-sheet Excel workbook with formatting

**Deliverable**: ✅ End-to-end working system with quality controls
- 3 new modules created: statistics.py, deduplication.py, excel_output.py (~1,380 lines)
- 3 comprehensive test files (~740 lines, 59 tests passing)
- Full pipeline integration (discovery → extraction → validation → deduplication → Excel output)
- 144 total tests passing across all 4 phases (100% success rate)

**See detailed Phase 4 documentation below for complete implementation details**

---

### Phase 5: Target Discovery Expansion & Production Testing (Sprint 5) - Days 9-12

**Status**: ⚠️ IN PROGRESS - Core pipeline complete, target discovery needs expansion

**Current Limitation**: Target discovery uses **sample data only** (CA, NY, TX states)
- Law school discovery: Falls back to 6 sample schools (ABA returns 403 Forbidden)
- Paralegal program discovery: Uses 10 hardcoded sample programs
- **All other states return 0 results**

Tasks:
- [ ] **Expand Target Discovery to All 50 States**
  - Implement workaround for ABA 403 error (API endpoint, alternative source, cached list)
  - Build AAfPE paralegal program directory scraper
  - Add state-specific community college system scrapers
  - Create comprehensive institution database covering all states

- [ ] **Full System Testing with Real Data**
  - Test complete pipeline on 5-10 states (once discovery expanded)
  - Run with 20-50 institutions per state
  - Verify Excel output quality across different institution types
  - Test existing database comparison feature with real datasets
  - Validate all 8 Excel sheets populate correctly with production data

- [ ] **Performance Optimization**
  - Add parallel processing for contact extraction (asyncio or multiprocessing)
  - Optimize Playwright usage (browser pooling, reuse connections)
  - Tune rate limiting based on actual site responsiveness
  - Consider batch processing for large state selections (10+ states)

- [ ] **Manual Quality Validation**
  - Review 20% of extracted contacts for accuracy
  - Verify title matching quality across different institution types
  - Check email validation accuracy (compare with manual verification)
  - Validate confidence scores align with actual contact quality
  - Document common failure patterns and edge cases

- [ ] **Documentation & Deployment**
  - Write production user guide with screenshots
  - Create detailed API setup guide (Hunter.io, ZeroBounce, NeverBounce registration)
  - Add troubleshooting guide for common issues (403 errors, timeouts, etc.)
  - Document data quality expectations and limitations
  - Create production deployment checklist

- [ ] **Code Quality & Maintenance**
  - Add type hints to all function signatures
  - Improve error messages for better user experience
  - Add progress bars for long-running operations
  - Create backup/resume functionality for interrupted scrapes

**Deliverable**: Production-ready scraper with nationwide coverage

**Priority 1 (Blocking)**: Expand target discovery beyond CA, NY, TX sample data
**Priority 2**: Performance optimization for large-scale scraping
**Priority 3**: Documentation and production deployment guide

---

## Testing Guide

**⚠️ IMPORTANT**: Target discovery currently uses sample data for **CA, NY, TX only**. Other states will return 0 results until Phase 5 target discovery expansion is complete.

### Testing the Complete Pipeline (Phases 1-4)

```bash
source venv/bin/activate && python main.py

# Recommended Test Configuration:
States: CA, NY        # ⚠️ MUST use CA, NY, or TX (sample data only)
Program Type: 3 (Both)
Mode: 2 (Full extraction)
Limit: 5 institutions
Existing Database: [Press Enter to skip]

# Expected Results:
- 5 institutions discovered from CA/NY sample data
- 3-4 of 5 institutions successful (60-80% success rate)
- 10-20 total contacts extracted
- 80%+ with validated emails (Phase 3)
- Average confidence: 60-80
- Excel workbook with 8 sheets generated
- Runtime: ~10-15 minutes
```

### Sample Institutions Available (for testing):
- **CA Law Schools**: Stanford, UCLA, UC Berkeley
- **NY Law Schools**: Columbia, NYU, Fordham
- **TX Law Schools**: UT Austin, SMU, University of Houston
- **CA Paralegal Programs**: UCLA Extension, Berkeley Extension, San Diego Miramar
- **NY Paralegal Programs**: NYU SPS, CUNY Paralegal Studies, Hunter College
- **TX Paralegal Programs**: Houston Community College, El Paso Community College, South Texas College

---

## Overall System Status

**Test Results Summary**:
```
144 tests passed in 16.39s (100% success rate)
├── 22 foundation tests (Phase 1: config, utilities)
├── 29 contact extraction tests (Phase 2: scraping, matching, patterns)
├── 34 email validation tests (Phase 3: APIs, batching, enrichment)
└── 59 quality control tests (Phase 4: statistics, deduplication, Excel)
```

**Phase 1 (Foundation)**: ✅ COMPLETE
- Target discovery module with sample data (CA, NY, TX)
- Configuration system with optional API support
- CLI interface with interactive prompts
- Comprehensive utilities and logging

**Phase 2 (Core Scraping)**: ✅ COMPLETE
- Contact extraction with fuzzy title matching
- Playwright integration for JavaScript-heavy sites
- Confidence scoring system (0-100 scale)
- Smart HTML parsing with multiple strategies

**Phase 3 (Email Intelligence)**: ✅ COMPLETE
- Email validation (ZeroBounce, NeverBounce direct API)
- Email finding (Hunter.io integration)
- Batch processing with smart service selection
- Confidence score adjustments based on email quality

**Phase 4 (Quality & Integration)**: ✅ COMPLETE
- Statistics calculation (state breakdown, email quality, confidence distribution)
- Hierarchical deduplication (email → name+institution)
- 8-sheet Excel workbook with color coding
- Optional existing database comparison

**Overall Progress**: ✅ ✅ ✅ ✅ | ⚠️ Phase 5 (Target Expansion & Testing) IN PROGRESS
