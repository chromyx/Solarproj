# Data source audit

Status values: **VERIFIED** (checked against the source and working), **LIMITED** (works, with restrictions or caveats), **UNVERIFIED** (not checked yet), **UNAVAILABLE** (no legal access route found).
All checks were done on **2026-11-25** unless stated.

## In use

### ALPEX day-ahead results (public website): LIMITED
| Item | Detail |
|---|---|
| URL | https://alpex.al/market-results/ (wpDataTables; rows load via `POST /wp-admin/admin-ajax.php?action=get_wdtable&table_id=89`) |
| Owner | ALPEX sh.a. (Albanian Power Exchange) |
| Data | Per delivery day and hourly MTU: AL price (EUR/MWh), AL volume (MWh), AL net position (MWh), and the same for KS |
| Coverage | From 12 Apr 2023 (first DAM delivery day) to today. Table reported 31,799 records on 2026-11-25 |
| Granularity | Hourly. 23 rows on spring DST days (label 3 skipped), 25 on autumn DST days. No 15-minute data seen yet |
| Access method | One request per delivery day with the `date` column filtered to `DD Mon YYYY\|DD Mon YYYY`. Multi-day ranges do **not** filter correctly. Requests are made about every 3 s, about 4 s per day in practice |
| robots.txt | `Disallow: /wp-admin/` but `Allow: /wp-admin/admin-ajax.php` |
| Licence | Site footer: "(c) ALPEX. All rights reserved." No data terms published. **No permission obtained.** The owner chose this free route on 2026-11-25 (instead of ENTSO-E, which needs an email). Rows are labeled `ALPEX_PUBLIC_WEB_ALL_RIGHTS_RESERVED_INTERNAL_USE`. **Internal use only. No hourly ALPEX data goes into git.** |
| Publication time | Not shown on the site. `published_at_utc` is stored as NULL. Before using this for decision backtests, the DAM publication time from the ALPEX trading procedures must be applied |
| Known quirks | The hidden `datetime` column is junk (e.g. "25 Oct 3026" on the 12:00 row, "01 Jan 1900" in 2023), so it is ignored. KS columns and AL net position are empty in the first months of 2023. About 1% of requests return a WordPress "Error establishing a database connection" page (HTTP 200, HTML) from ALPEX's own site. These are stored raw, followed by a 30 s pause and a retry |
| Cross-check | Monthly averages are compared with ALPEX's own monthly report PDFs (`powerdesk check monthly`; reference values in `data/reference/alpex_monthly_reported.yaml`) |
| Risks | The site layout can change: the parser then refuses (`AlpexSchemaError`) rather than guessing. Legal: written permission or a licensed feed is advisable before commercial reliance |

### ALPEX monthly reports and fee schedule (PDF): VERIFIED (as published)
- Monthly reports: https://alpex.al/monthly-reports/ (Apr 2023 to Oct 2026; PDF; the Mar 2026 PDF has no extractable text).
- Fee schedule v6 (uploaded Feb 2025): https://alpex.al/wp-content/uploads/2025/02/LISTA-E-TARIFAVE-NE-WEB-ANGLISHT_V6.pdf. Copied to `data/reference/alpex_fees.yaml`.

### PVGIS hourly radiation and weather (EU JRC): LIMITED
| Item | Detail |
|---|---|
| URL | https://re.jrc.ec.europa.eu/api/v5_3/seriescalc (no key) and `/PVcalc` for the cross-check |
| Data | Hourly beam and diffuse irradiance on the horizontal plane (W/m2), 2 m air temperature, 10 m wind. Radiation from PVGIS-SARAH3 (satellite), meteo from ERA5 |
| Coverage | 2005 to 2023 (19 years). Not real-time, and it does not cover 2024 to 2026 |
| Time convention | UTC; values are **hourly averages**; timestamps carry a minute offset (e.g. 12:10) |
| Licence | "Free for public use if the source is acknowledged": PVGIS (c) European Communities, 2001-2026. Commercial use is not addressed explicitly. Ask JRC-PVGIS@ec.europa.eu before commercial redistribution |
| Storage | Raw JSON (about 18 MB per location) is stored in `raw_payload` |

## Considered, not used now

| Source | Status | Why |
|---|---|---|
| ENTSO-E Transparency REST API (`web-api.tp.entsoe.eu`) | UNVERIFIED | Free. The token needs registration plus an email to transparency@entsoe.eu (owner declined for now). Albanian DA price availability not confirmed |
| Open-Meteo archive | UNAVAILABLE for this use | Free tier is non-commercial; returned HTTP 429 |
| ALPEX member API (ETSS, Technical Decision 5-T) | UNAVAILABLE | Members only (API user fee EUR 2,000/yr) |
| OST imbalance prices and settlement | UNVERIFIED | Needed for Step 4. Rules documents exist on ere.gov.al; the data feed has not been checked |
| Plant SCADA / revenue meter | UNAVAILABLE | Plant not built |
