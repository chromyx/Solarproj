---
name: paper-trading-day
description: Carry out a reproducible POWERDESK forward paper-trading run without submitting any live exchange orders.
---

# Daily forward paper trading

1. Check simulation-only mode and source health.
2. Capture versions of weather/price/production forecasts and exchange rules, including observation and publication timestamps.
3. Generate candidate delivery-interval sell schedules and risk estimates.
4. Independently check risk limits; freeze simulated orders and predictions before market outcomes.
5. When results arrive, record actual ALPEX outcomes and, if plant operating, metered export.
6. Compute simulated order acceptance, incremental net costs and positions, disclosing unknown settlement inputs.
7. Compare against predeclared passive benchmark.
8. Save tamper-evident run ID, strategy hash, data hashes, decisions and P&L reconciliation report.
9. Never send orders to a real exchange or represent paper returns as realized earnings.
