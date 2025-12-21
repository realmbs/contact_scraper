import pandas as pd
import requests
from io import BytesIO
from zipfile import ZipFile
import sys

def get_institutions(states):
    """
    Download IPEDS institutional data and filter by state codes.

    Args:
        states (list): List of state abbreviations (e.g., ['CA', 'NY', 'TX'])

    Returns:
        pd.DataFrame: Filtered institutions data
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

        filtered_df = df[df['STABBR'].isin(states)]
        print(f"Institutions found in target states: {len(filtered_df)}")

        if len(filtered_df) == 0:
            print(f"Warning: No institutions found for states: {states}")
            print(f"Available states: {sorted(df['STABBR'].unique())}")
            return filtered_df

        # Display breakdown by state
        for state in states:
            count = len(filtered_df[filtered_df['STABBR'] == state])
            print(f"  {state}: {count} institutions")

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
    states_input = input("Enter state codes separated by commas (e.g., CA,NY,TX): ")
    states = [s.strip() for s in states_input.split(",")]

    if not states or states == ['']:
        print("No states provided. Exiting.")
        sys.exit(1)

    get_institutions(states)