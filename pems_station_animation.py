#!/usr/bin/env python3
"""
Animated map: Bay Area freeway detectors shaded by Tue-Thu morning-peak
traffic (5-10 AM) relative to each detector's own pre-COVID level, year by year
(deeper blue = more traffic).

Uses the cached per-detector data from pems_station_analysis.py (same filters:
measured hours only, detector indexed to its 2016-19 average for the same month).
Key frames are each October in pems_station/, then the latest September after
the last October if there is one (indexed to pre-COVID Septembers). Between key
frames, values are interpolated; a detector appears only in years where it
reported well (or between two such years).

County outlines come from geo/cb_2023_us_county_500k.zip.

Usage:
    python pems_station_animation.py

Outputs:
    pems_station_animation.mp4
    pems_station_animation.gif   (smaller, for slides / chat)
"""

import io
import struct
import zipfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
from matplotlib.colors import LinearSegmentedColormap, Normalize

from bay_area_defs import ERA_SHADE, GRID, SEQ_BLUE, SURFACE, TEXT, TEXT_2, apply_style, era_of
from pems_station_analysis import AM_PEAK, add_index, load_all, window_values

COUNTY_ZIP = 'geo/cb_2023_us_county_500k.zip'
BBOX = (-123.05, 36.95, -121.45, 38.55)        # lon/lat extent of District 4 detectors
HOLD, TWEEN, FPS = 14, 16, 20                  # frames per key frame / transition
INDEX_RANGE = (60, 140)

PLACES = {'San Francisco': (-122.42, 37.77), 'Oakland': (-122.27, 37.80), 'San Jose': (-121.89, 37.34),
          'Dublin': (-121.94, 37.70), 'Livermore': (-121.77, 37.68), 'Walnut Creek': (-122.06, 37.91),
          'Fremont': (-121.99, 37.55), 'Santa Rosa': (-122.71, 38.44), 'Fairfield': (-122.04, 38.25)}


def county_outlines(path=COUNTY_ZIP, bbox=BBOX):
    """Polygon rings from the Census county shapefile that touch bbox (minimal .shp reader)."""
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith('.shp'))
        buf = io.BytesIO(z.read(name)).getvalue()
    rings, pos = [], 100
    while pos < len(buf):
        _, length = struct.unpack('>2i', buf[pos:pos + 8])
        rec = buf[pos + 8:pos + 8 + length * 2]
        pos += 8 + length * 2
        if struct.unpack('<i', rec[:4])[0] != 5:
            continue
        xmin, ymin, xmax, ymax = struct.unpack('<4d', rec[4:36])
        if xmax < bbox[0] or xmin > bbox[2] or ymax < bbox[1] or ymin > bbox[3]:
            continue
        nparts, npts = struct.unpack('<2i', rec[36:44])
        parts = list(struct.unpack(f'<{nparts}i', rec[44:44 + 4 * nparts])) + [npts]
        pts = np.frombuffer(rec[44 + 4 * nparts:44 + 4 * nparts + 16 * npts], dtype='<f8').reshape(-1, 2)
        rings += [pts[a:b] for a, b in zip(parts, parts[1:])]
    return rings


def key_frames(v):
    """Ordered (year, month) key frames: every October, then a later September if present."""
    octs = sorted(y for y, m in set(zip(v.year, v.month)) if m == 10)
    keys = [(y, 10) for y in octs]
    seps = sorted(y for y, m in set(zip(v.year, v.month)) if m == 9 and y > max(octs, default=0))
    if seps:
        keys.append((seps[-1], 9))
    return keys


def build_frames(v, keys):
    wide = v.pivot_table(index='station', columns=['year', 'month'], values='index')
    wide = wide.reindex(columns=pd.MultiIndex.from_tuples(keys))
    wide = wide.dropna(how='all')
    # interpolate across key frames only between years a detector actually reported
    filled = wide.T.reset_index(drop=True).interpolate(limit_area='inside').T
    pos = v.groupby('station')[['lon', 'lat']].first().loc[filled.index]
    frames = []                                     # (key position as float, values)
    for k in range(len(keys)):
        frames += [(k, filled[k].values)] * HOLD
        if k + 1 < len(keys):
            for t in np.linspace(0, 1, TWEEN + 2)[1:-1]:
                a, b = filled[k].values, filled[k + 1].values
                both = ~np.isnan(a) & ~np.isnan(b)
                frames.append((k + t, np.where(both, a + (b - a) * t, np.nan)))
    medians = [np.nanmedian(filled[k].values) for k in range(len(keys))]
    return pos, frames, medians


