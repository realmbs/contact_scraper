#!/usr/bin/env python3
"""
End-to-end integration test for Phase 3 (Email Validation & Enrichment).

Tests the complete pipeline:
1. Create sample contacts with emails
2. Run email enrichment
3. Verify validation results
4. Check confidence score updates
"""

import pandas as pd
from unittest.mock import patch, Mock

from modules.email_validator import enrich_contact_data


def test_phase3_integration():
    """Test complete Phase 3 enrichment pipeline."""

    print("=" * 70)
    print("PHASE 3 INTEGRATION TEST")
    print("=" * 70)
    print()

    # Create sample contacts (simulating Phase 2 output)
    contacts = pd.DataFrame([
        {
            'first_name': 'John',
            'last_name': 'Doe',
            'title': 'Professor of Law',
            'institution': 'Stanford Law School',
            'institution_url': 'https://law.stanford.edu',
            'email': 'jdoe@law.stanford.edu',
            'phone': '650-123-4567',
            'confidence_score': 60,
            'matched_role': 'Legal Writing Director',
            'program_type': 'Law School'
        },
        {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'title': 'Associate Dean',
            'institution': 'Stanford Law School',
            'institution_url': 'https://law.stanford.edu',
            'email': 'jsmith@law.stanford.edu',
            'phone': '650-123-4568',
            'confidence_score': 70,
            'matched_role': 'Associate Dean for Academic Affairs',
            'program_type': 'Law School'
        },
        {
            'first_name': 'Bob',
            'last_name': 'Johnson',
            'title': 'Librarian',
            'institution': 'UCLA Law School',
            'institution_url': 'https://law.ucla.edu',
            'email': 'bjohnson@law.ucla.edu',
            'phone': '',
            'confidence_score': 50,
            'matched_role': 'Library Director',
            'program_type': 'Law School'
        },
        {
            'first_name': 'Alice',
            'last_name': 'Williams',
            'title': 'Program Director',
            'institution': 'City College Paralegal Program',
            'institution_url': 'https://www.ccsf.edu',
            'email': '',  # Missing email - will test email finding
            'phone': '415-123-4567',
            'confidence_score': 40,
            'matched_role': 'Paralegal Program Director',
            'program_type': 'Paralegal Program'
        },
    ])

    print(f"Sample contacts created: {len(contacts)}")
    print(f"  With email: {len(contacts[contacts['email'] != ''])}")
    print(f"  Without email: {len(contacts[contacts['email'] == ''])}")
    print()

    # Mock validation responses (simulating API calls without using real credits)
    def mock_validate_auto(email):
        """Mock email validation for testing."""
        # Simulate different validation results
        if 'stanford' in email:
            return {
                'email': email,
                'status': 'valid',
                'score': 100,
                'is_catchall': False,
                'is_disposable': False,
                'service': 'neverbounce'
            }
        elif 'ucla' in email:
            return {
                'email': email,
                'status': 'catch-all',
                'score': 70,
                'is_catchall': True,
                'is_disposable': False,
                'service': 'zerobounce'
            }
        else:
            return {
                'email': email,
                'status': 'unknown',
                'score': 40,
                'is_catchall': False,
                'is_disposable': False,
                'service': 'none'
            }

    def mock_find_email(first_name, last_name, domain):
        """Mock Hunter.io email finder."""
        if 'ccsf.edu' in domain:
            return f"{first_name.lower()}.{last_name.lower()}@{domain}"
        return None

    # Run enrichment with mocked API calls
    with patch('modules.email_validator.validate_email_auto', side_effect=mock_validate_auto):
        with patch('modules.email_validator.find_email_with_hunter', side_effect=mock_find_email):
            enriched_contacts = enrich_contact_data(contacts)

    print()
    print("=" * 70)
    print("ENRICHMENT RESULTS")
    print("=" * 70)
    print()

    # Verify results
    print(f"Total contacts: {len(enriched_contacts)}")
    print()

    # Check email coverage
    with_email = len(enriched_contacts[enriched_contacts['email'] != ''])
    email_coverage = (with_email / len(enriched_contacts) * 100) if len(enriched_contacts) > 0 else 0
    print(f"Contacts with email: {with_email} ({email_coverage:.1f}%)")

    # Check validation columns added
    assert 'email_status' in enriched_contacts.columns, "Missing email_status column"
    assert 'email_score' in enriched_contacts.columns, "Missing email_score column"
    assert 'email_is_catchall' in enriched_contacts.columns, "Missing email_is_catchall column"
    print("✓ Validation columns added")

    # Check email quality stats
    validated = len(enriched_contacts[enriched_contacts['email_status'] == 'valid'])
    catchall = len(enriched_contacts[enriched_contacts['email_is_catchall'] == True])

    print(f"  Validated deliverable: {validated}")
    print(f"  Catch-all domains: {catchall}")
    print()

    # Check confidence score updates
    print("Confidence Score Updates:")
    for idx, row in enriched_contacts.iterrows():
        name = f"{row['first_name']} {row['last_name']}"
        old_score = contacts.loc[idx, 'confidence_score']
        new_score = row['confidence_score']
        change = new_score - old_score

        print(f"  {name}: {old_score} → {new_score} ({change:+d})")
    print()

    # Verify expected score changes
    # John Doe: valid email (+30) = 60 + 30 = 90
    assert enriched_contacts.iloc[0]['confidence_score'] == 90, "John Doe score incorrect"

    # Jane Smith: valid email (+30) = 70 + 30 = 100
    assert enriched_contacts.iloc[1]['confidence_score'] == 100, "Jane Smith score incorrect"

    # Bob Johnson: catch-all (-20) = 50 - 20 = 30
    assert enriched_contacts.iloc[2]['confidence_score'] == 30, "Bob Johnson score incorrect"

    # Alice Williams: email found (+20 for hunter) = 40 + 20 = 60
    assert enriched_contacts.iloc[3]['confidence_score'] == 60, "Alice Williams score incorrect"

    print("✓ All confidence scores updated correctly")
    print()

    # Verify 80%+ email coverage goal
    if email_coverage >= 80.0:
        print(f"✅ SUCCESS: {email_coverage:.1f}% email coverage (target: 80%+)")
    else:
        print(f"⚠️  WARNING: {email_coverage:.1f}% email coverage (target: 80%+)")

    # Verify validation rate
    validation_rate = (validated / with_email * 100) if with_email > 0 else 0
    if validation_rate >= 50.0:  # Lower threshold for mock test
        print(f"✅ SUCCESS: {validation_rate:.1f}% validation rate")
    else:
        print(f"⚠️  WARNING: {validation_rate:.1f}% validation rate")

    print()
    print("=" * 70)
    print("PHASE 3 INTEGRATION TEST COMPLETE")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  ✓ Email enrichment pipeline functional")
    print(f"  ✓ Validation columns added correctly")
    print(f"  ✓ Confidence scores updated based on email quality")
    print(f"  ✓ Email finding for missing emails working")
    print(f"  ✓ {email_coverage:.1f}% email coverage achieved")
    print()

    return enriched_contacts


if __name__ == '__main__':
    try:
        result = test_phase3_integration()
        print("✅ All integration tests passed!")
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        import sys
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import sys
        sys.exit(1)
