# Traffic findings: did RTO bring Tri-Valley commuters back onto the freeway?

*Written 2026-11-01. Source: Caltrans PeMS District 4 detector data (Clearinghouse `station_hour`). Script: `pems_station_analysis.py`; map animation: `pems_station_animation.py`. Cross-checks from Census ACS and Zillow added 2026-11-02.*

## Hypothesis tested
People moved to Dublin and the Tri-Valley while work was remote. When RTO mandates arrived (2025), morning traffic from that area increased.

## Method (short)
- **Only measured data.** Only detector-hours that were ≥95% observed count; PeMS fills the rest with estimates. Federal holidays and district-wide outages are dropped. That includes hours where every detector reports near-zero flow while still marked "observed".
- **Each detector against its own past.** Every detector is compared with its own average for the same month in 2016–2019. A route's value is the median across its detectors.
- **Data used:** October 2016–2025, plus September 2017/18/19 and 2025/26. September 2026 gives a second RTO year.
- **Morning peak** = Tue–Thu, 5–10 AM.
- **The direct RTO test** compares the same detectors in the last hybrid year and the first RTO year.

## Result: the hypothesis is not supported

**Change from hybrid to RTO, same detectors** (morning commute direction):

| Route | Oct 2024 → Oct 2025 | Sep 2025 → Sep 2026 |
|---|---|---|
| I-580 W Altamont → Livermore (Central Valley inflow) | −2.4% | −1.2% |
| I-580 W Pleasanton / Dublin | −5.1% | +0.1% |
| I-680 N San Ramon / Danville | +2.6% | +0.9% |
| I-680 S Sunol grade (→ San Jose) | +8.9% (3 detectors) | +2.2% (1 detector) |
| I-580 E Livermore, outbound (control) | −0.2% | −3.3% |

**Level vs. pre-COVID** (Tue–Thu morning peak, 2016–19 = 100):

| Route | Oct 2020 | Oct 2021 | Oct 2024 | Oct 2025 | Sep 2026 |
|---|---|---|---|---|---|
| I-580 W Altamont → Livermore | 95 | 100 | 101 | 100 | 99 |
| I-580 W Pleasanton / Dublin | 94 | 99 | 97 | 92 | 96 |
| I-580 W Dublin grade (→ Oakland) | 84 | 90 | 93 | n/a | n/a |
| I-680 N San Ramon / Danville | 73 | 87 | 90 | 88 | 91 |
| I-680 S Sunol grade | 77 | 92 | 93 | 101 | 104 |
| I-580 E Livermore (outbound) | 89 | 107 | 106 | 106 | 104 |

- There is no step up in 2025 on the main Tri-Valley routes, and there's none from the first RTO year to the second.
- **Sunol (I-680 S to San Jose) is the one exception.** It moved from ~93 during hybrid to 101–104 under RTO, but it rests on only 1–4 detectors. Treat it as a lead.
- **Inflow over the Altamont from the Central Valley barely fell.** It was 95 in Oct 2020 and has been back at 100–103 since 2021. This fits people moving out who keep commuting, but there was no extra RTO increase.

## Other findings

1. **Outer counties recovered; core counties didn't.** Morning-peak index, Oct 2025:

   | Napa | Sonoma | Solano | Contra Costa | San Francisco | Santa Clara | Alameda | Marin | San Mateo |
   |---|---|---|---|---|---|---|---|---|
   | 112 | 106 | 102 | 100 | 97 | 96 | 95 | 94 | 92 |

   The animation shows this clearly.
2. **The reverse commute grew.** Outbound morning traffic on I-580 E through Livermore has run 4–9% above pre-COVID every year since 2021, and the 3–5 AM hours are up 20–30%. The cause isn't established; growth in Central Valley logistics is one possibility.
3. **The hybrid pattern persists under RTO.** Monday/Friday morning peaks trail Tue–Thu, district-wide:

   | | Mon/Fri | Tue–Thu |
   |---|---|---|
   | Oct 2024 | 95.8 | 97.9 |
   | Oct 2025 | 93.8 | 97.7 |
   | Sep 2026 | 95.9 | 98.0 |

   The PM peak (~98–100), midday (~99–100) and weekends (100–102) are fully back. Only the morning commute is still short.
4. **Freeways never emptied.** District-wide morning-peak traffic was 88% of normal in Oct 2020. Transit fell far further.
5. **The morning peak shifted ~1.5–2 minutes later** after 2021. That's negligible.