def main():
    apply_style()
    d = load_all()
    v = add_index(window_values(d, 'Tue-Thu', AM_PEAK))
    v = v[v.lon.between(BBOX[0], BBOX[2]) & v.lat.between(BBOX[1], BBOX[3])]
    keys = key_frames(v)
    pos, frames, medians = build_frames(v, keys)
    labels = [f"{'Oct' if m == 10 else 'Sep'} {y}" for y, m in keys]
    eras = [era_of(pd.Timestamp(y, m, 15)) for y, m in keys]

    cmap = LinearSegmentedColormap.from_list('seq', SEQ_BLUE)
    norm = Normalize(*INDEX_RANGE)

    fig = plt.figure(figsize=(10, 8.6))
    ax = fig.add_axes([0.02, 0.17, 0.96, 0.72])
    for ring in county_outlines():
        ax.plot(ring[:, 0], ring[:, 1], color=GRID, lw=0.7, zorder=0)
    ax.scatter(pos.lon, pos.lat, s=4, color='#ebe9e4', zorder=1)       # network skeleton
    for name, (x, y) in PLACES.items():
        ax.text(x, y + 0.025, name, fontsize=8, color=TEXT_2, ha='center', zorder=4)
    ax.set_xlim(BBOX[0], BBOX[2])
    ax.set_ylim(BBOX[1], BBOX[3])
    ax.set_aspect(1 / np.cos(np.radians(37.75)))
    ax.axis('off')
    sc = ax.scatter([], [], s=14, c=[], cmap=cmap, norm=norm, zorder=3, linewidths=0)
    title = fig.text(0.03, 0.955, '', fontsize=22, fontweight='bold', color=TEXT)
    era_txt = fig.text(0.03, 0.915, '', fontsize=12, color=TEXT_2)
    fig.text(0.97, 0.955, 'Tue–Thu morning freeway traffic (5–10 AM)', fontsize=12, ha='right',
             fontweight='bold', color=TEXT)
    fig.text(0.97, 0.925, "each detector vs. its own pre-COVID level (2016–19 = 100)", fontsize=9.5,
             ha='right', color=TEXT_2)

    cax = fig.add_axes([0.62, 0.86, 0.33, 0.015])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation='horizontal')
    cb.set_ticks([60, 80, 100, 120, 140])
    cb.ax.tick_params(labelsize=8, colors=TEXT_2)
    cb.outline.set_visible(False)

    tax = fig.add_axes([0.08, 0.05, 0.86, 0.1])
    xs = np.arange(len(keys))
    for k, era in enumerate(eras):
        if ERA_SHADE.get(era):
            tax.axvspan(k - 0.5, k + 0.5, color=ERA_SHADE[era], lw=0, zorder=0)
    tax.plot(xs, medians, color=TEXT_2, lw=1.2, zorder=2)
    tax.axhline(100, color=GRID, lw=0.8, zorder=1)
    dot, = tax.plot([], [], 'o', color=TEXT, ms=7, zorder=3)
    tax.set_xticks(xs)
    tax.set_xticklabels([lab.replace('Oct ', '') for lab in labels], fontsize=8)
    tax.set_xlim(-0.5, len(keys) - 0.5)
    tax.set_ylabel('median', fontsize=8)
    tax.tick_params(axis='y', labelsize=7)
    tax.grid(axis='x', visible=False)
    fig.text(0.03, 0.01, 'Measured detector-hours only. Source: Caltrans PeMS District 4 (Clearinghouse station_hour).',
             fontsize=7.5, color=TEXT_2)

    def draw(i):
        kpos, vals = frames[i]
        ok = ~np.isnan(vals)
        sc.set_offsets(np.c_[pos.lon.values[ok], pos.lat.values[ok]])
        sc.set_array(np.clip(vals[ok], *INDEX_RANGE))
        k = int(round(kpos))
        title.set_text(labels[k])
        era_txt.set_text(f'{eras[k]} era · {ok.sum():,} detectors')
        dot.set_data([kpos], [np.interp(kpos, xs, medians)])
        return sc, title, era_txt, dot

    anim = FuncAnimation(fig, draw, frames=len(frames), blit=False)
    anim.save('pems_station_animation.mp4', writer=FFMpegWriter(fps=FPS, bitrate=2400), dpi=120,
              savefig_kwargs={'facecolor': SURFACE})
    # GIF: every other frame at half the rate, so it runs as long as the MP4 but is smaller
    gif = FuncAnimation(fig, draw, frames=range(0, len(frames), 2), blit=False)
    gif.save('pems_station_animation.gif', writer=PillowWriter(fps=FPS // 2), dpi=60,
             savefig_kwargs={'facecolor': SURFACE})
    plt.close(fig)
    print(f'Wrote pems_station_animation.mp4 / .gif: {len(keys)} key frames ({", ".join(labels)})')


if __name__ == '__main__':
    main()
