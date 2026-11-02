#!/usr/bin/env python3
"""
Bay Area (Caltrans District 4) freeway traffic at detector level, 2016-2026:
did commute traffic out of the Tri-Valley rise when RTO started, and what else
changed about when people drive?

Source: PeMS Clearinghouse District 4 station_hour files in pems_station/
(d04_text_station_hour_YYYY_MM.txt.gz - every detector, hourly) and station
metadata files (d04_text_meta_YYYY_MM_DD.txt) for postmile and lat/lon. Drop
more months into pems_station/ and re-run; they are picked up automatically.
Each monthly file is reduced once to per-detector hourly means and cached in
pems_station/cache/.

Method
  * Only detector-hours that were actually measured (>=95% observed) are used;
    PeMS imputes the rest. Federal holidays and district-wide outage days
    (e.g. Oct 20-31 2025) are dropped.
  * A detector counts in a month only if >=80% of the hours in the window being
    measured were observed.
  * Each detector is indexed to its OWN pre-COVID average for the same calendar
    month (2016-2019 files; needs >=2 of them), so detectors coming and going
    don't distort the series. A screenline's value is the median detector index.
  * The direct RTO test is the matched-detector change from the last hybrid
    year to the first RTO year (Oct 2024 -> Oct 2025, same detectors both years).

Screenlines (AM peak direction out of the outer suburbs; see SCREENLINES):
  I-580 W Altamont -> Livermore, I-580 W Pleasanton / Dublin, I-580 W Dublin
  grade (Dublin -> Castro Valley / Oakland), I-680 S Sunol grade (-> San Jose),
  I-680 N San Ramon / Danville, and I-580 E Livermore as a reverse-commute control.

Usage:
    python pems_station_analysis.py

Outputs:
    pems_station_screenline_index.csv   AM-peak index per screenline and month
    pems_station_rto_step.csv           matched-detector change between consecutive years
    pems_station_district_windows.csv   district-wide index by time window, plus AM peak timing
    pems_station_screenline_index.png   Tue-Thu AM-peak index by year per screenline
    pems_station_hourly_index.png       hour-of-day traffic vs pre-COVID, by era (October)
    pems_station_district_windows.png   district-wide: which hours/days came back, which didn't
"""

import glob
import os
import re
import time
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from bay_area_defs import SERIES, TEXT, TEXT_2, GRID, apply_style, era_of, shade_eras

DATA_DIR = 'pems_station'
CACHE_DIR = os.path.join(DATA_DIR, 'cache')
CACHE_VERSION = 4             # bump when aggregate_file() changes
PRE_COVID_LAST_YEAR = 2019
MIN_BASELINE_YEARS = 2
MIN_PCT_OBS = 95              # a detector-hour counts only if this % observed
MIN_GOOD_SHARE = 0.8          # detector needs this share of good hours in the window

AM_PEAK = range(5, 10)        # 5:00-9:59 AM (Altamont commuters leave early)

# name -> (freeway, direction, Abs_PM from, Abs_PM to, role)
SCREENLINES = {
    'I-580 W  Altamont → Livermore': (580, 'W', 22.0, 29.5, 'Central Valley inflow'),
    'I-580 W  Pleasanton / Dublin': (580, 'W', 30.0, 36.3, 'Valley + Livermore toward I-680'),
    'I-580 W  Dublin grade': (580, 'W', 37.0, 45.0, 'Dublin → Castro Valley / Oakland'),
    'I-680 S  Sunol grade': (680, 'S', 17.0, 29.0, 'Tri-Valley → San Jose'),
    'I-680 N  San Ramon / Danville': (680, 'N', 33.0, 42.6, 'Tri-Valley → Walnut Creek'),
    'I-580 E  Livermore (reverse)': (580, 'E', 28.0, 36.3, 'Control: outbound AM'),
}

