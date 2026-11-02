#!/usr/bin/env python3
"""
American Community Survey (ACS) 1-year commuting data for the core Bay Area,
the outer suburbs, and the Tri-Valley / I-580 cities. Did 2025, the first RTO
year, put outer-suburb residents back on long commutes?

Source: Census Bureau ACS 1-year estimates from api.census.gov. Data requests
need a free API key (https://api.census.gov/data/key_signup.html) set as
CENSUS_API_KEY in .env. Results are cached to acs/ on the first run, so the
key is only needed again after you delete a cache file.
  B08301  means of transportation to work      -> worked from home
  B08303  travel time to work (non-WFH)         -> 60+ minute commutes
  B08007  place of work, state and county       -> worked outside county of residence
  B08302  time leaving home to go to work       -> left before 6:00 AM
  B08013  aggregate travel time                 -> mean commute minutes
1-year estimates exist only for areas with 65,000+ people. There is no standard
2020 release (COVID disrupted collection), so the years are 2019 and 2021-2025.

"Worked from home" means the way the person got to work most days in the week
before the survey. A worker in the office 3 days a week counts as a commuter.
So the ACS sees shifts between mostly-remote and mostly-in-office, not a move
from 3 days to 5.

Every share is per 100 resident workers (people who live in the area), so a
fall in WFH and a rise in long commutes are measured on the same base. People
who work from home count as working in their county of residence.

B08301 (means of transportation) is often suppressed for mid-size areas by the
Bureau's data-quality filter, because rare modes such as ferry and taxi make
too many of its cells unreliable. So WFH = all workers (B08007) minus commuters
(B08303, whose universe is workers who did not work from home). Where B08301
is published, the script checks that the two agree and uses B08301's MOE.

Margins of error are the ACS 90% MOEs, combined with the Census Bureau's
approximation formulas (root-sum-of-squares for sums, the proportion formula for
shares). A year-to-year change counts as real when it is larger than its
combined MOE.

Region and era definitions live in bay_area_defs.py.

Usage:
    python acs_commute_analysis.py

Outputs:
    acs_commute_by_area.csv     estimates, MOEs and shares by county, place, group and year
    acs_rto_step.csv            changes with MOEs (2023->24, 2024->25, 2021->25, 2019->25)
    acs_commute_trends.png      county groups, 2019-2025
    acs_place_trends.png        Tri-Valley / I-580 cities vs SF and San Jose
    acs_rto_step.png            hybrid-year vs RTO-year change, with 90% MOEs
    acs_long_commuter_index.png number of 60+ min commuters as % of 2019, with 90% MOEs
"""

import json
import os
import urllib.request
from functools import lru_cache
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from dotenv import load_dotenv

from bay_area_defs import (CORE_COUNTIES, OUTER_COUNTIES, OUTER_GROUPS, SERIES, ERA_SHADE,
                           SURFACE, TEXT, TEXT_2, GRID, apply_style, label_ends)

DATA_DIR = Path('acs')
API = 'https://api.census.gov/data/{year}/acs/acs1'
YEARS = [2019, 2021, 2022, 2023, 2024, 2025]
# Era of each ACS year. Responses are spread across the calendar year, and 2022
# straddles the start of hybrid (April 2022).
YEAR_ERA = {2019: 'Pre-COVID', 2021: 'WFH', 2022: 'WFH/Hybrid', 2023: 'Hybrid', 2024: 'Hybrid', 2025: 'RTO'}
# Hybrid year, RTO year, remote peak -> now (2021 is the first post-2019 release), pre-COVID -> now.
STEPS = [(2023, 2024), (2024, 2025), (2021, 2025), (2019, 2025)]

