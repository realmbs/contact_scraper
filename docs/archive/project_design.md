# Legal Education Contact Scraper - Technical Design Document

## Project Overview
**Objective**: Build an intelligent web scraper to discover contacts at Law Schools and Paralegal Programs with minimal manual review required.

**Priority**: Quality data over speed - intelligent filtering and validation throughout pipeline.

---

## System Architecture

```
[User Input] → [Target Discovery] → [Contact Extraction] → [Enrichment/Validation] → [Deduplication] → [Output]
     ↓              ↓                      ↓                        ↓                      ↓            ↓
  State(s)     Find Programs         Scrape Contacts         Verify Emails          Clean Data     Excel File
  Program Type  Verify Status        Extract Names/Titles    Enrich Data           Match Existing  +Stats
```

---

## Phase 1: Data Source Strategy

### Law Schools (ABA-Accredited JD Programs)

**Primary Sources:**
1. **ABA Official List** (Gold Standard)
   - URL: `https://www.americanbar.org/groups/legal_education/resources/aba_approved_law_schools/`
   - Data: Complete list of ~200 ABA-accredited programs with locations
   - Reliability: 100% - official authoritative source
   - Update frequency: Quarterly

2. **Individual Law School Websites** (Direct Scraping)
   - Faculty/Staff directories
   - Library staff pages
   - Academic affairs pages
   - Legal writing program pages
   - Typical patterns:
     - `/faculty` or `/faculty-staff`
     - `/library/staff` or `/law-library/people`
     - `/academics/legal-writing`

3. **LinkedIn School Pages** (Enrichment)
   - Current employees by title search
   - Verification of employment status
   - Requires: Trial of LinkedIn Sales Navigator API or Proxycurl API

**Target Roles:**
- Law Library Director
- Associate Dean for Academic Affairs
- Legal Writing Director
- Experiential Learning Director
- Instructional Technology Librarian

### Paralegal Programs (Community/Technical Colleges)

**Primary Sources:**
1. **American Association for Paralegal Education (AAfPE)**
   - URL: `https://www.aafpe.org/`
   - Member directory with program listings
   - ~400 institutional members

2. **National Federation of Paralegal Associations**
   - URL: `https://www.paralegals.org/`
   - School directory by state

3. **State Community College Systems**
   - Each state has a centralized system website
   - Example: Florida College System (`www.fldoe.org/schools/higher-ed/fl-college-system/`)
   - Then scrape individual college websites

4. **Department of Education IPEDS Database**
   - All accredited institutions
   - Filter by: Associate's degree programs, Legal Studies CIP codes
   - Provides institutional URLs for scraping

**Target Roles:**
- Paralegal Program Director
- Dean of Workforce Programs
- Legal Studies Faculty
- Program Chair
- Academic Affairs leadership

---

## Phase 2: Technical Stack

### Core Scraping Framework
```python
# Required libraries
scrapy              # Professional-grade scraping framework
selenium            # JavaScript-heavy sites
playwright          # Modern alternative to Selenium
beautifulsoup4      # HTML parsing
requests            # HTTP requests
pandas              # Data manipulation
openpyxl            # Excel output
```

### Email Finding & Validation
```python
# Email discovery
hunter.io API       # Find email patterns, 50 free searches/month trial
clearbit API        # Email enrichment, limited free tier
emailhunter         # Python wrapper

# Email verification
zerobounce API      # 100 free validations trial
neverbounce API     # 1,000 free validations trial
kickbox API         # 100 free validations trial

# Pattern-based email construction
# If we find pattern: firstname.lastname@university.edu
# Can construct emails for other contacts at same institution
```

### Data Enrichment
```python
# LinkedIn data
proxycurl API       # LinkedIn scraping, $0.08/profile, trial available
phantombuster       # Alternative LinkedIn tool

# Contact verification
clearbit enrichment # Verify current employment
full-contact API    # Social profile aggregation
```

### Rate Limiting & Politeness
```python
ratelimit           # Python rate limiting
requests_cache      # Avoid duplicate requests
fake_useragent      # Rotate user agents
scrapy-rotating-proxies  # Optional: if needed for scale
```

