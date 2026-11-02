#!/usr/bin/env python3
"""
Zillow home values vs. distance to the Bay Area office hubs. Did the price
gradient flatten during WFH (the "donut effect") and steepen again under RTO?

Source: Zillow Home Value Index (ZHVI), mid-tier (33rd-67th percentile)
single-family + condo, monthly, by ZIP code (zillow/).
ZIP locations: mean of the 2020 census-block coordinates in each ZCTA, from the
LODES geography crosswalk (ca_xwalk.csv.gz). Blocks are smallest where people
live, so for a large rural ZIP the point sits near its populated part.

Distance is straight-line miles to the nearest hub in bay_area_defs.OFFICE_HUBS.
It stands in for commute time: Dublin is ~21 mi, Tracy ~37, Stockton ~53,
Sacramento ~70. ZIPs 120+ mi out are dropped. They are mostly the Lake Tahoe
and Truckee resort towns in Placer and El Dorado counties, a vacation-home
market that boomed in 2020-21 and is not a commute shed.

Zillow values are nominal. Each era's change is shown relative to the median
change across all study ZIPs. That removes region-wide moves (mortgage rates,
inflation) and leaves the gradient. Only ZIPs with a value every month from
2015 on are used, so band medians don't shift as ZIPs enter the data.

Region and era definitions live in bay_area_defs.py.

Usage:
    python zillow_price_gradient_analysis.py

Outputs:
    zillow_zip_gradient.csv          per-ZIP distance, value at each era boundary, era changes
    zillow_band_index_monthly.csv    median value and index (Jan 2020 = 100) by distance band
    zillow_place_index_monthly.csv   named sub-regions vs. the median study ZIP (Jan 2020 = 100)
    zillow_gradient_by_era.png
    zillow_place_index.png
    zillow_distance_bands.png
"""

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from bay_area_defs import (CORE_COUNTIES, OUTER_COUNTIES, OFFICE_HUBS, ERAS, SERIES,
                           SURFACE, TEXT, TEXT_2, apply_style, shade_eras, label_ends)

ZHVI = Path('zillow/Zip_zhvi_mid_tier_sfrcondo_month.csv')
XWALK = Path('ca_xwalk.csv.gz')

START = pd.Period('2015-01', 'M')   # balanced panel: ZIPs with a value every month from here on
BASE = pd.Period('2020-01', 'M')    # index base for the band chart
PRE_SPAN = 36                       # months of pre-COVID change, the "no treatment" comparison panel
MAX_MILES = 120                     # beyond this: Tahoe / Truckee resort ZIPs
EARTH_MI = 3958.8

BANDS = [(0, 10, '0–10 mi'), (10, 25, '10–25 mi'), (25, 45, '25–45 mi'),
         (45, 70, '45–70 mi'), (70, MAX_MILES, f'70–{MAX_MILES} mi')]
BAND_LABELS = [b[2] for b in BANDS]
# Ordinal blue ramp, near -> far (validated: monotone lightness, light end >= 2:1).
BAND_COLORS = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#0d366b']

AREA_COLORS = {'Core county': SERIES[0], 'Outer county': SERIES[1]}

# Places labelled on the gradient chart: (city as Zillow names it, county FIPS).
LABEL_CITIES = [('San Francisco', 75), ('San Jose', 85), ('Dublin', 1),
                ('Tracy', 77), ('Sacramento', 67)]

# Sub-regions for the place chart, in plotting (and colour) order.
PLACES = ['San Francisco', 'Santa Clara County', 'Tri-Valley', 'Tracy / Manteca / Mtn House', '45+ mi exurbs']
TRI_VALLEY = ['Dublin', 'Pleasanton', 'Livermore', 'San Ramon', 'Danville']
I580_SJ = ['Tracy', 'Mountain House', 'Lathrop', 'Manteca']


# --- Data ---------------------------------------------------------------------

