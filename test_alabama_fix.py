#!/usr/bin/env python3
"""
Test Alabama Law School title extraction fix
"""
import pandas as pd
from modules.contact_extractor import scrape_institution_contacts

print("=" * 80)
print("ALABAMA LAW SCHOOL - TITLE EXTRACTION FIX VALIDATION")
print("=" * 80)
print()

# Get Alabama from master database
print("Step 1: Loading Alabama from master database...")
df = pd.read_csv('data/master_institutions.csv')
alabama = df[(df['state'] == 'AL') & (df['type'] == 'Law School')].iloc[0]

print(f"Institution: {alabama['name']}")
print(f"URL: {alabama['url']}")
print()
print("NOTE: This will take ~2-3 minutes to complete...")
print()

# Scrape contacts
print("Step 2: Extracting contacts...")
print("-" * 80)

contacts = scrape_institution_contacts(
    institution_name=alabama['name'],
    institution_url=alabama['url'],
    state=alabama['state'],
    program_type=alabama['type']
)

print()
print("=" * 80)
print("EXTRACTION RESULTS")
print("=" * 80)
print()
print(f"Total contacts extracted: {len(contacts)}")
print()

if contacts:
    # Analyze titles
    titles_with_names = 0
    titles_with_jobs = 0
    empty_titles = 0

    print("First 15 contacts:")
    print("-" * 80)

    for i, contact in enumerate(contacts[:15]):
        name = contact['full_name']
        title = contact['title']
        email = contact['email']

        # Check if title is actually a name (bug indicator)
        if title == name:
            status = "❌ BUG"
            titles_with_names += 1
        elif not title or title.strip() == '':
            status = "⚠️  EMPTY"
            empty_titles += 1
        elif any(keyword in title.lower() for keyword in ['professor', 'dean', 'director', 'librarian', 'assistant', 'associate', 'coordinator']):
            status = "✅ OK"
            titles_with_jobs += 1
        else:
            status = "⚠️  CHECK"

        print(f"{i+1}. {status}")
        print(f"   Name:  {name}")
        print(f"   Title: {title}")
        print(f"   Email: {email[:50] if email else 'None'}")
        print()

    # Summary
    print("=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print()
    print(f"Total contacts: {len(contacts)}")
    print(f"Valid job titles: {titles_with_jobs}")
    print(f"Empty titles: {empty_titles}")
    print(f"Name in title field (BUG): {titles_with_names}")
    print(f"Other/Unknown: {len(contacts[:15]) - titles_with_names - titles_with_jobs - empty_titles}")
    print()

    if titles_with_names == 0:
        print("✅ FIX VERIFIED: No title/name duplication detected in first 15 contacts!")
    else:
        print(f"⚠️  PARTIAL FIX: {titles_with_names} contacts still have name in title field")

    # Show unique titles
    print()
    print("Unique titles extracted (first 20):")
    print("-" * 80)
    unique_titles = list(set([c['title'] for c in contacts if c['title']]))[:20]
    for j, title in enumerate(unique_titles, 1):
        print(f"{j}. {title}")

else:
    print("❌ No contacts extracted")