# District-wide windows: (label, day type, hours)
WINDOWS = [
    ('Tue–Thu AM peak (5–10)', 'Tue-Thu', AM_PEAK),
    ('Tue–Thu midday (10–3)', 'Tue-Thu', range(10, 15)),
    ('Tue–Thu PM peak (3–7)', 'Tue-Thu', range(15, 19)),
    ('Mon/Fri AM peak (5–10)', 'Mon/Fri', AM_PEAK),
    ('Weekend, all day', 'Weekend', range(24)),
]

COLS = ['ts', 'station', 'district', 'fwy', 'dir', 'type', 'length', 'samples',
        'pct_obs', 'flow', 'occ', 'speed']
HOLIDAYS = set(USFederalHolidayCalendar().holidays('2010-01-01', '2030-12-31').date)


# --- Loading ------------------------------------------------------------------

def hour_files():
    out = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, 'd04_text_station_hour_*.txt.gz'))):
        if time.time() - os.path.getmtime(path) < 60:
            print(f'  skipping {path}: modified in the last minute (download still in progress?)')
            continue
        m = re.search(r'_(\d{4})_(\d{2})\.txt\.gz$', path)
        out.append((int(m.group(1)), int(m.group(2)), path))
    return out


def aggregate_file(path):
    """Per detector, day type and hour: mean measured flow/speed and observed-hour counts."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, os.path.basename(path).replace('.txt.gz', f'.v{CACHE_VERSION}.pkl'))
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
        return pd.read_pickle(cache)
    print(f'  reading {path} (cached after the first run)')
    parts = []
    for chunk in pd.read_csv(path, header=None, usecols=range(len(COLS)), names=COLS, chunksize=1_000_000):
        parts.append(chunk[chunk.type == 'ML'].drop(columns=['district', 'type', 'length', 'samples', 'occ']))
    d = pd.concat(parts, ignore_index=True)
    d['ts'] = pd.to_datetime(d.ts, format='%m/%d/%Y %H:%M:%S')
    d['date'] = d.ts.dt.date
    d['hour'] = d.ts.dt.hour
    dow = d.ts.dt.dayofweek
    d['daytype'] = np.select([dow.between(1, 3), dow.isin([0, 4])], ['Tue-Thu', 'Mon/Fri'], 'Weekend')
    d = d[~d.date.isin(HOLIDAYS)]
    d['good'] = d.pct_obs >= MIN_PCT_OBS
    # A detector's typical flow for this hour and day type this month; exact zeros where it
    # normally carries traffic are a dead feed even when flagged "observed".
    d['dow'] = dow
    typical = d[d.good].groupby(['station', 'dow', 'hour']).flow.median().rename('typical')
    d = d.join(typical, on=['station', 'dow', 'hour'])
    d.loc[(d.flow == 0) & (d.typical > 200), 'good'] = False
    # Drop district-wide outages hour by hour: hours when few detectors report (whole days
    # like Oct 20-31 2025, or a few hours), and hours when they "report" but the typical
    # detector shows under 60% of its usual flow (feed failures, e.g. Oct 15 2025 midday).
    gd = d[d.good & (d.typical > 0)]
    rel = (gd.flow / gd.typical).groupby([gd.date, gd.hour]).median()
    reporting = d.groupby(['date', 'hour']).good.mean()
    bad = (reporting < 0.2) | (rel.reindex(reporting.index) < 0.6)
    down = bad[bad].index
    if len(down):
        days = sorted({dt for dt, _ in down})
        print(f'    dropping {len(down)} outage date-hours on {len(days)} days ({days[0]} .. {days[-1]})')
    d = d[~pd.MultiIndex.from_arrays([d.date, d.hour]).isin(down)]

    keys = ['station', 'daytype', 'hour']
    n_all = d.groupby(keys).size().rename('n_all')
    g = d[d.good].groupby(keys).agg(flow=('flow', 'mean'), speed=('speed', 'mean'), n_good=('flow', 'size'))
    agg = pd.concat([n_all, g], axis=1).reset_index()
    agg['n_good'] = agg.n_good.fillna(0).astype(int)
    attrs = d.groupby('station')[['fwy', 'dir']].first()
    agg = agg.join(attrs, on='station')
    days = d.groupby('daytype').date.nunique()
    agg['days'] = agg.daytype.map(days)
    agg.to_pickle(cache)
    return agg


def meta_files():
    out = []
    for path in glob.glob(os.path.join(DATA_DIR, 'd04_text_meta_*.txt')):
        m = re.search(r'_(\d{4})_(\d{2})_(\d{2})\.txt$', path)
        out.append((datetime(*map(int, m.groups())), path))
    return sorted(out)


def locations(year, month, metas):
    """Detector location for a month: the newest metadata file dated before the month ends,
    with any detector it lacks filled from the other files (nearest date first)."""
    month_end = datetime(year + month // 12, month % 12 + 1, 1)
    ranked = sorted(metas, key=lambda dm: (dm[0] >= month_end, abs((dm[0] - month_end).days)))
    frames = [pd.read_csv(p, sep='\t', usecols=['ID', 'Abs_PM', 'Latitude', 'Longitude', 'Lanes'])
              for _, p in ranked]
    loc = pd.concat(frames).drop_duplicates('ID').rename(columns={'ID': 'station'})
    return loc.set_index('station')


def load_all():
    metas = meta_files()
    if not metas:
        raise SystemExit(f'No d04_text_meta_*.txt files in {DATA_DIR}/')
    frames = []
    for year, month, path in hour_files():
        agg = aggregate_file(path)
        agg = agg.join(locations(year, month, metas), on='station')
        agg['year'], agg['month'] = year, month
        frames.append(agg)
    d = pd.concat(frames, ignore_index=True)
    d['screenline'] = None
    for name, (fwy, dr, lo, hi, _) in SCREENLINES.items():
        d.loc[(d.fwy == fwy) & (d.dir == dr) & d.Abs_PM.between(lo, hi), 'screenline'] = name
    return d


# --- Indices ------------------------------------------------------------------

def window_values(d, daytype, hours):
    """Per detector and month: summed hourly mean flow over the window, where well observed."""
    w = d[(d.daytype == daytype) & d.hour.isin(hours)]
    g = w.groupby(['station', 'year', 'month']).agg(
        flow=('flow', 'sum'), hours=('flow', 'count'), n_good=('n_good', 'sum'), n_all=('n_all', 'sum'),
        screenline=('screenline', 'first'), lat=('Latitude', 'first'), lon=('Longitude', 'first'),
        fwy=('fwy', 'first'), dir=('dir', 'first'))
    ok = (g.hours == len(hours)) & (g.n_good / g.n_all >= MIN_GOOD_SHARE)
    return g[ok].reset_index()


def add_index(v, col='flow'):
    """Index each detector-month to that detector's pre-COVID mean for the same calendar month."""
    pre = v[v.year <= PRE_COVID_LAST_YEAR].groupby(['station', 'month'])[col].agg(['mean', 'count'])
    pre = pre[pre['count'] >= MIN_BASELINE_YEARS]['mean'].rename('baseline')
    v = v.join(pre, on=['station', 'month'], how='inner')
    v['index'] = v[col] / v.baseline * 100
    v['date'] = pd.to_datetime(dict(year=v.year, month=v.month, day=15))
    v['era'] = v.date.map(era_of)
    return v


