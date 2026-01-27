"""
Test script for the CalTrans PeMS data scraper.

Requirements:
1. Create a free account at http://pems.dot.ca.gov (click "Register" link)
2. Create a .env file with your credentials:
   PEMS_USERNAME=your_username
   PEMS_PASSWORD=your_password

Bay Area relevant districts:
- District 4: San Francisco Bay Area (Oakland, San Francisco, San Jose)
"""

import sys
import os

from dotenv import load_dotenv
load_dotenv()

# Add the caltrans-pems package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'caltrans-pems'))

from pems.handler import PeMSHandler

USERNAME = os.environ.get('PEMS_USERNAME')
PASSWORD = os.environ.get('PEMS_PASSWORD')

def main():
    if not USERNAME or not PASSWORD:
        print("Please set your PeMS credentials!")
        print("Create a .env file with:")
        print("  PEMS_USERNAME=your_username")
        print("  PEMS_PASSWORD=your_password")
        print("\nRegister for a free account at: http://pems.dot.ca.gov")
        return

    print("Connecting to PeMS...")
    handler = PeMSHandler(username=USERNAME, password=PASSWORD)

    # Get available file types
    print("\nAvailable file types:")
    file_types = handler.get_file_types()
    for ft in file_types:
        print(f"  - {ft}")

    # Get districts for a specific file type (e.g., station_5min)
    print("\nAvailable districts for 'station_5min':")
    districts = handler.get_districts('station_5min')
    print(f"  {districts}")

    # Example: List available files for District 4 (Bay Area) in 2023
    print("\nSearching for files in District 4 (Bay Area), 2023...")
    files = handler.get_files(
        start_year=2023,
        end_year=2023,
        districts=['4'],  # District 4 = Bay Area
        file_types=['station_5min'],
        months=['01']  # Just January to start
    )

    print(f"\nFound {len(files)} files:")
    for f in files[:5]:  # Show first 5
        print(f"  {f['file_name']} ({f['megabites']} MB)")

    if len(files) > 5:
        print(f"  ... and {len(files) - 5} more")

if __name__ == '__main__':
    main()