def load_zhvi():
    """Monthly ZHVI for ZIPs in the study counties, plus each ZIP's city and county."""
    z = pd.read_csv(ZHVI)
    names = {f'{n} County': f for f, n in {**CORE_COUNTIES, **OUTER_COUNTIES}.items()}
    z = z[(z.State == 'CA') & z.CountyName.isin(names)].copy()
    z['county'] = z.CountyName.map(names)
    z = z.set_index(z.RegionName.astype(int).rename('zip'))

    dates = [c for c in z.columns if c[:2] == '20']
    values = z[dates]
    values.columns = pd.PeriodIndex(dates, freq='M')
    values = values.loc[:, START:]
    values = values[values.notna().all(axis=1)]
    meta = z.loc[values.index, ['City', 'county']].rename(columns={'City': 'city'})
    return values, meta


def zip_locations():
    x = pd.read_csv(XWALK, usecols=['zcta', 'blklatdd', 'blklondd'], dtype={'zcta': str})
    x = x[x.zcta != '99999']
    loc = x.groupby(x.zcta.astype(int).rename('zip'))[['blklatdd', 'blklondd']].mean()
    loc.columns = ['lat', 'lon']
    return loc


def nearest_hub(lat, lon):
    """Straight-line miles from each point to the nearest office hub, and that hub's name."""
    hubs = np.radians(np.array(list(OFFICE_HUBS.values())))
    la, lo = np.radians(lat)[:, None], np.radians(lon)[:, None]
    a = (np.sin((hubs[:, 0] - la) / 2) ** 2
         + np.cos(la) * np.cos(hubs[:, 0]) * np.sin((hubs[:, 1] - lo) / 2) ** 2)
    miles = 2 * EARTH_MI * np.arcsin(np.sqrt(a))
    return miles.min(axis=1), np.array(list(OFFICE_HUBS))[miles.argmin(axis=1)]


def era_windows(last):
    """(from, to) month for each era: the month before it starts to the month before the next.

    Pre-COVID is the PRE_SPAN months before WFH, a baseline for the gradient
    before any work-policy change. RTO runs to the last month of data.
    """
    starts = {name: pd.Period(start, 'M') for name, start, _ in ERAS}
    bounds = [starts['WFH'] - 1, starts['Hybrid'] - 1, starts['RTO'] - 1, last]
    return {'Pre-COVID': (bounds[0] - PRE_SPAN, bounds[0]),
            'WFH': (bounds[0], bounds[1]),
            'Hybrid': (bounds[1], bounds[2]),
            'RTO': (bounds[2], bounds[3])}


def place_of(z):
    """Sub-region of each ZIP for the place chart (None = not shown). Later rules win."""
    place = pd.Series(None, index=z.index, dtype=object)
    place[z.miles >= 45] = '45+ mi exurbs'
    place[z.county == 85] = 'Santa Clara County'
    place[z.county == 75] = 'San Francisco'
    place[z.city.isin(TRI_VALLEY) & z.county.isin([1, 13])] = 'Tri-Valley'
    place[z.city.isin(I580_SJ) & (z.county == 77)] = 'Tracy / Manteca / Mtn House'
    return place


def slope_per_10mi(miles, y):
    return 10 * np.polyfit(miles, y, 1)[0]


