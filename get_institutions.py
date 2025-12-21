import pandas as pd
import requests
from io import BytesIO
from zipfile import ZipFile
import sys
from config import CLIENT_TYPES

def classify_institution(institution_name, institution_alias=''):
    """
    Classify an institution based on its name and alias.

    Args:
        institution_name (str): The institution's name
        institution_alias (str): The institution's alias/alternate name

    Returns:
        list: List of matching client types
    """
    if not institution_name:
        return []

    # Combine name and alias for searching
    search_text = f"{institution_name} {institution_alias}".lower()

    matched_types = []

    for client_type, config in CLIENT_TYPES.items():
        # Check if any keywords match
        keywords = config.get('keywords', [])
        keyword_match = any(keyword.lower() in search_text for keyword in keywords)

        # Check exclude keywords (if any)
        exclude_keywords = config.get('exclude_keywords', [])
        excluded = any(keyword.lower() in search_text for keyword in exclude_keywords)

        if keyword_match and not excluded:
            matched_types.append(client_type)

    return matched_types

def get_institutions(states, client_types=None):
    """
    Download IPEDS institutional data and filter by state codes and client types.

    Args:
        states (list): List of state abbreviations (e.g., ['CA', 'NY', 'TX'])
        client_types (list, optional): List of client types to filter by.
                                       If None, returns all institution types.
                                       Options: 'Charter/K-12', 'Undergraduate', 'Graduate/Business',
                                               'Technical College', 'Continuing Education', 'Law School',
                                               'Paralegal Program', 'Law Firm'

    Returns:
        pd.DataFrame: Filtered institutions data with CLIENT_TYPE column
    """
    url = "https://nces.ed.gov/ipeds/datacenter/data/HD2023.zip"

    # Normalize state codes to uppercase
    states = [s.strip().upper() for s in states]

    print("Downloading IPEDS data...")
    print(f"Target states: {', '.join(states)}")

    try:
        # Download the ZIP file
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        print(f"Downloaded {len(response.content) / 1024 / 1024:.2f} MB")

        # Extract CSV from ZIP
        print("Extracting data...")
        with ZipFile(BytesIO(response.content)) as zip_file:
            # Get the CSV filename (should be HD2023.csv)
            csv_filename = [name for name in zip_file.namelist() if name.endswith('.csv')][0]
            print(f"Reading {csv_filename}...")

            # Read CSV into DataFrame
            with zip_file.open(csv_filename) as csv_file:
                df = pd.read_csv(csv_file, encoding='latin-1', low_memory=False)

        print(f"Total institutions in dataset: {len(df)}")

        # Filter by state codes
        # STABBR is the state abbreviation column in IPEDS data
        if 'STABBR' not in df.columns:
            print("Warning: STABBR column not found. Available columns:")
            print(df.columns.tolist())
            return pd.DataFrame()

        filtered_df = df[df['STABBR'].isin(states)].copy()
        print(f"Institutions found in target states: {len(filtered_df)}")

        if len(filtered_df) == 0:
            print(f"Warning: No institutions found for states: {states}")
            print(f"Available states: {sorted(df['STABBR'].unique())}")
            return filtered_df

        # Classify institutions by client type
        print("\nClassifying institutions...")
        filtered_df['CLIENT_TYPES'] = filtered_df.apply(
            lambda row: classify_institution(
                row.get('INSTNM', ''),
                row.get('IALIAS', '')
            ),
            axis=1
        )

        # Convert list to comma-separated string for easier viewing
        filtered_df['CLIENT_TYPE'] = filtered_df['CLIENT_TYPES'].apply(
            lambda types: ', '.join(types) if types else 'Unclassified'
        )

        # Filter by client types if specified
        if client_types:
            print(f"Filtering by client types: {', '.join(client_types)}")
            # Keep institutions that match at least one requested client type
            filtered_df = filtered_df[
                filtered_df['CLIENT_TYPES'].apply(
                    lambda types: any(ct in types for ct in client_types)
                )
            ]
            print(f"Institutions matching client types: {len(filtered_df)}")

        # Display breakdown by state
        print("\nBreakdown by state:")
        for state in states:
            count = len(filtered_df[filtered_df['STABBR'] == state])
            if count > 0:
                print(f"  {state}: {count} institutions")

        # Display breakdown by client type
        if len(filtered_df) > 0:
            print("\nBreakdown by client type:")
            all_types = []
            for types_list in filtered_df['CLIENT_TYPES']:
                all_types.extend(types_list)

            from collections import Counter
            type_counts = Counter(all_types)

            if type_counts:
                for client_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                    print(f"  {client_type}: {count} institutions")
            else:
                print("  No institutions classified")

        # Save to CSV
        output_file = "institutions.csv"
        filtered_df.to_csv(output_file, index=False)
        print(f"\nData saved to {output_file}")
        print(f"Columns: {len(filtered_df.columns)}, Rows: {len(filtered_df)}")

        return filtered_df

    except requests.exceptions.RequestException as e:
        print(f"Error downloading data: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing data: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Display available client types
    print("Available client types:")
    for i, client_type in enumerate(CLIENT_TYPES.keys(), 1):
        print(f"  {i}. {client_type}")

    print("\nFilter options:")
    states_input = input("Enter state codes separated by commas (e.g., CA,NY,TX): ")
    states = [s.strip() for s in states_input.split(",")]

    if not states or states == ['']:
        print("No states provided. Exiting.")
        sys.exit(1)

    # Optional client type filtering
    client_types_input = input("\nEnter client types to filter (comma-separated) or press Enter for all: ").strip()

    client_types = None
    if client_types_input:
        client_types = [ct.strip() for ct in client_types_input.split(",")]

        # Validate client types
        invalid_types = [ct for ct in client_types if ct not in CLIENT_TYPES]
        if invalid_types:
            print(f"Warning: Invalid client types: {invalid_types}")
            print(f"Valid options: {list(CLIENT_TYPES.keys())}")
            sys.exit(1)

    get_institutions(states, client_types)