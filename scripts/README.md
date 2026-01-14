# Utility Scripts

This directory contains utility scripts for data preparation and analysis.

## Data Preparation
- **build_master_database.py** - Consolidate ABA and AAfPE data into master_institutions.csv
- **enrich_master_database.py** - Add geocoding and metadata enrichment

## Data Cleanup
- **fix_missing_names.py** - Fix missing name fields in contact data
- **filter_target_roles.py** - Analyze and filter contacts by role

## Debugging
- **debug_html.py** - HTML parsing debugging helper

## Usage
All scripts should be run from the project root:
```bash
cd /Users/markblaha/contact_scraper
python scripts/build_master_database.py
```
