#!/usr/bin/env python3
"""
Time-lapse of a typical Tue-Thu on Bay Area freeways, hour by hour. Every route
is drawn as a line between neighbouring PeMS detectors, shaded by traffic volume
against that detector's own pre-COVID volume for the same month and hour (deeper
blue = more), and as wide as the number of vehicles per hour. Hybrid and RTO eras
side by side.

Uses the cached per-detector hourly data from pems_station_analysis.py (same
filters: measured hours only, holidays and district outages dropped). A
detector-month counts only if all 24 hours were well observed, so the same
detectors stay on screen all day. Within an era, each detector's values are
averaged over that era's months (Hybrid: Oct 2022-24; RTO: Sep/Oct 2025 and
Sep 2026). Each direction is drawn offset to the right of travel; grey lines are
pre-COVID detectors with no usable data in that era.

Usage:
    python pems_route_timelapse.py               # MP4 + GIF + hourly CSV
    python pems_route_timelapse.py --still 7 17  # PNG stills for 7-8 AM and 5-6 PM only

Outputs:
    pems_route_timelapse.mp4
    pems_route_timelapse.gif           (smaller, for slides / chat)
    pems_route_timelapse_hourly.csv    median detector index by hour and era, same detectors in both eras
    pems_route_timelapse_HHh.png       with --still
"""

import argparse
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize

from bay_area_defs import GRID, SEQ_BLUE, SURFACE, TEXT, TEXT_2, apply_style, era_of
from pems_station_analysis import MIN_BASELINE_YEARS, MIN_GOOD_SHARE, PRE_COVID_LAST_YEAR, load_all
from pems_station_animation import PLACES, county_outlines

PANELS = ['Hybrid', 'RTO']
ERA_COLORS = {'Hybrid': '#a3a19b', 'RTO': TEXT}        # neutral, so they don't read as the map's red/blue
BBOX = (-122.62, 37.20, -121.48, 38.28)       # core Bay Area out to the Altamont and Fairfield
START_HOUR = 3                                 # the day runs 3 AM -> 2 AM
HOLD, TWEEN, FPS = 8, 12, 20                   # frames per hour shown / per transition
INDEX_RANGE = (75, 125)
MIN_BASELINE_FLOW = 50                         # veh/hr; below this the index is noise (overnight)
MAX_GAP_MI = 4.0                               # don't join detectors further apart than this
OFFSET_MI = 0.35                               # each direction drawn this far right of the centreline
FLOW_FULL = 9000                               # veh/hr drawn at full line width
LW_MIN, LW_MAX = 0.4, 3.2
KX = np.cos(np.radians(37.75))                 # lon degrees -> equal-distance x
MI_PER_DEG = 69.0
SKELETON = '#e9e7e2'

LABELS = {**{k: v for k, v in PLACES.items()
             if BBOX[0] < v[0] < BBOX[2] and BBOX[1] < v[1] < BBOX[3]},
          'Altamont Pass': (-121.65, 37.745)}
PERIODS = [(range(0, 5), 'night'), (range(5, 10), 'morning commute'), (range(10, 15), 'midday'),
           (range(15, 19), 'evening commute'), (range(19, 24), 'evening')]


# --- Data ---------------------------------------------------------------------

def era_months(d):
    ym = sorted(set(zip(d.year, d.month)))
    return {era: [(y, m) for y, m in ym if era_of(datetime(y, m, 15)) == era] for era in PANELS}


def detector_hours(d):
    """Per era, detector and hour (Tue-Thu): mean flow, and mean index vs the detector's own
    pre-COVID flow in the same calendar month and hour. Only detector-months well observed in
    all 24 hours count."""
    w = d[d.daytype == 'Tue-Thu'].copy()
    w['ok'] = w.flow.notna() & (w.n_good / w.n_all >= MIN_GOOD_SHARE)
    w = w[w.groupby(['station', 'year', 'month']).ok.transform('sum') == 24]
    pre = w[w.year <= PRE_COVID_LAST_YEAR].groupby(['station', 'month', 'hour']).flow.agg(['mean', 'count'])
    pre = pre[pre['count'] >= MIN_BASELINE_YEARS]['mean'].rename('baseline')
    w = w.join(pre, on=['station', 'month', 'hour'], how='inner')
    w['index'] = (w.flow / w.baseline * 100).where(w.baseline > MIN_BASELINE_FLOW)
    eras = {(y, m): era_of(datetime(y, m, 15)) for y, m in set(zip(w.year, w.month))}
    w['era'] = [eras[ym] for ym in zip(w.year, w.month)]
    pre_stations = set(w.loc[w.year <= PRE_COVID_LAST_YEAR, 'station'])
    w = w[w.era.isin(PANELS)]
    h = w.groupby(['era', 'station', 'hour']).agg(flow=('flow', 'mean'), index=('index', 'mean')).reset_index()
    return h, pre_stations


