# Bay Area Migration & Return-to-Office Analysis

A data analysis project investigating the relationship between work-from-home policies, suburban migration patterns, and traffic trends in the San Francisco Bay Area (2019-2025).

## Research Questions

This project aims to test two hypotheses:

1. **Did work-from-home policies contribute to migration to suburbs surrounding the Bay Area?**
2. **Did subsequent return-to-office (RTO) mandates cause an increase in traffic from surrounding areas?**

## Project Structure

```
bay_area_migration/
├── Data Files
│   ├── bay_area_migration_data_sources.xlsx   # Reference file tracking data sources
│   ├── bay_area_rto_timeline.xlsx             # Initial RTO timeline data
│   ├── bay_area_rto_timeline_expanded.xlsx    # Expanded RTO dataset
│   └── pems_output{YEAR}N[_40].xlsx           # PeMS traffic data (2019-2025)
│
├── Analysis
│   ├── pems_data_analysis.ipynb               # Jupyter notebook for traffic analysis
│   └── pems_combined_data.csv                 # Combined traffic dataset
│
├── Visualizations
│   ├── visualize_rto_timeline.py              # RTO timeline chart generator
│   ├── rto_timeline_visualization.png         # Company work policy transitions
│   └── vmt_monthly_histogram.png              # Monthly VMT bar chart
│
└── Documentation
    ├── README.md
    └── CLAUDE.md
```

## Data Sources

### RTO Timeline Data
Tracks work policy transitions for major Bay Area tech companies:
- Work From Home (WFH) start dates
- Hybrid transition dates
- 5-day Return to Office dates

### PeMS Traffic Data
California Performance Measurement System (PeMS) data containing:
- **VMT** - Vehicle Miles Traveled
- **Delay** - Traffic delay metrics at V_t=60 and V_t=40 thresholds
- **Productivity Loss** - Lane-mile-hours lost to congestion

Data spans January 2019 through December 2025, providing pre-pandemic baseline through post-RTO periods.

## Visualizations

### RTO Timeline Chart
![RTO Timeline](rto_timeline_visualization.png)

Horizontal bar chart showing company work policy transitions:
- 🟢 Green: Work From Home (Full Remote)
- 🟡 Yellow: Hybrid (2-4 days/week in office)
- 🔴 Red: 5-Day Return to Office
- 🔵 Blue: Remote-First (Permanent Policy)

### VMT Monthly Histogram
![VMT Histogram](vmt_monthly_histogram.png)

Monthly vehicle miles traveled in the Bay Area, showing the dramatic drop during COVID lockdowns and subsequent recovery patterns.

## Key Time Periods

| Period | Dates | Characteristics |
|--------|-------|-----------------|
| Pre-COVID Baseline | 2019 | Normal commute patterns |
| COVID Lockdowns | Mar 2020 - 2021 | Sharp VMT decline, mass WFH adoption |
| Hybrid Era | 2021 - 2024 | Gradual traffic recovery, mixed policies |
| RTO Mandates | 2024 - 2025 | Major companies requiring 5-day office return |

## Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install pandas matplotlib openpyxl jupyter
```

## Usage

### Generate RTO Timeline Visualization
```bash
python visualize_rto_timeline.py
```

### Run Traffic Analysis
```bash
jupyter notebook pems_data_analysis.ipynb
```

## Geographic Definitions

- **Bay Area**: Within 45 minutes of major white-collar offices (San Francisco, San Jose, Oakland)
- **Surrounding Suburbs**: Greater than 45 minutes from major offices (Tracy, Stockton, Sacramento corridor, etc.)

## Status

This is an ongoing research project gathering evidence to support or refute the stated hypotheses. Contributions of additional data sources or analysis approaches are welcome.
