# POWERDESK — Project instructions for Claude Code

## Mission
Build a reliable, verifiable, risk-controlled electricity trading and optimization platform for a **15.5 MW solar PV project in Albania**. The company intends to trade directly on ALPEX through an in-house desk. Start with validated market-data infrastructure and paper simulation. Do not enable real exchange orders without separate authorization and complete readiness gates.

## Canonical documents
- `docs/MASTER_PROMPT.md` — full requirements and project mission.
- `docs/ROADMAP.md` — milestones and definitions of done.
- `docs/VALIDATION_PLAN.md` — evidence required to claim results.
- `docs/DATA_CONTRACTS.md` — timestamp, provenance, energy and money invariants.
- `.claude/rules/` — mandatory safety, data and finance rules.

## Critical unknowns
15.5 MW may be DC MWp or AC; grid export limit, coordinates, construction/commissioning dates, plant specs, yield study, licences, clearing and BRP arrangements are not provided. Never fabricate them. Mark assumptions in config and in UI.

## Development loop
1. Inspect repo and read relevant docs.
2. State scope, plan, dependencies and acceptance tests.
3. Implement smallest functional and tested vertical slice.
4. Run lint/types/tests; preserve exact output.
5. Document actual vs synthetic data, blocked integrations, security concerns and next steps.
6. Never claim success, profitability or live readiness without evidence.

## Mandatory engineering rules
- UTC storage; `Europe/Tirane` presentation; handle DST and different delivery-period lengths.
- Preserve original publication/as-of time, data source, retrieval time, revisions and licences.
- No look-ahead bias, leaked future data, fabricated market APIs, or unlabeled simulated values.
- Use MW for power, MWh for interval energy, GWh for aggregate energy, and €/MWh for market price; explicitly define MWp DC, MW AC and grid export MW.
- Use precise monetary arithmetic; reconcile schedule, meter, trades, settlement and P&L.
- Model bid acceptance, fees, liquidity and balancing; avoid assuming perfect execution.
- Enforce independent risk limits. No live trades, broad credential access, spending or production deployment without explicit owner approval.
- Keep README and milestone documents current. Prefer maintainability over code volume.

## Stack defaults
Python 3.12+, FastAPI, PostgreSQL, pandas/Polars, pvlib, LightGBM for later phases, Pyomo/HiGHS for optimization; Next.js/TypeScript later, pytest/Playwright, Docker Compose and GitHub Actions where useful. Prefer lean Phase 1 implementation first.

## Phase 1 objective
Create schema/migrations, raw-data storage, a verified ALPEX import interface, UTC interval normalization, provenance and revision tracking, a test dataset, deterministic tests, basic data explorer/API and source availability report. Do not pretend a missing live feed exists.
