"""
Shared definitions for the Bay Area migration / RTO analysis scripts.

Edit the region lists or era dates here and every analysis script picks them up.

Geography is county-level, which is a coarse stand-in for the 45-minute rule:
eastern Contra Costa (Antioch, Brentwood) and southern Santa Clara (Gilroy) are
really >45 min from the office hubs but sit in "core" counties. A tract-level
split using geo/ + ca_xwalk.csv.gz would sharpen this.
"""

from datetime import datetime

import matplotlib.pyplot as plt

# --- Geography (California county FIPS codes, state 06) -----------------------

# "Bay Area": counties whose population mostly lives <=45 min from the major
# white-collar office hubs (SF, Oakland, Peninsula, Silicon Valley).
CORE_COUNTIES = {
    1: 'Alameda',
    13: 'Contra Costa',
    41: 'Marin',
    75: 'San Francisco',
    81: 'San Mateo',
    85: 'Santa Clara',
}

# "Surrounding suburbs": commuter-shed counties mostly >45 min from the hubs,
# grouped by corridor.
OUTER_GROUPS = {
    'North Bay / Solano': {95: 'Solano', 55: 'Napa', 97: 'Sonoma'},
    'Sacramento region': {67: 'Sacramento', 61: 'Placer', 17: 'El Dorado', 113: 'Yolo'},
    'Northern San Joaquin Valley': {77: 'San Joaquin', 99: 'Stanislaus', 47: 'Merced'},
    'Central Coast': {87: 'Santa Cruz', 69: 'San Benito', 53: 'Monterey'},
}

OUTER_COUNTIES = {fips: name for grp in OUTER_GROUPS.values() for fips, name in grp.items()}
COUNTY_TO_GROUP = {fips: grp for grp, cs in OUTER_GROUPS.items() for fips in cs}

# Major white-collar office hubs (lat, lon), for distance-based splits that
# cut across county lines. Suburban office parks (Bishop Ranch, Pleasanton)
# are left out on purpose: the Tri-Valley is treated as a commuter origin.
OFFICE_HUBS = {
    'San Francisco': (37.7907, -122.3985),     # FiDi / SoMa
    'Oakland': (37.8044, -122.2712),           # downtown
    'Menlo Park / Palo Alto': (37.4500, -122.1500),
    'Mountain View': (37.4040, -122.0500),
    'Cupertino': (37.3349, -122.0090),
    'Santa Clara': (37.3707, -121.9635),
    'San Jose': (37.3337, -121.8907),          # downtown
}

# --- Work-policy eras ---------------------------------------------------------
# Boundaries follow bay_area_rto_timeline_expanded.xlsx: WFH begins March 2020,
# large employers go hybrid from ~April 2022 (Google, then Apple/Meta), 5-day
# mandates arrive from January 2025 (Amazon, then others).

ERAS = [
    # (name, start, end) - end is exclusive
    ('Pre-COVID', datetime(2014, 1, 1), datetime(2020, 3, 1)),
    ('WFH', datetime(2020, 3, 1), datetime(2022, 4, 1)),
    ('Hybrid', datetime(2022, 4, 1), datetime(2025, 1, 1)),
    ('RTO', datetime(2025, 1, 1), datetime(2030, 1, 1)),
]


def era_of(date):
    for name, start, end in ERAS:
        if start <= date < end:
            return name
    return None


# --- Chart styling ------------------------------------------------------------
# Validated categorical palette (fixed order - assign by entity, never cycle).
SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100',
          '#e87ba4', '#008300', '#4a3aa7', '#e34948']
# Diverging poles + neutral midpoint.
DIV_POS = '#2a78d6'
DIV_NEG = '#e34948'
NEUTRAL = '#f0efec'

SURFACE = '#fcfcfb'
TEXT = '#0b0b0b'
TEXT_2 = '#52514e'
GRID = '#e4e3df'

# Light washes for era shading (kept recessive so data marks dominate).
ERA_SHADE = {'Pre-COVID': None, 'WFH': '#eeeeea', 'Hybrid': '#f6f5f1', 'RTO': '#eeeeea'}


def apply_style():
    plt.rcParams.update({
        'figure.facecolor': SURFACE,
        'axes.facecolor': SURFACE,
        'savefig.facecolor': SURFACE,
        'axes.edgecolor': GRID,
        'axes.labelcolor': TEXT_2,
        'axes.titlecolor': TEXT,
        'axes.titlesize': 11,
        'axes.titleweight': 'bold',
        'axes.titlelocation': 'left',
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.grid': True,
        'axes.axisbelow': True,
        'grid.color': GRID,
        'grid.linewidth': 0.6,
        'xtick.color': TEXT_2,
        'ytick.color': TEXT_2,
        'xtick.labelsize': 9,
        'ytick.labelsize': 9,
        'legend.frameon': False,
        'legend.fontsize': 9,
        'lines.linewidth': 1.6,
        'font.size': 10,
        'text.color': TEXT,
    })


def shade_eras(ax, xmin=None, xmax=None, label=True):
    """Shade WFH / Hybrid / RTO spans on a date x-axis and name them at the top."""
    lo, hi = ax.get_xlim()
    import matplotlib.dates as mdates
    for name, start, end in ERAS:
        color = ERA_SHADE[name]
        s, e = mdates.date2num(start), mdates.date2num(end)
        s, e = max(s, lo), min(e, hi)
        if s >= e:
            continue
        if color:
            ax.axvspan(s, e, color=color, zorder=0, lw=0)
        if label:
            ax.text((s + e) / 2, 1.0, name, transform=ax.get_xaxis_transform(),
                    ha='center', va='bottom', fontsize=8, color=TEXT_2)
    ax.set_xlim(lo, hi)


def label_ends(ax, series, fmt, min_gap=0.035):
    """Value labels at the right end of each line, nudged apart so they don't overlap."""
    lo, hi = ax.get_ylim()
    ends = sorted((s.iloc[-1], s.index[-1]) for s in (s.dropna() for s in series) if len(s))
    ys = []
    for v, _ in ends:
        ys.append(max(v, ys[-1] + min_gap * (hi - lo)) if ys else v)
    for (v, x), y in zip(ends, ys):
        ax.annotate(fmt.format(v), (x, y), xytext=(6, 0), textcoords='offset points',
                    va='center', fontsize=8, color=TEXT_2)
