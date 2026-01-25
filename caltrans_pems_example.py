"""
Example: Using caltrans-pems package for automated PeMS data retrieval

Installation: pip install git+https://github.com/Seb-Good/caltrans-pems.git
Requirements: mechanize, beautifulsoup4, pandas, numpy

CalTrans District Reference for Bay Area Analysis:
| District | Region                      | Relevance to Project                              |
|----------|-----------------------------|----------------------------------------------------|
| 4        | San Francisco Bay Area      | Core Bay Area - tech company HQs                  |
| 3        | Sacramento / North          | Includes I-80 corridor (Tracy, Fairfield commuters)|
| 10       | Stockton / Central Valley   | Tracy, Manteca, Modesto - outer suburb commutes   |
| 5        | San Luis Obispo / Central Coast | Less relevant                                 |

Key Corridors for Commuter Analysis:
- I-680 (Tri-Valley / Dublin / Pleasanton)
- I-580 (Livermore / Tracy / Central Valley)
- I-880 (Oakland / Fremont / San Jose)
- I-80 (Bay Bridge / Richmond / Fairfield / Vacaville)
- US-101 (Peninsula / South Bay / Gilroy)
"""

import os
import glob
import pandas as pd

# =============================================================================
# 1. Initialize handler with PeMS credentials
# =============================================================================
# You need a free account at http://pems.dot.ca.gov

from pems.handler import PeMSHandler

handler = PeMSHandler(
    username='your_pems_username',
    password='your_pems_password',
    debug=True  # Enable logging for troubleshooting
)

# =============================================================================
# 2. Explore available data types
# =============================================================================

# Get list of available file types (e.g., 'station_5min', 'station_hour', etc.)
file_types = handler.get_file_types()
print("Available file types:", file_types)

# Get available districts for a specific file type
# Bay Area districts: District 4 (SF Bay Area), District 3 (Sacramento area)
districts = handler.get_districts(file_type='station_hour')
print("Available districts:", districts)

# =============================================================================
# 3. Query available files for download
# =============================================================================

# Search for files matching criteria
# District 4 = San Francisco Bay Area
available_files = handler.get_files(
    file_type='station_hour',    # Hourly station data
    district_id='4',             # Bay Area
    years=[2019, 2020, 2021, 2022, 2023, 2024, 2025]
)

print(f"Found {len(available_files)} files available for download")
print(available_files.head())

# =============================================================================
# 4. Download files
# =============================================================================

# Set download directory
download_path = './pems_raw_data'
os.makedirs(download_path, exist_ok=True)

# Download files (automatically skips previously downloaded files)
handler.download_files(
    files=available_files,
    output_path=download_path
)

# =============================================================================
# 5. Download specific data types for Bay Area analysis
# =============================================================================

# For traffic volume analysis, useful file types include:
#   - 'station_5min'  : 5-minute aggregated station data
#   - 'station_hour'  : Hourly aggregated station data
#   - 'station_day'   : Daily aggregated station data
#   - 'station_meta'  : Station metadata (location, lanes, etc.)

# Download daily data for multiple years (more manageable file sizes)
for year in range(2019, 2026):
    daily_files = handler.get_files(
        file_type='station_day',
        district_id='4',  # Bay Area
        years=[year]
    )
    handler.download_files(
        files=daily_files,
        output_path=f'./pems_raw_data/daily/{year}'
    )
    print(f"Downloaded {year} daily data")


# =============================================================================
# 6. Processing downloaded data for corridor-specific analysis
# =============================================================================

def load_and_filter_corridor_data():
    """Example of processing downloaded PeMS data for specific corridors."""

    # Load station metadata to identify corridor stations
    # Station metadata includes location (lat/lon), freeway, direction, etc.
    station_meta = pd.read_csv('./pems_raw_data/d04_text_meta_yyyy_mm_dd.txt', sep='\t')

    # Filter to specific freeways of interest
    # These corridors connect outer suburbs to Bay Area job centers
    commuter_corridors = {
        'I-580': station_meta[station_meta['Fwy'] == 580],  # Livermore/Tracy
        'I-680': station_meta[station_meta['Fwy'] == 680],  # Tri-Valley
        'I-80':  station_meta[station_meta['Fwy'] == 80],   # East Bay / Fairfield
    }

    # Get station IDs for each corridor
    corridor_stations = {}
    for corridor, df in commuter_corridors.items():
        # Focus on westbound (toward SF/Oakland) morning commute direction
        westbound = df[df['Dir'].isin(['W', 'S'])]  # West or South toward city
        corridor_stations[corridor] = westbound['ID'].tolist()
        print(f"{corridor}: {len(westbound)} westbound stations")

    return corridor_stations


def load_corridor_data(year, corridor_station_ids):
    """Load daily data and filter to specific station IDs."""
    files = glob.glob(f'./pems_raw_data/daily/{year}/*.txt')

    dfs = []
    for f in files:
        df = pd.read_csv(f, sep='\t')
        df = df[df['Station'].isin(corridor_station_ids)]
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)


def calculate_peak_hour_volume(hourly_df):
    """Extract 6-9 AM weekday traffic as proxy for commuter volume.

    Use this with hourly data instead of daily.
    """
    # Filter to weekdays only
    hourly_df['Date'] = pd.to_datetime(hourly_df['Timestamp']).dt.date
    hourly_df['Hour'] = pd.to_datetime(hourly_df['Timestamp']).dt.hour
    hourly_df['DayOfWeek'] = pd.to_datetime(hourly_df['Timestamp']).dt.dayofweek

    # Weekdays (Mon=0, Fri=4), morning peak (6-9 AM)
    peak = hourly_df[
        (hourly_df['DayOfWeek'] < 5) &
        (hourly_df['Hour'] >= 6) &
        (hourly_df['Hour'] < 9)
    ]

    # Aggregate by month
    peak['Month'] = pd.to_datetime(peak['Date']).dt.to_period('M')
    monthly_peak = peak.groupby('Month')['Flow'].sum().reset_index()
    monthly_peak.columns = ['Month', 'Peak_AM_Volume']

    return monthly_peak


# =============================================================================
# Example usage
# =============================================================================

if __name__ == '__main__':
    # Get corridor station IDs
    corridor_stations = load_and_filter_corridor_data()

    # Load I-580 data (key Tracy/Central Valley commuter corridor)
    i580_data = {}
    for year in range(2019, 2026):
        i580_data[year] = load_corridor_data(year, corridor_stations['I-580'])
        print(f"Loaded {len(i580_data[year])} records for I-580 in {year}")
