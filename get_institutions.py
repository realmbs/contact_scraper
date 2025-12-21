import pandas as pd
import requests
from io import StringIO

def get_institutions(states) :
  # download ipeds data
  url: str = "https://nces.ed.gov/ipeds/datacenter/data/HD2023.zip"

  print("Downloading IPEDS data...")

  institutions = []

  for state in states:
    print(f"Processing state: {state}")
    pass

  df = pd.DataFrame(institutions)
  df.to_csv("institutions.csv", index=False)
  
  print(f"Data saved to institutions.csv")

if __name__ == "__main__":
  states = input("Enter state codes separated by commas (e.g., CA,NY,TX): ").split(",")
  states = [s.strip() for s in states]
  get_institutions(states)