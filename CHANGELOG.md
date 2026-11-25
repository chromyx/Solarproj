# Changelog

## 2026-11-25
- Starter pack added (instructions, rules, agents, skills, roadmap, validation plan, data contracts).
- Step 1: ALPEX day-ahead collector (`powerdesk ingest alpex`): raw payloads stored first; append-only
  tables enforced by DB triggers; DST-aware MTU mapping; retries, a 30 s pause after site errors, and a
  fail-safe stop after 5 consecutive failed days; coverage and freshness status; monthly cross-check vs
  ALPEX reports.
- Step 2: pvlib production model on PVGIS 2005-2023 weather, earnings arithmetic in Decimal,
  `powerdesk report earnings`.
- Docs: data source audit, market facts with status, plant parameter register, ALPEX fee schedule v6.
- Full ALPEX AL/KS day-ahead history collected locally (12 Apr 2023 to 24 Nov 2026): 31,750 of 31,753
  hourly AL prices; 0 failed days; about 1% transient ALPEX site errors, retried.
- Found and handled source issues: ALPEX DST labeling differs by year (detected per day from the
  published labels); two autumn DST days published with 24 labels are marked BAD; one corrupted
  label on 2023-12-31. Price limits changed over time (-500 and +4,000 EUR/MWh seen in 2024).
- Monthly cross-check vs ALPEX reports: 8/9 exact; the Oct 2026 AL headline (240.08) contradicts
  the report's own per-hour table (our 242.08) and is recorded as an explained discrepancy.
- First earnings report: `reports/earnings_2026-11-25.md`.