---

## Phase 3: Scraper Design - Modular Architecture

### Module 1: Target Discovery Engine
**File**: `target_discovery.py`

**Purpose**: Build comprehensive list of institutions to scrape

**Functions**:
- `get_aba_law_schools(states: list) -> DataFrame`
  - Scrape ABA official list
  - Filter by state codes
  - Extract: school name, city, state, URL
  - Verify ABA accreditation status
  
- `get_paralegal_programs(states: list) -> DataFrame`
  - Query AAfPE directory
  - Scrape state community college systems
  - Cross-reference with IPEDS data
  - Verify program active status
  - Extract: institution name, city, state, URL, program URL

**Output**: `targets_[timestamp].csv`
- Columns: institution_name, type, city, state, primary_url, program_url, accreditation_status

**Quality Controls**:
- Deduplication by name + state
- URL validation (200 status check)
- Flag institutions with missing URLs for manual review

---

### Module 2: Contact Extraction Engine
**File**: `contact_extractor.py`

**Purpose**: Scrape individual institution websites for target contacts

**Class**: `InstitutionScraper`
- Adaptive scraping strategies per institution
- Maintains scraping history to avoid redundant requests

**Functions**:
- `find_directory_pages(base_url: str) -> list`
  - Search for common directory patterns
  - Find: /faculty, /staff, /library, /administration
  - Use sitemap.xml if available
  - Breadth-first search through site structure (max 3 levels deep)

- `extract_contacts(page_url: str, target_roles: list) -> list`
  - Parse directory pages
  - Extract: name, title, email, phone, department
  - Title matching with fuzzy logic (not exact string match)
  - Handle various HTML structures (tables, divs, lists)

- `build_email_from_pattern(name: str, domain: str, pattern: str) -> str`
  - If we find 3+ emails at institution, detect pattern
  - Construct emails for contacts missing email addresses
  - Common patterns: firstname.lastname, flastname, firstnamelastname

**Title Matching Intelligence**:
```python
# Use fuzzy matching + keyword detection
target_keywords = {
    'law_library_director': ['library director', 'head librarian', 'law library', 'director of library'],
    'dean_academic_affairs': ['dean', 'academic affairs', 'associate dean for academic'],
    'legal_writing_director': ['legal writing', 'legal research', 'director of writing', 'lawr director'],
    'experiential_learning': ['experiential learning', 'clinical programs', 'externships director'],
    'instructional_tech': ['instructional technology', 'educational technology', 'tech librarian'],
    'paralegal_director': ['paralegal director', 'paralegal program', 'program director', 'legal studies chair'],
    'workforce_dean': ['dean of workforce', 'continuing education', 'career programs dean'],
}
```

**Output**: `contacts_raw_[timestamp].csv`
- Columns: institution, type, state, first_name, last_name, title, email, phone, source_url, confidence_score

---

### Module 3: Email Enrichment & Validation Engine
**File**: `email_validator.py`

**Purpose**: Find missing emails and validate all email addresses

**Functions**:
- `find_missing_emails(contact_df: DataFrame) -> DataFrame`
  - For contacts without emails:
    1. Try Hunter.io search (name + domain)
    2. Try Clearbit enrichment (name + institution)
    3. If email pattern detected, construct and validate
    4. LinkedIn search via Proxycurl (name + institution + title)
  - Add confidence score (0-100)

- `validate_emails(email_list: list) -> DataFrame`
  - Batch validation through ZeroBounce or NeverBounce
  - Results: valid, invalid, catch-all, unknown, disposable
  - Only keep valid + catch-all (with flag)
  - Add validation_status and validation_score columns

- `enrich_contact_data(contact_df: DataFrame) -> DataFrame`
  - Optional: Add LinkedIn profile URLs
  - Optional: Add additional phone numbers
  - Verify employment status (still at institution?)

**Quality Thresholds**:
- Only include contacts with:
  - Email present AND (valid OR catch-all with score >70)
  - OR confidence_score >= 80 for pattern-constructed emails