def station_locations(d):
    """Latest known position, postmile and route of each detector, inside the map."""
    loc = d.dropna(subset=['Latitude', 'Longitude', 'Abs_PM']).sort_values(['year', 'month'])
    loc = loc.groupby('station')[['fwy', 'dir', 'Abs_PM', 'Latitude', 'Longitude']].last()
    loc = loc.rename(columns={'Latitude': 'lat', 'Longitude': 'lon'})
    return loc[loc.lon.between(BBOX[0], BBOX[2]) & loc.lat.between(BBOX[1], BBOX[3])]


def hour_matrix(h, era, stations, col):
    """stations x 24 array in animation order (START_HOUR first)."""
    order = [(START_HOUR + k) % 24 for k in range(24)]
    wide = h[h.era == era].pivot(index='station', columns='hour', values=col)
    return wide.reindex(index=stations, columns=order).values


def route_segments(loc, stations):
    """Segments joining neighbouring detectors along each freeway direction, shifted to the right
    of travel so both directions show. Returns (segments, i, j); i/j index into stations."""
    pos = pd.Series(np.arange(len(stations)), index=stations)
    segs, ii, jj = [], [], []
    for (_, dr), g in loc.loc[stations].groupby(['fwy', 'dir']):
        g = g.sort_values('Abs_PM')
        if len(g) < 2:
            continue
        along = g.lat if dr in 'NS' else g.lon
        with np.errstate(invalid='ignore', divide='ignore'):
            rising = np.corrcoef(g.Abs_PM, along)[0, 1] > 0
        if rising != (dr in 'NE'):
            g = g.iloc[::-1]                       # order by direction of travel
        x, y, pm = g.lon.values * KX, g.lat.values, g.Abs_PM.values
        for k in range(len(g) - 1):
            dx, dy = x[k + 1] - x[k], y[k + 1] - y[k]
            length = np.hypot(dx, dy)
            if length == 0 or length * MI_PER_DEG > MAX_GAP_MI or abs(pm[k + 1] - pm[k]) > MAX_GAP_MI:
                continue
            ox, oy = dy / length * OFFSET_MI / MI_PER_DEG, -dx / length * OFFSET_MI / MI_PER_DEG
            segs.append([((x[k] + ox) / KX, y[k] + oy), ((x[k + 1] + ox) / KX, y[k + 1] + oy)])
            ii.append(pos[g.index[k]])
            jj.append(pos[g.index[k + 1]])
    return np.array(segs).reshape(-1, 2, 2), np.array(ii, dtype=int), np.array(jj, dtype=int)


def at(m, p):
    """Values at animation position p (hours since START_HOUR), linear between hours."""
    lo = int(np.floor(p))
    hi, t = min(lo + 1, m.shape[1] - 1), p - lo
    return m[:, lo] * (1 - t) + m[:, hi] * t


# --- Drawing ------------------------------------------------------------------

def hour_label(k):
    a, b = (START_HOUR + k) % 24, (START_HOUR + k + 1) % 24
    ap = lambda x: 'AM' if x < 12 else 'PM'
    num = lambda x: x % 12 or 12
    return f'{num(a)}–{num(b)} {ap(a)}' if ap(a) == ap(b) else f'{num(a)} {ap(a)}–{num(b)} {ap(b)}'


def period_of(k):
    hr = (START_HOUR + k) % 24
    return next(name for hours, name in PERIODS if hr in hours)


def widths(flow):
    return np.where(np.isnan(flow), 0, LW_MIN + (LW_MAX - LW_MIN) * np.clip(flow / FLOW_FULL, 0, 1))