def screenline_index(v):
    s = v[v.screenline.notna()].groupby(['screenline', 'year', 'month', 'date', 'era'])['index'].agg(
        ['median', 'count']).reset_index().rename(columns={'median': 'index', 'count': 'detectors'})
    return s


def consecutive_steps(v):
    """Matched-detector median % change between consecutive available years of the same month."""
    rows = []
    sl = v[v.screenline.notna()]
    for month, vm in sl.groupby('month'):
        years = sorted(vm.year.unique())
        for y0, y1 in zip(years, years[1:]):
            a = vm[vm.year == y0].set_index('station')
            b = vm[vm.year == y1].set_index('station')
            both = a.index.intersection(b.index)
            for name in SCREENLINES:
                st = [s for s in both if a.at[s, 'screenline'] == name]
                if not st:
                    continue
                chg = (b.loc[st, 'flow'] / a.loc[st, 'flow'] - 1) * 100
                rows.append({'screenline': name, 'month': month, 'from': y0, 'to': y1,
                             'from_era': era_of(datetime(y0, month, 15)), 'to_era': era_of(datetime(y1, month, 15)),
                             'detectors': len(st), 'median_pct_change': chg.median()})
    return pd.DataFrame(rows)


def peak_timing(d):
    """Flow-weighted mean clock time of the Tue-Thu 5-10 AM peak per detector-month (hours)."""
    w = d[(d.daytype == 'Tue-Thu') & d.hour.isin(AM_PEAK) & d.flow.notna()].copy()
    w['fh'] = w.flow * (w.hour + 0.5)
    g = w.groupby(['station', 'year', 'month']).agg(fh=('fh', 'sum'), flow=('flow', 'sum'),
                                                     hours=('flow', 'count'), n_good=('n_good', 'sum'),
                                                     n_all=('n_all', 'sum'))
    g = g[(g.hours == len(AM_PEAK)) & (g.n_good / g.n_all >= MIN_GOOD_SHARE)]
    g['centroid'] = g.fh / g.flow
    g = g.reset_index()
    pre = g[g.year <= PRE_COVID_LAST_YEAR].groupby(['station', 'month']).centroid.agg(['mean', 'count'])
    pre = pre[pre['count'] >= MIN_BASELINE_YEARS]['mean'].rename('base_centroid')
    g = g.join(pre, on=['station', 'month'], how='inner')
    g['shift_min'] = (g.centroid - g.base_centroid) * 60
    return g.groupby(['year', 'month']).shift_min.median().rename('am_peak_shift_min')