**Output**: `contacts_validated_[timestamp].csv`

---

### Module 4: Deduplication & Matching Engine
**File**: `deduplication.py`

**Purpose**: Remove duplicates and compare against existing database

**Functions**:
- `deduplicate_contacts(new_contacts: DataFrame) -> DataFrame`
  - Fuzzy name matching (account for typos, middle initials)
  - Email exact match
  - Institution + title similarity
  - Keep highest quality record (prioritize validated emails)

- `compare_with_existing(new_contacts: DataFrame, existing_file: str) -> tuple`
  - Load existing contacts (your uploaded file)
  - Find: truly_new, duplicates, potential_updates
  - Potential updates: same person, different title/email
  - Return all three DataFrames

- `merge_strategy(existing_record, new_record) -> dict`
  - If conflict, keep most recently validated data
  - Flag records needing manual review
  - Preserve all historical data in separate columns

**Output**: 
- `contacts_new_[timestamp].csv` - brand new contacts
- `contacts_duplicates_[timestamp].csv` - already in database
- `contacts_updates_[timestamp].csv` - existing contacts with new info

---

### Module 5: Main Orchestrator
**File**: `main.py`

**Purpose**: User interface and workflow orchestration

**User Input Flow**:
```
Welcome to Legal Education Contact Scraper
==========================================

Enter state codes (comma-separated, e.g., FL,GA,AL): 
> TX,CA,NY

Select program type:
1. Law Schools (ABA-accredited)
2. Paralegal Programs
3. Both
> 3

Use existing database for comparison? (Y/N): 
> Y

Enter path to existing contacts file: 
> /path/to/batch1_followup1.xlsx

Configuration Summary:
- States: TX, CA, NY
- Program Types: Law Schools + Paralegal Programs  
- Existing Database: batch1_followup1.xlsx (125 contacts)

Proceed? (Y/N): Y

[Progress output with detailed logging]
```

**Workflow Execution**:
1. Load configuration
2. Run target discovery (with progress bar)
3. For each institution:
   - Attempt contact extraction
   - Log success/failure
   - Cache results
4. Email finding for missing emails
5. Batch email validation
6. Deduplication
7. Comparison with existing DB
8. Generate outputs + statistics report

**Output**: 
- Excel file matching your existing format
- Statistics dashboard
- Log file with all decisions made

---

## Phase 4: Quality Assurance Features

### 1. Confidence Scoring System
Each contact gets a confidence score (0-100):
```
+40 points: Email found on official institution website
+30 points: Email validated as deliverable
+20 points: Title exactly matches target role
+10 points: LinkedIn profile confirms current employment
+10 points: Phone number found
-20 points: Email is catch-all domain
-30 points: Email constructed from pattern (not verified)
```

Contacts with score < 50 flagged for manual review.

### 2. Data Quality Checks
- **URL validation**: All source URLs return 200 status
- **Email format**: Regex validation before external validation
- **Name validation**: No numbers, no excessive punctuation
- **Title relevance**: Fuzzy match score >= 60 to target roles
- **Duplicate detection**: Multiple algorithms (email, name+institution, phone)

### 3. Logging & Transparency
- All decisions logged with reasoning
- Flagged records explained in separate sheet
- Source URLs preserved for manual verification
- Confidence scores broken down by component

### 4. Error Handling
- Retry logic with exponential backoff
- Graceful degradation (continue if one institution fails)
- Cache successful requests (avoid re-scraping on failure)
- API quota tracking and warnings

---

## Phase 5: Implementation Roadmap

### Sprint 1 (Days 1-2): Foundation
- [ ] Set up project structure
- [ ] Install and test all required libraries
- [ ] Register for trial API keys:
  - Hunter.io (50 searches/month)
  - ZeroBounce or NeverBounce (100-1000 validations)
  - Proxycurl (trial with credit card)
- [ ] Build Target Discovery module
- [ ] Test on 2-3 states, verify institution lists

