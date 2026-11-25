# POWERDESK

Market data, solar modeling and (later) trading decision support for **ONE SOLAR's 15.5 MW solar plant in Divjake, Albania**, selling on **ALPEX**.

**Mode: `SIMULATION_ONLY`.** This code does not submit orders to any exchange and contains no order-entry path. Every number is labeled ACTUAL, MODELED, SIMULATED or ILLUSTRATIVE; see `docs/DATA_CONTRACTS.md`.

## Status (2026-11-25)

| Step | What | Status |
|---|---|---|
| 0 | Repo, starter instructions, source audit, plant parameter register | done |
| 1 | ALPEX day-ahead price history collector (raw + canonical, append-only, DST-safe) | built and tested; full history collected locally |
| 2 | "What would the plant have earned?" report (pvlib + PVGIS + ALPEX prices) | built and tested; see `reports/` |
| 3+ | Daily paper bid sheet, imbalance ledger, battery... | not started (only if Steps 1-2 show value) |

Roadmap and gates: `docs/ROADMAP.md`. Evidence rules: `docs/VALIDATION_PLAN.md`.

## Quick start

Requirements: Python 3.12+ and PostgreSQL 16 (via `docker compose up -d db`, or a local install).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # then export the variables, e.g. `set -a; . ./.env; set +a`

powerdesk db upgrade                                    # create tables (append-only triggers)
powerdesk ingest alpex --from 2023-04-12                # one request per day, ~3 s apart (~70 min first run)
powerdesk sources status                                # coverage, gaps, freshness
powerdesk check monthly                                 # cross-check vs ALPEX monthly reports
powerdesk report earnings                               # writes reports/earnings_<date>.md + .json
```

Re-running `ingest alpex` only fetches missing or incomplete days. `--refresh` re-fetches complete days; changed values are stored as new revisions and never overwritten.

## Tests

```bash
export POWERDESK_TEST_DATABASE_URL=postgresql+psycopg://powerdesk:powerdesk_dev@localhost:5432/powerdesk_test
ruff check . && mypy && pytest -q
```

Database tests are skipped when `POWERDESK_TEST_DATABASE_URL` is not set. CI (`.github/workflows/ci.yml`) runs them against PostgreSQL. All test data is synthetic; no real ALPEX data is stored in git.

## Layout

```
powerdesk/
  timeutil.py            delivery days -> UTC intervals (23/24/25 h; 15/60 min), ALPEX MTU labels
  canonical.py           validation, revision-safe storage, coverage
  db/                    SQLAlchemy models + Alembic migration (append-only triggers)
  ingestion/alpex_web.py ALPEX public results collector (one delivery day per request)
  solar/pvgis.py         PVGIS hourly weather download (stored raw)
  solar/model.py         pvlib model: weather -> exported MWh per hour
  analysis/earnings.py   capture price / revenue arithmetic (Decimal)
  analysis/report.py     earnings report
  cli.py                 `powerdesk` command
config/plant.yaml        plant parameters, each CONFIRMED / PROVISIONAL / UNKNOWN
data/reference/          published ALPEX figures used for cross-checks and fees (cited)
docs/                    master prompt, roadmap, validation plan, data contracts, sources, market rules, plant
```

## Important
- Plant parameters are mostly **provisional** (see `docs/PLANT.md`). Production figures are scenarios, not expected generation.
- ALPEX data comes from the public website (all rights reserved, no permission obtained), **for internal use only**. Do not redistribute it. See `docs/DATA_SOURCES.md`.
- Never put credentials in the repository, `.env.example` or chat.
- Live trading needs separate authorization, exchange membership, risk controls and review (`docs/MASTER_PROMPT.md` sections 10 and 14).
