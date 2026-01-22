#!/usr/bin/env python3
"""
RTO Timeline Visualization Script

Generates a horizontal bar chart showing Bay Area tech companies'
work policy transitions from WFH -> Hybrid -> Return to Office (2020-2026).

Usage:
    python visualize_rto_timeline.py

Output:
    rto_timeline_visualization.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np
import re

# Configuration
INPUT_FILE = 'bay_area_rto_timeline_expanded.xlsx'
OUTPUT_FILE = 'rto_timeline_visualization.png'

# Date range for visualization
START_DATE = datetime(2020, 1, 1)
END_DATE = datetime(2026, 1, 31)

# Colors for different work policies
COLORS = {
    'wfh': '#2ecc71',      # Green - Work From Home
    'hybrid': '#f1c40f',   # Yellow - Hybrid
    'rto': '#e74c3c',      # Red - 5-Day RTO
    'remote_first': '#3498db'  # Blue - Remote-First (permanent)
}

# Milestone events to mark on timeline
MILESTONES = [
    (datetime(2020, 3, 15), 'COVID\nLockdowns'),
    (datetime(2022, 6, 1), 'Tesla/Twitter\nRTO'),
    (datetime(2025, 1, 2), 'Amazon\n5-Day'),
]

def parse_date(date_str):
    """Parse various date formats from the spreadsheet."""
    if pd.isna(date_str) or date_str in ['Not announced', 'Limited data', 'Limited mandate']:
        return None

    # Remove parenthetical notes like "(3 days/week)"
    date_str = re.sub(r'\s*\([^)]*\)', '', str(date_str)).strip()

    # Handle "N/A" variants
    if date_str.startswith('N/A'):
        return None

    # Common month-year patterns
    month_year_patterns = [
        (r'(\w+)\s+(\d{4})', '%B %Y'),  # "March 2020"
        (r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', '%B %d %Y'),  # "January 2, 2025"
    ]

    for pattern, fmt in month_year_patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                if fmt == '%B %Y':
                    return datetime.strptime(f"{match.group(1)} {match.group(2)}", fmt)
                else:
                    return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", fmt)
            except ValueError:
                pass

    # Handle year-only like "2022 (post-Musk acquisition)" or "2021"
    year_match = re.search(r'\b(20\d{2})\b', date_str)
    if year_match:
        return datetime(int(year_match.group(1)), 6, 1)  # Default to June

    return None


def is_remote_first(row):
    """Determine if company adopted permanent remote-first policy."""
    hybrid_str = str(row['Hybrid Transition Date']).lower() if pd.notna(row['Hybrid Transition Date']) else ''
    notes = str(row['Notes']).lower() if pd.notna(row['Notes']) else ''

    remote_keywords = ['remote-first', 'digital-first', 'digital by default',
                       'team anywhere', 'live and work anywhere', 'went remote-first',
                       'went digital-first']

    return any(kw in hybrid_str or kw in notes for kw in remote_keywords)


def get_company_timeline(row):
    """
    Build timeline segments for a company.
    Returns list of (start_date, end_date, policy_type) tuples.
    """
    segments = []

    wfh_start = parse_date(row['WFH Start Date']) or datetime(2020, 3, 15)
    hybrid_date = parse_date(row['Hybrid Transition Date'])
    rto_date = parse_date(row['5-Day RTO Date'])

    # Check if company is remote-first (permanent WFH)
    if is_remote_first(row):
        segments.append((wfh_start, END_DATE, 'remote_first'))
        return segments

    # Check if company skipped hybrid (went directly to RTO)
    hybrid_str = str(row['Hybrid Transition Date']).lower() if pd.notna(row['Hybrid Transition Date']) else ''
    skipped_hybrid = 'skipped' in hybrid_str or 'n/a' in hybrid_str.lower()

    if skipped_hybrid and rto_date:
        # WFH until RTO
        segments.append((wfh_start, rto_date, 'wfh'))
        segments.append((rto_date, END_DATE, 'rto'))
    elif hybrid_date:
        # WFH -> Hybrid
        segments.append((wfh_start, hybrid_date, 'wfh'))
        if rto_date:
            # Hybrid -> RTO
            segments.append((hybrid_date, rto_date, 'hybrid'))
            segments.append((rto_date, END_DATE, 'rto'))
        else:
            # Still hybrid
            segments.append((hybrid_date, END_DATE, 'hybrid'))
    else:
        # Still WFH or status unclear - show as hybrid (most likely current state)
        segments.append((wfh_start, END_DATE, 'hybrid'))

    return segments


def create_visualization(df):
    """Create the RTO timeline visualization."""
    # Filter to companies with good data (exclude Limited data rows)
    df_filtered = df[~df['Hybrid Transition Date'].astype(str).str.contains('Limited data', na=False)].copy()

    # Sort companies by RTO date (companies with 5-day RTO first, then by date)
    def sort_key(row):
        rto_date = parse_date(row['5-Day RTO Date'])
        if rto_date:
            return (0, rto_date)
        hybrid_date = parse_date(row['Hybrid Transition Date'])
        if hybrid_date:
            return (1, hybrid_date)
        return (2, datetime(2099, 1, 1))

    df_filtered['sort_key'] = df_filtered.apply(sort_key, axis=1)
    df_filtered = df_filtered.sort_values('sort_key', ascending=False)

    # Create figure
    fig, ax = plt.subplots(figsize=(14, 10))

    companies = df_filtered['Employer'].tolist()
    y_positions = range(len(companies))

    # Plot timeline bars for each company
    for idx, (_, row) in enumerate(df_filtered.iterrows()):
        segments = get_company_timeline(row)
        for start, end, policy in segments:
            if start and end:
                width = (end - start).days
                ax.barh(idx, width, left=mdates.date2num(start),
                       color=COLORS[policy], height=0.7, edgecolor='white', linewidth=0.5)

    # Add milestone lines
    for milestone_date, label in MILESTONES:
        ax.axvline(x=mdates.date2num(milestone_date), color='darkred',
                   linestyle='--', linewidth=1, alpha=0.7)
        ax.text(mdates.date2num(milestone_date), len(companies) + 0.5, label,
                ha='center', va='bottom', fontsize=9, color='darkred', fontweight='bold')

    # Configure axes
    ax.set_yticks(y_positions)
    ax.set_yticklabels(companies)
    ax.set_ylim(-0.5, len(companies) + 1.5)

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b\n%Y'))
    ax.set_xlim(mdates.date2num(START_DATE), mdates.date2num(END_DATE))

    # Labels and title
    ax.set_xlabel('Timeline', fontsize=12)
    ax.set_ylabel('Company', fontsize=12)
    ax.set_title('Bay Area Tech Companies: Work Policy Timeline (2020-2026)\n'
                 'Transitions from WFH → Hybrid → Return to Office',
                 fontsize=14, fontweight='bold')

    # Legend
    legend_elements = [
        plt.Rectangle((0, 0), 1, 1, facecolor=COLORS['wfh'], label='Work From Home (Full Remote)'),
        plt.Rectangle((0, 0), 1, 1, facecolor=COLORS['hybrid'], label='Hybrid (2-4 days/week in office)'),
        plt.Rectangle((0, 0), 1, 1, facecolor=COLORS['rto'], label='5-Day Return to Office'),
        plt.Rectangle((0, 0), 1, 1, facecolor=COLORS['remote_first'], label='Remote-First (Permanent Policy)'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9)

    # Add summary statistics
    rto_count = df_filtered['5-Day RTO Date'].apply(
        lambda x: parse_date(x) is not None and parse_date(x) <= datetime(2026, 1, 20)
    ).sum()
    hybrid_count = len(df_filtered) - rto_count - df_filtered.apply(is_remote_first, axis=1).sum()
    remote_count = df_filtered.apply(is_remote_first, axis=1).sum()

    summary = f"As of Jan 2026: {rto_count} companies at 5-day RTO | {hybrid_count} still hybrid | {remote_count} remote-first"
    ax.text(0.5, -0.08, summary, transform=ax.transAxes, ha='center',
            fontsize=9, color='gray', style='italic')

    # Grid and styling
    ax.grid(axis='x', alpha=0.3)
    ax.set_axisbelow(True)

    plt.tight_layout()
    plt.savefig(OUTPUT_FILE, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    print(f"Visualization saved to {OUTPUT_FILE}")


def main():
    """Main entry point."""
    print(f"Reading data from {INPUT_FILE}...")
    df = pd.read_excel(INPUT_FILE)
    print(f"Found {len(df)} companies")

    print("Creating visualization...")
    create_visualization(df)
    print("Done!")


if __name__ == '__main__':
    main()