def draw_map(ax, outlines, skeleton):
    for ring in outlines:
        ax.plot(ring[:, 0], ring[:, 1], color=GRID, lw=0.6, zorder=0)
    ax.add_collection(LineCollection(skeleton, colors=SKELETON, linewidths=1.0, zorder=1))
    for name, (x, y) in LABELS.items():
        ax.text(x, y + 0.02, name, fontsize=8, color=TEXT_2, ha='center', zorder=4)
    ax.set_xlim(BBOX[0], BBOX[2])
    ax.set_ylim(BBOX[1], BBOX[3])
    ax.set_aspect(1 / KX)
    ax.axis('off')


def month_label(months):
    return ', '.join(datetime(y, m, 1).strftime('%b %Y') for y, m in months)


def build(d):
    loc = station_locations(d)
    h, pre_stations = detector_hours(d)
    h = h[h.station.isin(loc.index)]
    months = era_months(d)

    cmap = LinearSegmentedColormap.from_list('seq', SEQ_BLUE)
    cmap.set_bad((0, 0, 0, 0))
    norm = Normalize(*INDEX_RANGE)
    outlines = county_outlines(bbox=BBOX)
    skeleton, _, _ = route_segments(loc, sorted(pre_stations & set(loc.index)))

    fig = plt.figure(figsize=(16, 9))
    fig.text(0.012, 0.955, 'A weekday on Bay Area freeways, hour by hour', fontsize=20, fontweight='bold')
    fig.text(0.012, 0.918, 'Tue–Thu traffic on each stretch vs. the same hour before COVID '
             '(2016–19 = 100)  ·  line width = vehicles per hour', fontsize=11.5, color=TEXT_2)

    panels = {}
    for n, era in enumerate(PANELS):
        stations = sorted(h.loc[h.era == era, 'station'].unique())
        segs, i, j = route_segments(loc, stations)
        orphans = np.setdiff1d(np.arange(len(stations)), np.r_[i, j])
        ax = fig.add_axes([0.005 + 0.37 * n, 0.06, 0.37, 0.80])
        draw_map(ax, outlines, skeleton)
        lc = LineCollection(segs, cmap=cmap, norm=norm, capstyle='round', zorder=2)
        ax.add_collection(lc)
        pts = ax.scatter(loc.loc[stations].lon.values[orphans], loc.loc[stations].lat.values[orphans],
                         c=np.zeros(len(orphans)), cmap=cmap, norm=norm, s=0, linewidths=0, zorder=3)
        ax.set_title(f'{era} era', loc='left', fontsize=14, pad=20)
        ax.text(0, 1.006, f'{month_label(months[era])}  ·  {len(stations):,} detectors',
                transform=ax.transAxes, va='bottom', fontsize=9, color=TEXT_2)
        panels[era] = dict(lc=lc, pts=pts, i=i, j=j, orphans=orphans,
                           idx=hour_matrix(h, era, stations, 'index'), flow=hour_matrix(h, era, stations, 'flow'))

    # right column: clock, legends, hourly profile
    x0 = 0.765
    clock = fig.text(x0, 0.80, '', fontsize=30, fontweight='bold')
    period = fig.text(x0, 0.765, '', fontsize=12, color=TEXT_2)
    fig.text(x0, 0.715, 'Traffic vs. same hour pre-COVID', fontsize=9.5, fontweight='bold')
    cax = fig.add_axes([x0, 0.685, 0.21, 0.016])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation='horizontal')
    cb.set_ticks([75, 90, 100, 110, 125])
    cb.ax.tick_params(labelsize=8, colors=TEXT_2)
    cb.outline.set_visible(False)
    fig.text(x0, 0.635, 'less traffic', fontsize=8, color=TEXT_2)
    fig.text(x0 + 0.21, 0.635, 'more traffic', fontsize=8, color=TEXT_2, ha='right')

    fig.text(x0, 0.585, 'Vehicles per hour', fontsize=9.5, fontweight='bold')
    lax = fig.add_axes([x0, 0.515, 0.21, 0.06])
    for k, v in enumerate([1000, 4000, 8000]):
        lax.plot([k, k + 0.6], [0, 0], color=TEXT_2, lw=widths(np.array([v]))[0], solid_capstyle='round')
        lax.text(k + 0.3, -0.6, f'{v:,}', ha='center', va='top', fontsize=8, color=TEXT_2)
    lax.set_xlim(-0.1, 2.8)
    lax.set_ylim(-1.4, 0.6)
    lax.axis('off')

    both = set(h.loc[h.era == PANELS[0], 'station']) & set(h.loc[h.era == PANELS[1], 'station'])
    prof = (h[h.station.isin(both)].groupby(['era', 'hour'])['index'].agg(['median', 'count'])
            .rename(columns={'median': 'median_index', 'count': 'detectors'}).reset_index())
    tax = fig.add_axes([x0 + 0.025, 0.14, 0.19, 0.30])
    xs = np.arange(24)
    order = [(START_HOUR + k) % 24 for k in xs]
    curves, dots = {}, {}
    for era in PANELS:
        c = prof[prof.era == era].set_index('hour').median_index.reindex(order).values
        curves[era] = c
        tax.plot(xs, c, color=ERA_COLORS[era], lw=1.8, label=era)
        dots[era], = tax.plot([], [], 'o', color=ERA_COLORS[era], ms=6, zorder=4)
    tax.axhline(100, color=TEXT_2, lw=0.8)
    cursor = tax.axvline(0, color=TEXT, lw=0.8, zorder=3)
    tax.set_xticks(xs[::3])
    tax.set_xticklabels([f'{hr % 12 or 12}{"a" if hr < 12 else "p"}' for hr in order[::3]], fontsize=8)
    tax.set_xlim(-0.5, 23.5)
    tax.tick_params(axis='y', labelsize=8)
    tax.grid(axis='x', visible=False)
    tax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=8.5)
    tax.set_title(f'Median detector ({len(both):,} in both eras)', fontsize=9.5)

    fig.text(0.012, 0.03, 'Each detector vs. its own 2016–19 average for the same calendar month and hour; '
             'measured detector-hours only, holidays and district outages dropped. Grey: pre-COVID detectors with '
             'no usable data in that era.', fontsize=8, color=TEXT_2)
    fig.text(0.012, 0.012, 'Directions drawn side by side, each on the right of travel. '
             'Source: Caltrans PeMS District 4 (Clearinghouse station_hour).', fontsize=8, color=TEXT_2)

    def draw(p):
        k = int(round(p))
        for era, pn in panels.items():
            vi, vf = at(pn['idx'], p), at(pn['flow'], p)
            seg_i = (vi[pn['i']] + vi[pn['j']]) / 2
            seg_f = (vf[pn['i']] + vf[pn['j']]) / 2
            pn['lc'].set_array(np.ma.masked_invalid(np.clip(seg_i, *INDEX_RANGE)))
            pn['lc'].set_linewidths(widths(seg_f))
            o = pn['orphans']
            pn['pts'].set_array(np.ma.masked_invalid(np.clip(vi[o], *INDEX_RANGE)))
            pn['pts'].set_sizes(widths(vf[o]) ** 2 * 2)
            dots[era].set_data([p], [np.interp(p, xs, curves[era])])
        cursor.set_xdata([p, p])
        clock.set_text(hour_label(k))
        period.set_text(period_of(k))

    return fig, draw, prof