VARS = {
    'workers': 'B08007_001',
    'wfh_published': 'B08301_021',
    'commuters': 'B08303_001',
    'tt_60_89': 'B08303_012',
    'tt_90_plus': 'B08303_013',
    'out_county': 'B08007_004',
    'out_state': 'B08007_005',
    'agg_minutes': 'B08013_001',
    'leave_0000_0459': 'B08302_002',
    'leave_0500_0529': 'B08302_003',
    'leave_0530_0559': 'B08302_004',
}
# Expected label fragments, checked against the API's variable metadata on
# download, so a renumbered table fails loudly instead of shifting columns.
LABELS = {
    'B08007_001': 'Total', 'B08303_001': 'Total',
    'B08301_021': 'Worked from home', 'B08303_012': '60 to 89 minutes',
    'B08303_013': '90 or more minutes', 'B08007_004': 'Worked outside county of residence',
    'B08007_005': 'Worked outside state of residence', 'B08302_002': '12:00 a.m. to 4:59 a.m.',
    'B08302_003': '5:00 a.m. to 5:29 a.m.', 'B08302_004': '5:30 a.m. to 5:59 a.m.',
    'B08013_001': 'Aggregate travel time',
}
CONTROLLED = -555555555   # MOE code: estimate is controlled to a total, so its MOE is 0

PLACES = {f'{name} city, California': name for name in
          ['San Francisco', 'San Jose', 'Oakland', 'Dublin', 'Pleasanton', 'Livermore',
           'San Ramon', 'Tracy', 'Manteca', 'Stockton']}
TRI_VALLEY = ['Dublin', 'Pleasanton', 'Livermore', 'San Ramon']

COUNTY_GROUPS = {'Core counties': list(CORE_COUNTIES.values()),
                 **{g: list(cs.values()) for g, cs in OUTER_GROUPS.items()}}
PLACE_GROUPS = {'San Francisco': ['San Francisco'], 'San Jose': ['San Jose'], 'Tri-Valley': TRI_VALLEY,
                'Tracy': ['Tracy'], 'Manteca': ['Manteca'], 'Stockton': ['Stockton'],
                # Dublin has no 2019 estimate, so this is the Tri-Valley's pre-COVID comparison.
                'Tri-Valley excl. Dublin': [c for c in TRI_VALLEY if c != 'Dublin']}
CHART_PLACES = ['San Francisco', 'San Jose', 'Tri-Valley', 'Tracy', 'Manteca', 'Stockton']
# Areas on the 2019-indexed count chart: they need a 2019 value, so the
# Tri-Valley appears without Dublin and the Central Coast is left out (San Benito).
COUNT_PANELS = {
    'Counties': ['Core counties', 'North Bay / Solano', 'Sacramento region', 'Northern San Joaquin Valley'],
    'Cities': ['San Francisco', 'San Jose', 'Tri-Valley excl. Dublin', 'Tracy', 'Manteca', 'Stockton'],
}
# Colour follows the area across charts (same slots as the trend charts).
AREA_COLORS = {**{a: SERIES[i] for i, a in enumerate(COUNTY_GROUPS)},
               **{a: SERIES[i] for i, a in enumerate(CHART_PLACES)},
               'Tri-Valley excl. Dublin': SERIES[CHART_PLACES.index('Tri-Valley')]}

# Share columns: numerator (all per 100 resident workers) and chart label.
METRICS = {
    'wfh_pct': ('wfh', 'Worked from home'),
    'long_pct': ('long', 'Commute 60+ minutes'),
    'out_county_pct': ('out_of_county', 'Work outside home county'),
    'early_pct': ('early', 'Leave home before 6 AM'),
}


# --- Data ---------------------------------------------------------------------

def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        body = r.read().decode()
    if body.lstrip().startswith('<'):   # the API answers key problems with an HTML page
        title = body.split('<title>')[1].split('</title>')[0] if '<title>' in body else 'HTML page'
        raise RuntimeError(f'Census API returned "{title}" instead of data. Check CENSUS_API_KEY in .env.')
    return json.loads(body)


@lru_cache(maxsize=None)
def check_labels(year):
    for var, fragment in LABELS.items():
        label = get_json(f'{API.format(year=year)}/variables/{var}E.json')['label']
        if fragment not in label:
            raise ValueError(f'{year} {var}E is "{label}", expected "{fragment}"')