def build():
    values, meta = load_zhvi()
    zips = meta.join(zip_locations(), how='inner')
    zips['miles'], zips['nearest_hub'] = nearest_hub(zips.lat.values, zips.lon.values)
    zips = zips[zips.miles < MAX_MILES].copy()
    values = values.loc[zips.index]
    zips['area'] = np.where(zips.county.isin(list(CORE_COUNTIES)), 'Core county', 'Outer county')
    zips['band'] = pd.cut(zips.miles, [b[0] for b in BANDS] + [BANDS[-1][1]],
                          labels=BAND_LABELS, right=False)
    zips['place'] = place_of(zips)

    windows = era_windows(values.columns[-1])
    for p in sorted({p for w in windows.values() for p in w}):
        zips[f'zhvi_{p}'] = values[p].round(0)

    summary = []
    for era, (a, b) in windows.items():
        chg = values[b] / values[a] - 1
        zips[f'{era}_pct'] = 100 * chg
        zips[f'{era}_vs_median_pct'] = 100 * ((1 + chg) / (1 + chg.median()) - 1)
        y = zips[f'{era}_vs_median_pct']
        not_sf = zips.county != 75
        summary.append({
            'era': era, 'from': a, 'to': b, 'median_zip_pct': 100 * chg.median(),
            'slope_pts_per_10mi': slope_per_10mi(zips.miles, y),
            'slope_excl_sf': slope_per_10mi(zips.miles[not_sf], y[not_sf]),
            **{band: y[zips.band == band].median() for band in BAND_LABELS},
        })

    idx = 100 * values.div(values[BASE], axis=0)
    months = values.columns.to_timestamp()
    band_rows = []
    for band in BAND_LABELS:
        m = zips.band == band
        band_rows.append(pd.DataFrame({'month': months, 'band': band, 'zips': int(m.sum()),
                                       'median_value': values[m].median().values,
                                       'index': idx[m].median().values}))
    bands = pd.concat(band_rows, ignore_index=True)
    inner = bands[bands.band == BAND_LABELS[0]].set_index('month').median_value
    bands['pct_of_inner_band'] = 100 * bands.median_value / bands.month.map(inner)

    # Each ZIP's index relative to the median ZIP that month, then the median per place.
    rel = 100 * idx.div(idx.median(), axis=1)
    places = pd.DataFrame({p: rel[zips.place == p].median() for p in PLACES})
    places.index = months
    places.index.name = 'month'
    return zips, bands, places, windows, pd.DataFrame(summary)


# --- Charts -------------------------------------------------------------------