def positions():
    """Animation position (hours since START_HOUR) for every frame: hold on each hour, then tween."""
    out = []
    for k in range(24):
        out += [float(k)] * HOLD
        if k < 23:
            out += list(np.linspace(k, k + 1, TWEEN + 2)[1:-1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--still', type=int, nargs='+', metavar='HOUR', help='write PNG stills for these hours (0-23) only')
    args = ap.parse_args()

    apply_style()
    fig, draw, prof = build(load_all())
    if args.still:
        for hr in args.still:
            draw(float((hr - START_HOUR) % 24))
            fig.savefig(f'pems_route_timelapse_{hr:02d}h.png', dpi=120)
            print(f'Wrote pems_route_timelapse_{hr:02d}h.png')
        return

    prof.to_csv('pems_route_timelapse_hourly.csv', index=False)
    frames = positions()
    anim = FuncAnimation(fig, draw, frames=frames, blit=False)
    anim.save('pems_route_timelapse.mp4', writer=FFMpegWriter(fps=FPS, bitrate=4000), dpi=120,
              savefig_kwargs={'facecolor': SURFACE})
    # GIF: every other frame at half the rate, so it runs as long as the MP4 but is smaller
    gif = FuncAnimation(fig, draw, frames=frames[::2], blit=False)
    gif.save('pems_route_timelapse.gif', writer=PillowWriter(fps=FPS // 2), dpi=60,
             savefig_kwargs={'facecolor': SURFACE})
    plt.close(fig)
    print(f'Wrote pems_route_timelapse.mp4 / .gif ({len(frames)} frames) and pems_route_timelapse_hourly.csv')


if __name__ == '__main__':
    main()