def fetch(year, geo):
    """One year of California county or place estimates + MOEs, cached as CSV."""
    path = DATA_DIR / f'acs1_{year}_{geo}.csv'
    cols = ['NAME'] + [f'{v}{s}' for v in VARS.values() for s in 'EM']
    if path.exists() and set(cols) <= set(pd.read_csv(path, nrows=0).columns):
        return pd.read_csv(path)

    load_dotenv()
    key = os.environ.get('CENSUS_API_KEY')
    if not key:
        raise SystemExit('Set CENSUS_API_KEY in .env (free key: https://api.census.gov/data/key_signup.html)')
    check_labels(year)
    rows = get_json(f'{API.format(year=year)}?get={",".join(cols)}&for={geo}:*&in=state:06&key={key}')
    DATA_DIR.mkdir(exist_ok=True)
    pd.DataFrame(rows[1:], columns=rows[0]).to_csv(path, index=False)
    print(f'fetched {path}')
    return pd.read_csv(path)


def load():
    study = list(CORE_COUNTIES.values()) + list(OUTER_COUNTIES.values())
    frames = []
    for year in YEARS:
        for geo in ['county', 'place']:
            df = fetch(year, geo)
            if geo == 'county':
                df = df.assign(area=df.NAME.str.replace(' County, California', '', regex=False))
                df = df[df.area.isin(study)]
            else:
                df = df[df.NAME.isin(PLACES)].assign(area=lambda d: d.NAME.map(PLACES))
            t = pd.DataFrame({'year': year, 'kind': geo, 'area': df.area.values})
            for name, var in VARS.items():
                e = pd.to_numeric(df[f'{var}E'], errors='coerce').values
                m = pd.to_numeric(df[f'{var}M'], errors='coerce').values
                t[name] = np.where(e < 0, np.nan, e)
                t[f'{name}_moe'] = np.where(m == CONTROLLED, 0, np.where(m < 0, np.nan, m))
            frames.append(t)
    return pd.concat(frames, ignore_index=True)


def add_groups(areas):
    """Sum member areas into groups (MOE of a sum = root-sum-of-squares).

    Members are the areas with an estimate in every year from 2021 on, which
    fixes the composition for the hybrid/RTO comparison. A year where a member
    is missing is left blank for that group (e.g. 2019 for the Tri-Valley:
    Dublin was under 65,000 people then). Dropped members and blank years are
    printed.
    """
    rows = []
    for kind, groups in [('county', COUNTY_GROUPS), ('place', PLACE_GROUPS)]:
        sub = areas[(areas.kind == kind) & areas.workers.notna()]
        for grp, members in groups.items():
            present = {y: set(sub[sub.year == y].area) for y in YEARS}
            keep = [m for m in members if all(m in present[y] for y in YEARS if y >= 2021)]
            if missing := sorted(set(members) - set(keep)):
                print(f'{grp}: left out {", ".join(missing)} (no 1-year estimate in some years)')
            for year in YEARS:
                if absent := [m for m in keep if m not in present[year]]:
                    print(f'{grp}: no {year} value (missing {", ".join(absent)})')
                    continue
                d = sub[(sub.year == year) & sub.area.isin(keep)]
                r = {'year': year, 'kind': f'{kind} group', 'area': grp, 'members': ', '.join(keep)}
                for name in VARS:
                    r[name] = d[name].sum(min_count=len(d))
                    r[f'{name}_moe'] = np.sqrt((d[f'{name}_moe'] ** 2).sum(min_count=len(d)))
                rows.append(r)
    return pd.concat([areas, pd.DataFrame(rows)], ignore_index=True)


def combine(df, name, parts):
    df[name] = df[parts].sum(axis=1, min_count=len(parts))
    df[f'{name}_moe'] = np.sqrt((df[[f'{p}_moe' for p in parts]] ** 2).sum(axis=1))


def share(df, num, den):
    """Share (%) and its 90% MOE, where num is a subset of den (Census proportion formula)."""
    p = df[num] / df[den]
    rad = df[f'{num}_moe'] ** 2 - p ** 2 * df[f'{den}_moe'] ** 2
    # A negative radicand means the proportion formula doesn't apply; the Bureau
    # says to fall back to the ratio formula.
    rad = rad.where(rad >= 0, df[f'{num}_moe'] ** 2 + p ** 2 * df[f'{den}_moe'] ** 2)
    return 100 * p, 100 * np.sqrt(rad) / df[den]


