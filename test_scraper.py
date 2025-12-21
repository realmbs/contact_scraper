#!/usr/bin/env python3
"""
Test script to run scraper on a small sample of institutions
"""
import pandas as pd
from scrape_contacts import ContactScraper

def create_test_sample():
    """Create a small sample CSV for testing"""
    # Load the full dataset (utf-8-sig handles BOM)
    df = pd.read_csv('institutions.csv', encoding='utf-8-sig')

    # Strip BOM from column names if present
    df.columns = df.columns.str.replace('ï»¿', '', regex=False)

    # Select a diverse sample:
    # - 1 Law School
    # - 1 Technical College
    # - 1 Undergraduate
    # - 1 Charter/K-12
    # - 1 Graduate/Business

    samples = []

    # Get one of each type
    for client_type in ['Law School', 'Technical College', 'Undergraduate',
                        'Charter/K-12', 'Graduate/Business']:
        matching = df[df['CLIENT_TYPE'].str.contains(client_type, na=False)]
        if len(matching) > 0:
            # Get first match that has a website
            for idx, row in matching.iterrows():
                if pd.notna(row.get('WEBADDR')) and row.get('WEBADDR'):
                    samples.append(row)
                    print(f"Selected {client_type}: {row['INSTNM']}")
                    break

    # Create test CSV
    test_df = pd.DataFrame(samples)
    test_df.to_csv('test_institutions.csv', index=False)
    print(f"\nCreated test_institutions.csv with {len(test_df)} institutions")
    return len(test_df)

if __name__ == "__main__":
    print("Creating test sample...")
    count = create_test_sample()

    if count > 0:
        print("\n" + "="*80)
        print("Starting test scrape...")
        print("="*80 + "\n")

        # Run scraper on test sample
        scraper = ContactScraper(resume=False)
        scraper.run(input_file='test_institutions.csv', output_file='test_contacts.csv')

        print("\n" + "="*80)
        print("Test complete! Check test_contacts.csv for results")
        print("="*80)
    else:
        print("No test samples found")
