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