def derive(df):
    df['wfh'] = df.workers - df.commuters
    df['wfh_moe'] = df.wfh_published_moe.where(df.wfh_published.notna(),
                                                np.hypot(df.workers_moe, df.commuters_moe))
    gap = (df.wfh - df.wfh_published).abs().max()
    print(f'WFH check: workers - commuters vs published B08301_021, largest gap {gap:,.0f} workers')
    combine(df, 'long', ['tt_60_89', 'tt_90_plus'])
    combine(df, 'out_of_county', ['out_county', 'out_state'])
    combine(df, 'early', ['leave_0000_0459', 'leave_0500_0529', 'leave_0530_0559'])
    for col, (num, _) in METRICS.items():
        df[col], df[f'{col}_moe'] = share(df, num, 'workers')
    # WFH share = 100 - commuter share. The commuter share's proportion-formula
    # MOE is much tighter than one built from the MOE of (workers - commuters),
    # which treats two highly correlated totals as independent.
    commute_pct, commute_moe = share(df, 'commuters', 'workers')
    df['wfh_pct'], df['wfh_pct_moe'] = 100 - commute_pct, commute_moe
    # Mean one-way commute of people who commute (ratio formula).
    r = df.agg_minutes / df.commuters
    df['mean_minutes'] = r
    df['mean_minutes_moe'] = np.sqrt(df.agg_minutes_moe ** 2 + r ** 2 * df.commuters_moe ** 2) / df.commuters
    return df


def index_to_2019(df, col='long'):
    """A count as an index (2019 = 100) with its 90% MOE (ratio formula; the
    base year is exact by definition). Blank where an area has no 2019 value."""
    base = df[df.year == 2019].set_index(['kind', 'area'])[[col, f'{col}_moe']]
    b = df.join(base, on=['kind', 'area'], rsuffix='_2019')
    r = b[col] / b[f'{col}_2019']
    moe = np.sqrt(b[f'{col}_moe'] ** 2 + r ** 2 * b[f'{col}_moe_2019'] ** 2) / b[f'{col}_2019']
    df[f'{col}_index_2019'] = 100 * r
    df[f'{col}_index_2019_moe'] = (100 * moe).where(df.year != 2019, 0)
    return df


def steps(df):
    """Change between pairs of years for every area, with the MOE of the change."""
    rows = []
    for (kind, area), d in df.groupby(['kind', 'area']):
        d = d.set_index('year')
        for a, b in STEPS:
            if a not in d.index or b not in d.index:
                continue
            r = {'kind': kind, 'area': area, 'step': f'{a}→{b}'}
            for m in list(METRICS) + ['mean_minutes']:
                r[m] = d.at[b, m] - d.at[a, m]
                r[f'{m}_moe'] = np.hypot(d.at[a, f'{m}_moe'], d.at[b, f'{m}_moe'])
                r[f'{m}_significant'] = abs(r[m]) > r[f'{m}_moe']
            rows.append(r)
    return pd.DataFrame(rows)


# --- Charts -------------------------------------------------------------------

def plot_years(ax, s, color, label, dx=0):
    """2019, then 2021-2025 as a line. There's no 2020 release, so 2019 isn't joined to 2021.
    dx nudges the series sideways so overlapping error bars stay readable."""
    s = s.dropna()
    ax.plot(s.index[s.index == 2019] + dx, s[s.index == 2019], color=color, marker='o', markersize=5, lw=0)
    later = s[s.index > 2019]
    ax.plot(later.index + dx, later.values, color=color, marker='o', markersize=5, label=label)


