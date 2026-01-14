# main.py CLI Interface - Updated for Phase 2

**Date**: 2025-12-23
**Status**: ✅ Complete

---

## Overview

The main.py entry point has been updated to integrate Phase 2 contact extraction functionality. Users can now run either discovery-only mode or full extraction (discovery + contact scraping) through an interactive CLI.

---

## New Features

### 1. **Dual Mode Operation**
```
What would you like to do?
  1. Discovery only (find institutions)
  2. Full extraction (discovery + contact scraping) (default)
```

**Discovery Mode**:
- Finds law schools and paralegal programs
- Saves target list to CSV
- Quick operation (< 1 minute)
- Good for validating target lists

**Full Extraction Mode**:
- Discovers targets
- Scrapes contact information from each institution
- Provides comprehensive statistics
- Saves both targets and contacts

### 2. **Institution Limit**
```
How many institutions would you like to scrape?
  - Enter a number (e.g., 5)
  - Press Enter for all discovered institutions
```

Allows users to:
- Test on small batches first (e.g., 3-5 institutions)
- Run full extraction on all discovered targets
- Control execution time and resource usage

### 3. **Enhanced Results Display**

**Discovery Results**:
- Total targets found
- Breakdown by type (law schools vs paralegal programs)
- Breakdown by state
- File saved location

**Extraction Results** (Full Mode):
- Total contacts extracted
- Breakdown by program type
- Email/phone found percentages
- Confidence score distribution (High/Medium/Low)
- Top matched roles
- Common failure reasons and recommendations

### 4. **Better Error Handling**

When no contacts are extracted:
```
Common reasons:
  - Anti-scraping measures (403 Forbidden)
  - JavaScript-heavy sites (need Playwright)
  - Outdated URLs or changed website structures

Recommendations:
  - Try fewer institutions for testing
  - Check logs for specific errors
  - Consider enabling Playwright for JavaScript sites
```

---

## Usage Examples

### Example 1: Discovery Only
```bash
$ python main.py

# Input:
States: CA, NY
Program Type: 3 (Both)
Mode: 1 (Discovery only)

# Output:
DISCOVERY RESULTS
- Total Targets: 13
- Law Schools: 6
- Paralegal Programs: 7
- Saved to: output/targets_discovered_YYYYMMDD_HHMMSS.csv
```

### Example 2: Full Extraction (Limited)
```bash
$ python main.py

# Input:
States: CA
Program Type: 1 (Law Schools only)
Mode: 2 (Full extraction)
Limit: 3

# Output:
PHASE 1: DISCOVERING TARGETS
- Found 4 law schools in CA

PHASE 2: EXTRACTING CONTACTS
- Scraping 3 institutions...
- Extracted 5 contacts
- Email found: 80%
- High confidence: 2 (40%)
- Saved to: output/contacts_raw_YYYYMMDD_HHMMSS.csv
```

### Example 3: Full Extraction (All)
```bash
$ python main.py

# Input:
States: ALL
Program Type: 3 (Both)
Mode: 2 (Full extraction)
Limit: [blank - all]

# Output:
PHASE 1: DISCOVERING TARGETS
- Found 200+ institutions across all states

PHASE 2: EXTRACTING CONTACTS
- Scraping 200+ institutions...
- This will take ~2-4 hours...
```

---

## User Flow

```
┌─────────────────────────────────────┐
│  Start main.py                      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Show Banner + Validate Config      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Get User Input:                    │
│  - States (CA, NY, TX, etc.)        │
│  - Program Type (Law/Para/Both)     │
│  - Mode (Discovery/Full)            │
│  - Limit (if Full mode)             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Confirm Configuration              │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  PHASE 1: Target Discovery          │
│  - Get law schools (if selected)    │
│  - Get paralegal programs           │
│  - Display results                  │
│  - Save targets to CSV              │
└──────────────┬──────────────────────┘
               │
               ├─── Discovery Mode ───> [END]
               │
               └─── Full Mode ─────────┐
                                       │
                                       ▼
               ┌─────────────────────────────────────┐
               │  PHASE 2: Contact Extraction        │
               │  - Scrape each institution          │
               │  - Extract contacts                 │
               │  - Calculate confidence scores      │
               │  - Display statistics               │
               │  - Save contacts to CSV             │
               └──────────────┬──────────────────────┘
                              │
                              ▼
               ┌─────────────────────────────────────┐
               │  Show Final Summary                 │
               │  - Files saved                      │
               │  - Next steps                       │
               └─────────────────────────────────────┘
```

---

## Output Files

### Discovery Mode
```
output/
└── targets_discovered_20251223_133819.csv
```

**Columns**:
- name, state, city, url
- type (Law School / Paralegal Program)
- accreditation_status

### Full Extraction Mode
```
output/
├── targets_discovered_20251223_134500.csv
└── contacts_raw_20251223_134502.csv
```

**Contacts CSV Columns**:
- institution_name, institution_url, state, program_type
- first_name, last_name, full_name
- title, matched_role
- email, phone
- confidence_score, title_match_score
- extraction_method, source_url, extracted_at

---

## Statistics Shown

### Discovery Results
- Total targets found
- Law schools count
- Paralegal programs count
- Breakdown by state

### Extraction Results
- Total contacts extracted
- Breakdown by program type
- Email found percentage
- Phone found percentage
- Confidence distribution (High/Medium/Low)
- Top 5 matched roles
- Success/failure reasons

---

## Next Steps Guidance

### After Discovery Mode
```
Next Steps:
  - Review the discovered targets
  - Run in 'Full extraction' mode to scrape contacts
```

### After Full Extraction
```
Next Steps:
  - Review extracted contacts
  - Proceed to Phase 3: Email Validation & Enrichment
```

---

## Technical Implementation

### Functions Added
```python
get_user_input_mode() -> str
    # Returns 'discovery' or 'full'

get_max_institutions() -> Optional[int]
    # Returns integer limit or None for all
```

### Main Function Updated
- Integrated contact_extractor module
- Added conditional flow (discovery vs full)
- Enhanced statistics display
- Better error messages
- Progress tracking

### Dependencies
- modules.target_discovery.get_all_targets
- modules.contact_extractor.scrape_multiple_institutions
- modules.utils.save_dataframe
- config.settings.validate_config

---

## Testing

**Tested Scenarios**:
1. ✅ Discovery only mode (CA, NY, TX)
2. ✅ Full extraction with limit (CA, 3 institutions)
3. ✅ Empty results handling
4. ✅ User cancellation (Ctrl+C)
5. ✅ Invalid input handling

**Results**: All scenarios working correctly

---

## Code Quality

- **Lines of Code**: 334 lines
- **Error Handling**: Comprehensive try/except blocks
- **User Experience**: Clear prompts, helpful error messages
- **Statistics**: Rich output with percentages and breakdowns
- **Logging**: All operations logged to file

---

## Improvements Over Phase 1

### Before (Phase 1)
- Discovery only
- Basic output
- No statistics
- Fixed workflow

### After (Phase 2)
- Discovery + Extraction modes
- Rich statistics
- Confidence distributions
- Flexible workflow
- Helpful error messages
- Institution limit control

---

## Status

✅ **Complete and Production-Ready**

The main.py entry point now provides a complete, user-friendly interface for both target discovery and contact extraction workflows.