**Deliverable**: Working target discovery producing accurate institution lists

### Sprint 2 (Days 3-4): Core Scraping
- [ ] Build Contact Extraction module
- [ ] Implement adaptive scraping strategies
- [ ] Build title matching logic with test cases
- [ ] Test on 5-10 institutions per program type
- [ ] Refine HTML parsing for common website structures

**Deliverable**: Extract 20+ contacts with titles and emails from test institutions

### Sprint 3 (Days 5-6): Email Intelligence
- [ ] Build Email Validation module
- [ ] Integrate Hunter.io API
- [ ] Integrate email validation API
- [ ] Implement email pattern detection
- [ ] Test email construction accuracy (validate constructed emails)

**Deliverable**: 80%+ of contacts have validated email addresses

### Sprint 4 (Days 7-8): Quality & Integration
- [ ] Build Deduplication module
- [ ] Implement confidence scoring
- [ ] Build comparison with existing database
- [ ] Create main orchestrator with user input
- [ ] Build output formatting (match existing Excel structure)

**Deliverable**: End-to-end working system with quality controls

### Sprint 5 (Days 9-10): Testing & Refinement
- [ ] Full test run on 3-5 states
- [ ] Manual validation of 20% of results
- [ ] Tune confidence score thresholds
- [ ] Optimize performance (parallel processing)
- [ ] Add statistics dashboard
- [ ] Documentation and usage guide

**Deliverable**: Production-ready scraper with documentation

---

## Phase 6: Expected Performance Metrics

### Output Quality Targets
- **Email validity rate**: >90% valid or catch-all
- **Title relevance**: >85% match target roles
- **Manual review required**: <10% of total contacts
- **Duplicate rate**: <5% internal duplicates
- **Coverage**: 80%+ of institutions yield at least 1 contact

### Processing Speed (estimated)
- **Target Discovery**: 5-10 minutes for 25 states
- **Contact Extraction**: 30-60 seconds per institution
  - Law Schools: ~2-3 hours for 50 schools
  - Paralegal Programs: ~5-8 hours for 200 programs
- **Email Validation**: 1-2 hours (API dependent)
- **Total Runtime**: 8-12 hours for comprehensive 25-state scrape

*Can be parallelized to reduce to 3-4 hours*

### Expected Yield (per 25 states)
- **Law Schools**: 50-70 schools × 3-5 contacts = **150-350 contacts**
- **Paralegal Programs**: 200-300 programs × 2-4 contacts = **400-1200 contacts**
- **Total**: **550-1550 high-quality contacts**

---

## Phase 7: Maintenance & Scaling Considerations

### API Cost Management
- Monitor API usage daily
- When trial ends, cost per 1000 contacts:
  - Hunter.io: ~$50/month (cheaper bulk plans available)
  - Email Validation: ~$10/month (bulk discounts)
  - Proxycurl: ~$100/month (optional, can skip)
- Total: ~$60-160/month for sustained usage

### Re-scraping Strategy
- Institution websites change slowly
- Re-scrape schedule:
  - Full re-scrape: Every 6 months
  - Incremental updates: Monthly (new hires, role changes)
  - Email re-validation: Every 3 months

### Scaling to 50 States
- Current design handles all 50 states
- Just adjust state input parameter
- Consider distributed scraping for faster processing
- Database recommended for >5000 contacts (SQLite sufficient)

---

## Risk Mitigation

### Technical Risks
1. **Website structure changes**
   - Mitigation: Adaptive scraping, fallback strategies, manual URL input option
   
2. **API rate limits**
   - Mitigation: Built-in rate limiting, caching, batch processing
   
3. **Anti-scraping measures**
   - Mitigation: Respect robots.txt, random delays, rotating user agents

### Data Quality Risks
1. **Outdated contact info**
   - Mitigation: LinkedIn verification, email validation, recency indicators
   
2. **False positives in title matching**
   - Mitigation: Confidence scoring, manual review flags, multiple matching algorithms

3. **Email pattern failures**
   - Mitigation: Only construct if 3+ examples, validate all constructed emails