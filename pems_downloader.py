"""
Simplified PeMS Data Downloader

Bypasses the broken HTML parsing in caltrans-pems by directly querying
the clearinghouse API with known file types.

CalTrans District Reference for Bay Area Analysis:
| District | Region                      |
|----------|-----------------------------|
| 4        | San Francisco Bay Area      |
| 3        | Sacramento / North          |
| 10       | Stockton / Central Valley   |

Common file types:
- station_5min  : 5-minute aggregated station data
- station_hour  : Hourly aggregated station data
- station_day   : Daily aggregated station data
- station_meta  : Station metadata (location, lanes, etc.)
"""

import os
import sys
import json
import time
import logging
import mechanize
import pandas as pd
from http.cookiejar import LWPCookieJar

BASE_URL = 'http://pems.dot.ca.gov'
CLEARING_HOUSE_URL = '{}/?srq=clearinghouse&district_id={}&yy={}&type={}&returnformat=text'

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)


class SimplePeMSDownloader:

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.browser = self._login()

    def _login(self):
        """Log into CalTrans PeMS."""
        browser = mechanize.Browser()
        browser.set_cookiejar(LWPCookieJar())
        browser.set_handle_equiv(True)
        browser.set_handle_referer(True)
        browser.set_handle_robots(False)
        browser.set_handle_redirect(mechanize.HTTPRedirectHandler)
        browser.set_handle_refresh(mechanize._http.HTTPRefreshProcessor(), max_time=1)

        browser.addheaders = [
            ('User-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        ]

        log.info('Opening PeMS login page...')
        browser.open(BASE_URL + "/?dnode=Clearinghouse")

        browser.select_form(nr=0)
        browser.form['username'] = self.username
        browser.form['password'] = self.password
        browser.submit()

        log.info('Logged in successfully.')
        return browser

    def get_available_files(self, district_id, year, file_type):
        """Query clearinghouse for available files."""
        url = CLEARING_HOUSE_URL.format(BASE_URL, district_id, year, file_type)
        log.info(f'Querying: district={district_id}, year={year}, type={file_type}')

        try:
            self.browser.open(url)
            response = json.loads(self.browser.response().read())

            files = []
            if 'data' in response:
                for month, month_files in response['data'].items():
                    for f in month_files:
                        files.append({
                            'district': district_id,
                            'year': year,
                            'month': month,
                            'file_type': file_type,
                            'file_name': f.get('file_name'),
                            'file_id': f.get('file_id'),
                            'bytes': f.get('bytes'),
                            'url': f.get('url')
                        })
            return files
        except Exception as e:
            log.error(f'Error querying clearinghouse: {e}')
            return []

    def download_file(self, file_info, save_path):
        """Download a single file."""
        os.makedirs(save_path, exist_ok=True)
        file_path = os.path.join(save_path, file_info['file_name'])

        if os.path.exists(file_path):
            log.info(f"Skipping {file_info['file_name']} (already exists)")
            return True

        try:
            log.info(f"Downloading {file_info['file_name']}...")
            self.browser.retrieve(BASE_URL + file_info['url'], file_path)
            log.info(f"Saved to {file_path}")
            time.sleep(2)  # Be nice to the server
            return True
        except Exception as e:
            log.error(f"Error downloading {file_info['file_name']}: {e}")
            return False

    def download_range(self, districts, years, file_types, save_path='./pems_data'):
        """Download files for a range of districts, years, and file types."""
        all_files = []

        for district in districts:
            for year in years:
                for file_type in file_types:
                    files = self.get_available_files(district, year, file_type)
                    all_files.extend(files)

        log.info(f'Found {len(all_files)} files to download')

        for f in all_files:
            subdir = os.path.join(save_path, f['file_type'], f'district_{f["district"]}', str(f['year']))
            self.download_file(f, subdir)

        return all_files


if __name__ == '__main__':
    # =========================================================================
    # Configuration - Update with your PeMS credentials
    # =========================================================================
    USERNAME = 'your_pems_username'
    PASSWORD = 'your_pems_password'

    # Districts: 4=Bay Area, 3=Sacramento, 10=Stockton/Central Valley
    DISTRICTS = ['4']

    # Years to download
    YEARS = [2019, 2020, 2021, 2022, 2023, 2024]

    # File types: station_day is smaller and good for initial analysis
    FILE_TYPES = ['station_day']

    # =========================================================================
    # Download
    # =========================================================================
    downloader = SimplePeMSDownloader(USERNAME, PASSWORD)

    # First, just list what's available
    files = downloader.get_available_files(
        district_id='4',
        year=2023,
        file_type='station_day'
    )

    print(f"\nFound {len(files)} files for District 4, 2023, station_day:")
    for f in files[:5]:
        print(f"  - {f['file_name']}")
    if len(files) > 5:
        print(f"  ... and {len(files) - 5} more")

    # Uncomment to actually download:
    # downloader.download_range(DISTRICTS, YEARS, FILE_TYPES, save_path='./pems_data')