def district_windows(d):
    rows = []
    for label, daytype, hours in WINDOWS:
        v = add_index(window_values(d, daytype, hours))
        g = v.groupby(['year', 'month', 'date', 'era'])['index'].agg(['median', 'count']).reset_index()
        g['window'] = label
        rows.append(g.rename(columns={'median': 'index', 'count': 'detectors'}))
    out = pd.concat(rows, ignore_index=True)
    out = out.join(peak_timing(d), on=['year', 'month'])
    return out


def hourly_index(d, month=10):
    """Median detector index by hour of day (Tue-Thu), per era, for one calendar month.
    Uses only detector-months that were well observed in all 24 hours, so every hour is
    measured on the same detectors (otherwise the profile turns into a sawtooth)."""
    w = d[(d.month == month) & (d.daytype == 'Tue-Thu')].copy()
    w['ok'] = w.flow.notna() & (w.n_good / w.n_all >= MIN_GOOD_SHARE)
    full = w.groupby(['station', 'year']).ok.transform('sum') == 24
    w = w[full]
    pre = w[w.year <= PRE_COVID_LAST_YEAR].groupby(['station', 'hour']).flow.agg(['mean', 'count'])
    pre = pre[pre['count'] >= MIN_BASELINE_YEARS]['mean'].rename('baseline')
    w = w.join(pre, on=['station', 'hour'], how='inner')
    w = w[w.baseline > 50]                       # skip near-empty overnight hours
    w['index'] = w.flow / w.baseline * 100
    w['era'] = [era_of(datetime(y, month, 15)) for y in w.year]
    return w


# --- Charts -------------------------------------------------------------------

def plot_years(ax, x, col='index', label=None, **kw):
    """Plot one month's yearly series, breaking the line where years are missing."""
    x = x.sort_values('year')
    seg = (x.year.diff() != 1).cumsum()
    for i, (_, part) in enumerate(x.groupby(seg)):
        ax.plot(part.date, part[col], label=label if i == 0 else None, **kw)