## Caveats (traffic counts)
- **One or two months per year.** October 2025 has only 8 usable Tue–Thu days (a District 4 outage after Oct 20).
- **Fewer working detectors over time.** Usable detectors fell from ~1,270 (2020) to ~550 (2025). Coverage at the Dublin grade (I-580 W west of I-680) ended after 2024, so Dublin's own westbound commute isn't measured for RTO.
- **Whole-freeway PeMS totals are unreliable for 2025.** The `pems_corridor_analysis.py` VMT figures (+10% for I-580 W) are mostly estimated and contradict these measured counts.
- **District 4 only.** Tracy and Mountain House (District 10) are seen only where their traffic enters District 4 at the Altamont.

## Cross-checks from survey and housing data

### Census ACS: how residents commute (`acs_commute_analysis.py`)
ACS 1-year estimates for 2019 and 2021–2025 (there's no standard 2020 release). Rates are per 100 resident workers. \* means the change is larger than its 90% margin of error. Tri-Valley = Dublin, Pleasanton, Livermore and San Ramon.

- **No RTO-year step here either.** Change in long commutes (60+ min) per 100 resident workers:

  | | 2023→24 (hybrid) | 2024→25 (RTO) |
  |---|---|---|
  | Core counties | +0.8\* | +0.1 |
  | San Francisco | +1.8\* | +0.6 |
  | Tri-Valley | +3.7\* | −0.3 |
  | Northern San Joaquin Valley | −0.6 | +0.4 |
  | Tracy | −2.6 | +3.6 (±6.5) |

- **Commuting came back during hybrid and stopped near the 2019 level.** Number of residents commuting 60+ min, as % of each area's 2019 count:

  | | 2021 | 2024 | 2025 |
  |---|---|---|---|
  | Core counties | 35% | 69% | 68% |
  | North Bay / Solano | 74% | 74% | 72% |
  | Sacramento region | 66% | 90% | 82% |
  | Northern San Joaquin Valley | 85% | 95% | 99% |
  | Tri-Valley (excl. Dublin, which has no 2019 estimate) | 33% | 99% | 87% |
  | Tracy | 70% | 82% | 98% (±24) |
  | Stockton | 95% | 93% | 108% (±24) |

  No area is clearly above 2019. If WFH movers had become commuters, the outer suburbs should be.
- **The outer suburbs barely stopped commuting.** At the 2021 peak, 10 in 100 San Joaquin Valley workers worked from home, against 35 in the core, so there was little to return. This matches the Altamont counts (95 → 100).
- **Tracy residents commute out less than in 2019.** Working outside the county fell from 53 to 44 per 100 workers, and leaving home before 6 AM from 27 to 20 (both beyond the margin of error).
- *Caveat:* the ACS counts anyone in the office 3+ days a week as a commuter, so a move from 3 to 5 days is invisible. City margins are wide: Tracy and Manteca rates carry ±5–7 points.

### Zillow: home values (`zillow_price_gradient_analysis.py`)
Zillow Home Value Index by ZIP, relative to the median study ZIP (Jan 2020 = 100):

| | Feb 2020 | Mar 2022 (end of WFH) | Dec 2024 (end of hybrid) | Aug 2026 |
|---|---|---|---|---|
| San Francisco | 100 | 81 | 69 | 79 |
| Tri-Valley (incl. Danville) | 100 | 114 | 116 | 108 |
| Tracy / Manteca / Mountain House | 100 | 111 | 111 | 105 |
| Santa Clara County | 100 | 102 | 109 | 110 |
| Exurbs 45+ mi from the office hubs | 100 | 101 | 102 | 102 |

- **The WFH shift was SF against the I-580 corridor, not a smooth distance gradient.** Value change by distance from the office hubs had a slope of only +0.7 points per 10 mi during WFH (+0.3 without SF), and about 0 under RTO.
- **Under RTO the corridor is giving back part of its gain while SF rebounds.** That fits RTO raising the value of living near the office, but SF's rebound may also be AI hiring, and the data can't separate the two. SF was already losing ground before COVID: its relative value fell from about 118 to 100 over 2015–2020.
- ZIPs 120+ mi out (Lake Tahoe / Truckee) are excluded as a vacation-home market.

## Figures
- `pems_station_screenline_index.png`: each route by year, with the hybrid → RTO step
- `pems_station_district_windows.png`: district-wide morning/midday/PM/Mon-Fri/weekend, and peak timing
- `pems_station_hourly_index.png`: hour-of-day change by era
- `pems_station_animation.mp4` / `.gif`: detector map, Oct 2016 → Sep 2026
- `acs_rto_step.png`: hybrid-year vs RTO-year change in residents' commuting, with margins of error
- `acs_long_commuter_index.png`: residents commuting 60+ min as % of 2019, 2021–2025
- `acs_place_trends.png` / `acs_commute_trends.png`: commuting measures for cities and county groups, 2019–2025
- `zillow_place_index.png`: places vs. the median ZIP, 2015–2026
- `zillow_gradient_by_era.png` / `zillow_distance_bands.png`: home-value change by distance from the office hubs