def chart_trends(df, areas, path, title, footnote, stand_in_2019=None):
    """2x2 panels of METRICS over time. stand_in_2019 maps an area with no 2019
    value to a similar area whose 2019 value is drawn as an open marker."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), sharex=True)
    for ax, (col, (_, label)) in zip(axes.flat, METRICS.items()):
        series = []
        for area, color in zip(areas, SERIES):
            s = df[df.area == area].set_index('year')[col]
            plot_years(ax, s, color, area)
            series.append(s)
            if stand_in := (stand_in_2019 or {}).get(area):
                ref = df[(df.area == stand_in) & (df.year == 2019)][col]
                ax.scatter([2019] * len(ref), ref, s=36, facecolor=SURFACE, edgecolor=color, linewidth=1.5, zorder=3)
        ax.axvspan(2024.5, 2025.5, color=ERA_SHADE['RTO'], zorder=0, lw=0)
        ax.set_xlim(2018.5, 2025.9)
        label_ends(ax, series, '{:.1f}')
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:g}'))
        ax.set_title(f'{label}, per 100 resident workers', pad=6)
        ax.set_xticks(YEARS, [f'{y}\n{YEAR_ERA[y]}' for y in YEARS])
        ax.tick_params(axis='x', labelbottom=True)
    axes[0, 0].legend(loc='best')
    fig.suptitle(title, x=0.01, ha='left', fontsize=13, fontweight='bold', color=TEXT)
    fig.text(0.01, 0.01, footnote, fontsize=8, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def chart_counts(df, title):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), sharey=True)
    for ax, (panel, areas) in zip(axes, COUNT_PANELS.items()):
        series = []
        for area, dx in zip(areas, np.linspace(-0.12, 0.12, len(areas))):
            d = df[df.kind.str.endswith('group') & (df.area == area)].set_index('year')
            later = d[d.index > 2019]     # 2019 is 100 by definition: the reference line
            color = AREA_COLORS[area]
            plot_years(ax, later.long_index_2019, color, area, dx)
            ax.errorbar(later.index + dx, later.long_index_2019, yerr=later.long_index_2019_moe,
                        fmt='none', ecolor=color, elinewidth=1, alpha=0.5)
            series.append(later.long_index_2019.set_axis(later.index + dx))
        ax.axhline(100, color=TEXT_2, lw=0.8)
        ax.text(2018.6, 101.5, '2019 level (100%)', fontsize=8, color=TEXT_2, ha='left')
        ax.axvspan(2024.5, 2025.5, color=ERA_SHADE['RTO'], zorder=0, lw=0)
        ax.set_xlim(2018.5, 2026.0)
        ax.yaxis.set_major_formatter(mticker.StrMethodFormatter('{x:.0f}%'))
        label_ends(ax, series, '{:.0f}%')
        ax.set_xticks(YEARS, [f'{y}\n{YEAR_ERA[y]}' for y in YEARS])
        ax.set_title(panel, pad=6)
        ax.legend(loc='lower right', fontsize=8, ncol=1 if len(areas) <= 4 else 2)
    axes[0].set_ylabel('Residents commuting 60+ min, % of 2019 count')
    fig.suptitle(title, x=0.01, ha='left', fontsize=13, fontweight='bold', color=TEXT)
    fig.text(0.01, 0.01, 'Each area\'s count of 60+ min commuters vs. its own 2019 count. Whiskers: 90% margin of error. '
             'No 2020 1-year release. Source: Census ACS 1-year (B08303).\nTri-Valley = Livermore, Pleasanton, '
             'San Ramon (Dublin has no 2019 estimate); Central Coast omitted (no 2019 for San Benito).',
             fontsize=8, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.savefig('acs_long_commuter_index.png', dpi=150)
    plt.close(fig)


def chart_step(st, title):
    st = st[st.kind.str.endswith('group')]              # SF / San Jose are also single-city groups
    rows = list(COUNTY_GROUPS) + CHART_PLACES           # top to bottom
    y = np.arange(len(rows))[::-1].astype(float)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.8), sharey=True)
    panels = [('wfh_pct', 'Worked from home', '← RTO predicts a fall'),
              ('long_pct', 'Commute 60+ minutes', 'RTO predicts a rise in outer areas →')]
    for ax, (col, label, expect) in zip(axes, panels):
        for step, color, dy in [('2023→2024', TEXT_2, 0.17), ('2024→2025', SERIES[0], -0.17)]:
            d = st[st.step == step].set_index('area').reindex(rows)
            sig = d[f'{col}_significant'].astype('boolean').fillna(False).to_numpy(dtype=bool)
            ax.errorbar(d[col], y + dy, xerr=d[f'{col}_moe'], fmt='none', ecolor=color, elinewidth=1.2)
            ax.scatter(d[col][sig], (y + dy)[sig], s=40, color=color, edgecolor=SURFACE, linewidth=1,
                       zorder=3, label=f'{step}, beyond MOE')
            ax.scatter(d[col][~sig], (y + dy)[~sig], s=40, facecolor=SURFACE, edgecolor=color, linewidth=1.5,
                       zorder=3, label=f'{step}, within MOE')
        ax.axvline(0, color=TEXT_2, lw=0.8)
        ax.axhline(len(CHART_PLACES) - 0.5, color=GRID, lw=1.2)
        ax.grid(axis='y', visible=False)
        ax.set_title(label, pad=6)
        ax.set_xlabel(f'Change, points per 100 resident workers\n{expect}')
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:+g}' if v else '0'))
    axes[0].set_yticks(y, rows)
    axes[0].set_ylim(-0.6, len(rows) - 0.4)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower right', ncol=4, fontsize=8, bbox_to_anchor=(1, 0.035))
    fig.suptitle(title, x=0.01, ha='left', fontsize=13, fontweight='bold', color=TEXT)
    fig.text(0.01, 0.01, 'Whiskers: 90% margin of error of the change. Counties above the line, cities below. '
             f'Tri-Valley = {", ".join(TRI_VALLEY)}. Source: Census ACS 1-year.', fontsize=8, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    fig.savefig('acs_rto_step.png', dpi=150)
    plt.close(fig)


def main():
    apply_style()
    df = index_to_2019(derive(add_groups(load())))
    df = df.sort_values(['kind', 'area', 'year'])
    df.to_csv('acs_commute_by_area.csv', index=False, float_format='%.2f')
    st = steps(df)
    st.to_csv('acs_rto_step.csv', index=False, float_format='%.2f')

    groups = df[df.kind == 'county group']
    places = df[df.kind == 'place group']
    chart_trends(groups, list(COUNTY_GROUPS), 'acs_commute_trends.png',
                 'Residents drifted back to commuting through the hybrid years; 2025 added no extra step',
                 'Groups are sums of counties with a 1-year estimate 2021-2025 (Central Coast has no 2019: San Benito). '
                 'No 2020 1-year release. Shaded: first RTO year. Source: Census ACS 1-year.')
    chart_trends(places, CHART_PLACES, 'acs_place_trends.png',
                 'Tri-Valley long commutes were back to pre-COVID levels by 2024, before the RTO year',
                 f'Tri-Valley = {", ".join(TRI_VALLEY)}. Open 2019 marker: Tri-Valley without Dublin (under 65,000 '
                 'people in 2019). City MOEs are wide (Tracy, Manteca ±5-7 pts); see acs_rto_step.png.',
                 stand_in_2019={'Tri-Valley': 'Tri-Valley excl. Dublin'})
    chart_step(st, 'The RTO year moved commuting less than the hybrid year before it')
    chart_counts(df, 'Long commutes rebounded from the remote low, but almost nowhere above 2019')

    for col, (_, label) in METRICS.items():
        print(f'\n{label}, per 100 resident workers:')
        g = df[df.kind.str.endswith('group')]
        print(g.pivot(index='area', columns='year', values=col)
              .reindex(list(COUNTY_GROUPS) + list(PLACE_GROUPS)).to_string(float_format=lambda v: f'{v:.1f}'))
    print('\nResidents commuting 60+ min, % of 2019 count (± 90% MOE, in points):')
    g = df[df.kind.str.endswith('group') & df.area.isin(sum(COUNT_PANELS.values(), []))]
    cells = g.assign(cell=[f'{v:.0f} ±{e:.0f}' for v, e in zip(g.long_index_2019, g.long_index_2019_moe)])
    print(cells.pivot(index='area', columns='year', values='cell')
          .reindex(sum(COUNT_PANELS.values(), [])).to_string())
    print('\nYear-to-year change (points), * = larger than its 90% MOE:')
    s = st[st.kind.str.endswith('group')].copy()
    for m in ['wfh_pct', 'long_pct', 'out_county_pct', 'early_pct']:
        s[m] = [f'{v:+.1f}{"*" if sig else " "} ±{e:.1f}' for v, sig, e in zip(s[m], s[f'{m}_significant'], s[f'{m}_moe'])]
    print(s.set_index(['area', 'step'])[['wfh_pct', 'long_pct', 'out_county_pct', 'early_pct']]
          .reindex(list(COUNTY_GROUPS) + list(PLACE_GROUPS), level=0).to_string())


if __name__ == '__main__':
    main()