def year_axis(ax, dates, ref=100):
    ax.set_xlim(pd.Timestamp(min(dates).year, 1, 1), pd.Timestamp(max(dates).year, 12, 31))
    shade_eras(ax)
    ax.axhline(ref, color=TEXT_2, lw=0.8, zorder=1)


def chart_screenlines(s, steps):
    names = [n for n in SCREENLINES if n in set(s.screenline)]
    ncol = 2
    nrow = int(np.ceil(len(names) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(11, 3.0 * nrow), sharex=True, sharey=True, squeeze=False)
    month_style = {10: (SERIES[0], 'o', 'October'), 9: (SERIES[1], 's', 'September')}
    for ax, name in zip(axes.flat, names):
        x = s[s.screenline == name]
        for month, (color, marker, label) in month_style.items():
            xm = x[x.month == month]
            if len(xm):
                plot_years(ax, xm, color=color, marker=marker, ms=4, label=label)
        pre = x[x.year <= PRE_COVID_LAST_YEAR]['index']
        if len(pre):
            ax.axhspan(pre.min(), pre.max(), color=SERIES[0], alpha=0.10, lw=0, zorder=0)
        year_axis(ax, s.date)
        ax.set_title(f'{name}\n{SCREENLINES[name][4]}', fontsize=9.5, pad=14)
        st = steps[(steps.screenline == name) & (steps.from_era == 'Hybrid') & (steps.to_era == 'RTO')]
        if len(st):
            r = st.iloc[-1]
            ax.text(0.02, 0.05, f"{r['from']}→{r['to']} same detectors: {r.median_pct_change:+.1f}% (n={r.detectors})",
                    transform=ax.transAxes, fontsize=8, color=TEXT)
    for ax in axes.flat[len(names):]:
        ax.set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel('index, pre-COVID = 100', fontsize=8)
    axes.flat[0].legend(loc='lower right', fontsize=8)
    fig.suptitle('Tue–Thu 5–10 AM traffic at Tri-Valley commute screenlines vs. each detector\'s pre-COVID level',
                 x=0.01, ha='left', fontsize=12, fontweight='bold')
    fig.text(0.01, 0.005, 'Median detector index; each detector vs its own 2016–19 average for the same month. '
             'Blue band = range of the pre-COVID years. Measured hours only. Source: Caltrans PeMS D4.',
             fontsize=7.5, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig('pems_station_screenline_index.png', dpi=150)
    plt.close(fig)


def chart_hourly(h):
    eras = [e for e in ['WFH', 'Hybrid', 'RTO'] if e in set(h.era)]
    colors = {'WFH': SERIES[2], 'Hybrid': SERIES[3], 'RTO': SERIES[1]}
    groups = [('All District 4 detectors', h)] + [
        (name, h[h.screenline == name]) for name in SCREENLINES if name in set(h.screenline)]
    ncol = 2
    nrow = int(np.ceil(len(groups) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(11, 2.8 * nrow), sharex=True, squeeze=False)
    for ax, (title, g) in zip(axes.flat, groups):
        for era in eras:
            ge = g[g.era == era]
            if ge.empty:
                continue
            prof = ge.groupby('hour')['index'].median()
            years = sorted(ge.year.unique())
            ax.plot(prof.index, prof.values, color=colors[era], marker='o', ms=2.5,
                    label=f"{era} ({years[0]}{'–' + str(years[-1]) if len(years) > 1 else ''})")
        ax.axhline(100, color=TEXT_2, lw=0.8)
        ax.axvspan(AM_PEAK.start - 0.5, AM_PEAK.stop - 0.5, color=GRID, alpha=0.5, lw=0, zorder=0)
        ax.set_title(title, fontsize=9.5)
        ax.set_xticks(range(0, 24, 3))
        ax.set_xticklabels([f'{hr % 12 or 12}{"a" if hr < 12 else "p"}' for hr in range(0, 24, 3)])
    for ax in axes.flat[len(groups):]:
        ax.set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel('pre-COVID hour = 100', fontsize=8)
    axes.flat[0].legend(fontsize=8, loc='lower right')
    fig.suptitle('Tue–Thu traffic by hour of day vs. pre-COVID, October', x=0.01, ha='left',
                 fontsize=12, fontweight='bold')
    fig.text(0.01, 0.005, 'Median detector index per hour (each detector vs its own 2016–19 October average). '
             'Shaded = 5–10 AM. Source: Caltrans PeMS D4.', fontsize=7.5, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.015, 1, 0.97))
    fig.savefig('pems_station_hourly_index.png', dpi=150)
    plt.close(fig)


def chart_district(w):
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True, gridspec_kw={'height_ratios': [2.2, 1]})
    for (label, _, _), color in zip(WINDOWS, SERIES):
        for month, ls in [(10, '-'), (9, ':')]:
            x = w[(w.window == label) & (w.month == month)]
            if len(x):
                plot_years(ax, x, color=color, ls=ls, marker='o', ms=3,
                           label=label if month == 10 else None)
    year_axis(ax, w.date)
    ax.set_ylabel('median detector index, pre-COVID = 100')
    ax.legend(fontsize=8, loc='lower left', ncol=2)
    ax.set_title('District 4 freeways: which parts of the week came back', pad=14)

    t = w.drop_duplicates(['year', 'month'])
    for month, ls in [(10, '-'), (9, ':')]:
        x = t[t.month == month]
        if len(x):
            plot_years(ax2, x, col='am_peak_shift_min', color=TEXT, ls=ls, marker='o', ms=3,
                       label='October' if month == 10 else 'September')
    year_axis(ax2, w.date, ref=0)
    ax2.set_ylabel('minutes vs pre-COVID')
    ax2.set_title('Timing of the Tue–Thu morning peak (+ = later)', fontsize=10, pad=14)
    ax2.legend(fontsize=8, loc='lower left')
    fig.text(0.01, 0.005, 'Solid = October, dotted = September. Each detector vs its own 2016–19 average for the '
             'same month; measured hours only. Source: Caltrans PeMS D4.', fontsize=7.5, color=TEXT_2)
    fig.tight_layout(rect=(0, 0.015, 1, 1))
    fig.savefig('pems_station_district_windows.png', dpi=150)
    plt.close(fig)


def main():
    apply_style()
    d = load_all()
    print('Months loaded:', ', '.join(f'{y}-{m:02d}' for y, m in sorted(set(zip(d.year, d.month)))))

    am = add_index(window_values(d, 'Tue-Thu', AM_PEAK))
    s = screenline_index(am)
    steps = consecutive_steps(am)
    w = district_windows(d)
    h = hourly_index(d)

    s.round(2).to_csv('pems_station_screenline_index.csv', index=False)
    steps.round(2).to_csv('pems_station_rto_step.csv', index=False)
    w.round(2).to_csv('pems_station_district_windows.csv', index=False)
    chart_screenlines(s, steps)
    chart_hourly(h)
    chart_district(w)

    pd.set_option('display.width', 200)
    print('\nTue-Thu AM-peak index by screenline (pre-COVID = 100):')
    print(s.pivot_table(index=['month', 'year'], columns='screenline', values='index').round(1).to_string())
    print('\nMatched-detector change, hybrid -> RTO:')
    print(steps[(steps.from_era == 'Hybrid') & (steps.to_era == 'RTO')].round(1).to_string(index=False))
    print('\nDistrict-wide index by window:')
    print(w.pivot_table(index=['month', 'year'], columns='window', values='index').round(1).to_string())
    print(w.drop_duplicates(['year', 'month'])[['year', 'month', 'am_peak_shift_min']].round(1).to_string(index=False))


if __name__ == '__main__':
    main()
