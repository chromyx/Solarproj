# POWERDESK milestone roadmap

Status at creation: **project instructions and setup only**. No operational trading platform, market adapter, tested model or real trade exists merely because these files are present.

**Progress (2026-11-25), working one small step at a time:**
- Phase 0: source audit started (`docs/DATA_SOURCES.md`, `docs/MARKET_RULES.md`); plant unknowns registered (`docs/PLANT.md`). Balancing, collateral and licensing rules are still UNVERIFIED.
- Phase 1: ALPEX DAM collector built (public website route; licence LIMITED, internal use). Tested on DST days; monthly cross-check against ALPEX reports.
- Phase 2 (partial, pre-design): pvlib baseline on PVGIS history with PROVISIONAL parameters; yield cross-checked against the PVGIS calculator. Not calibrated: the plant is not built and design documents are missing.
- Step 2 decision report ("what would the plant have earned"): `reports/`.

| Phase | Outcome | Exit gate |
|---|---|---|
| 0: Discovery | Verified market/data audit, scope, risks, architecture | Primary source links; explicit unknowns; accepted data contracts |
| 1: Data | ALPEX import adapter, raw and canonical storage, validation, explorer | Real downloaded licensed sample OR explicit fixture mode; tests for times/units/revisions |
| 2: Solar | Physical PV baseline and forecast revisions | Unit tests; physical plausibility; verified design assumptions |
| 3: Price | Baselines, ML, probabilistic prediction | Out-of-time evaluation; baseline comparison; no leakage |
| 4: Simulator | Day-ahead/intraday order, positions, balancing and settlement | Exchange-rule tests, separate ledgers, independent reconciliation |
| 5: Strategy | Bidding, correction, limits and optimized simulation | Net economic backtest vs passive baseline; risk rules enforced |
| 6: Terminal | Operational dashboard, admin, audits and provenance labels | End-to-end tested, accurate labels, responsive UI |
| 7: Forward test | Daily frozen paper decisions and outcomes | Initial 90 days; seasonality limitation acknowledged; verifiable ledger |
| 8: Readiness | Security/compliance/operations, data and market integration readiness | Independent reviewer; source licences; human approval; restore tested |
| 9: Live | Narrowly scoped authorized commercial pilot | Owner approval, licensed access, risk gate, reconciled live statements |
| 10: Growth | Battery and multi-asset products | Existing plant edge proven and risk budget approved |

Time estimates are speculative until source access and plant scope are verified. Phase 1 must not depend on completing all later modules.