def binned_median(x, y, width=10, min_n=5):
    b = (x // width) * width + width / 2
    g = y.groupby(b).agg(['median', 'size'])
    return g[g['size'] >= min_n]['median']


def chart_gradient(zips, windows, summary):
    fig, axes = plt.subplots(1, 4, figsize=(16, 5.2), sharey=True)
    for ax, (era, (a, b)), row in zip(axes, windows.items(), summary.itertuples()):
        y = zips[f'{era}_vs_median_pct']
        for area, color in AREA_COLORS.items():
            m = zips.area == area
            ax.scatter(zips.miles[m], y[m], s=16, color=color, alpha=0.55,
                       edgecolor=SURFACE, linewidth=0.5, label=area, zorder=2)
        line = binned_median(zips.miles, y)
        ax.plot(line.index, line.values, color=TEXT, lw=2, marker='o', markersize=4,
                label='Median, 10-mile bins', zorder=3)
        ax.axhline(0, color=TEXT_2, lw=0.8, zorder=1)

        for city, county in LABEL_CITIES:
            m = (zips.city == city) & (zips.county == county)
            if m.any():
                ax.annotate(city, (zips.miles[m].median(), y[m].median()), xytext=(0, 9),
                            textcoords='offset points', ha='center', fontsize=7.5, color=TEXT,
                            zorder=4, bbox=dict(boxstyle='round,pad=0.15', fc=SURFACE, ec='none', alpha=0.8))

        ax.set_title(f'{era}: {a.strftime("%b %Y")} → {b.strftime("%b %Y")}', pad=20)
        ax.text(0, 1.015, f'Median ZIP {row.median_zip_pct:+.0f}% · slope {row.slope_pts_per_10mi:+.1f} pts / 10 mi',
                transform=ax.transAxes, fontsize=8, color=TEXT_2)
        ax.set_xlabel('Miles to nearest office hub (straight line)')
    axes[0].set_ylabel('Change vs. the median ZIP (%)')
    axes[0].yaxis.set_major_formatter(mticker.StrMethodFormatter('{x:+.0f}%'))
    axes[0].legend(loc='lower right', fontsize=8)

    fig.suptitle('Distance alone explains little: the WFH shift was mostly SF falling behind, '
                 'and SF is the part rebounding under RTO',
                 x=0.01, ha='left', fontsize=13, fontweight='bold', color=TEXT)
    fig.text(0.01, 0.01, 'Each dot is a ZIP: its home-value change minus the median study ZIP, so region-wide '
             'moves (rates, inflation) cancel. Source: Zillow ZHVI mid-tier, nominal. Hubs: SF, Oakland, Menlo Park/'
             'Palo Alto, Mountain View, Cupertino, Santa Clara, San Jose.', fontsize=8, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig('zillow_gradient_by_era.png', dpi=150)
    plt.close(fig)


def chart_places(places, zips):
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for place, color in zip(PLACES, SERIES):
        n = int((zips.place == place).sum())
        ax.plot(places.index, places[place], color=color, label=f'{place} ({n} ZIPs)')
    label_ends(ax, [places[p] for p in PLACES], '{:.0f}')
    ax.axhline(100, color=TEXT_2, lw=0.8)
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo, hi + (hi - lo) * 0.03)
    shade_eras(ax)
    ax.set_title('Home value relative to the median study ZIP (Jan 2020 = 100)', pad=18)
    ax.set_ylabel('100 = moved with the region')
    ax.legend(loc='lower left')
    fig.text(0.01, 0.01, 'Median across each place\'s ZIPs of (ZIP index ÷ median-ZIP index). Exurbs = ZIPs 45+ mi '
             'from the nearest office hub. Source: Zillow ZHVI mid-tier single-family + condo.',
             fontsize=8, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig('zillow_place_index.png', dpi=150)
    plt.close(fig)


def chart_bands(bands):
    fig, (a, b) = plt.subplots(2, 1, figsize=(11, 8.5), sharex=True)
    for band, color in zip(BAND_LABELS, BAND_COLORS):
        s = bands[bands.band == band].set_index('month')
        a.plot(s.index, s['index'], color=color, label=f'{band} ({s.zips.iloc[0]} ZIPs)')
        if band != BAND_LABELS[0]:
            b.plot(s.index, s.pct_of_inner_band, color=color, label=band)
    by_band = bands.set_index('month').groupby('band', observed=True)
    label_ends(a, [g['index'] for _, g in by_band], '{:.0f}')
    label_ends(b, [g.pct_of_inner_band for band, g in by_band if band != BAND_LABELS[0]], '{:.0f}%')
    a.axhline(100, color=TEXT_2, lw=0.8)
    lo, hi = a.get_xlim()
    a.set_xlim(lo, hi + (hi - lo) * 0.04)
    shade_eras(a)
    shade_eras(b, label=False)

    a.set_title('Median home value by distance from the office hubs (Jan 2020 = 100)', pad=18)
    a.legend(loc='upper left', title='Miles to nearest hub', title_fontsize=8)
    b.set_title('...as a share of the 0–10 mi median (the price discount for distance)', pad=8)
    b.yaxis.set_major_formatter(mticker.StrMethodFormatter('{x:.0f}%'))
    b.legend(loc='upper left')

    fig.text(0.01, 0.01, 'Median across ZIPs in each band (unweighted); same ZIPs every month. '
             'Source: Zillow ZHVI mid-tier single-family + condo, nominal.', fontsize=8, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig('zillow_distance_bands.png', dpi=150)
    plt.close(fig)


def main():
    apply_style()
    zips, bands, places, windows, summary = build()
    zips.drop(columns=['band']).assign(band=zips.band.astype(str)).to_csv(
        'zillow_zip_gradient.csv', index_label='zip', float_format='%.2f')
    bands.to_csv('zillow_band_index_monthly.csv', index=False, float_format='%.2f')
    places.to_csv('zillow_place_index_monthly.csv', float_format='%.2f')
    chart_gradient(zips, windows, summary)
    chart_places(places, zips)
    chart_bands(bands)

    print(f'{len(zips)} ZIPs, data through {zips.filter(like="zhvi_").columns[-1][5:]}')
    print('\nChange vs. median ZIP by distance band (%), and gradient slope:')
    print(summary.drop(columns=['from', 'to']).set_index('era').T.to_string(float_format=lambda v: f'{v:+.1f}'))
    print('\nMedian value as % of the 0–10 mi band:')
    s = bands.pivot(index='month', columns='band', values='pct_of_inner_band')[BAND_LABELS[1:]]
    picks = [w[0].to_timestamp() for w in windows.values()] + [s.index[-1]]
    print(s.loc[picks].to_string(float_format=lambda v: f'{v:.0f}%'))
    print('\nPlaces vs. the median study ZIP (Jan 2020 = 100):')
    print(places.loc[picks].T.to_string(float_format=lambda v: f'{v:.0f}'))


if __name__ == '__main__':
    main()
