# Data contracts and invariants

## Units and definitions
- `capacity_dc_mwp`: panel nameplate DC peak power.
- `capacity_ac_mw`: inverter AC rated power.
- `grid_export_limit_mw`: contracted/exportable maximum at connection point.
- `energy_export_mwh`: energy delivered over specified start/end interval (not power).
- `annual_energy_gwh = sum(interval_export_mwh) / 1000`.
- `price_eur_per_mwh`: euros per MWh for stated trading zone/product and delivery interval.
- `capture_price_eur_per_mwh`: total electricity revenue / delivered MWh, clearly identifying net/gross basis and exclusions.
- `incremental_net_trading_pnl_eur`: strategy net result minus fair baseline net result on matched delivery/production.

## Mandatory interval fields
`delivery_start_utc`, `delivery_end_utc`, `market_zone`, `product`, `source_name`, `source_record_id`, `published_at_utc`, `observed_at_utc` (if applicable), `ingested_at_utc`, `revision_id`, `value`, `unit`, `quality_status`, `is_simulated`, `source_license_status`.

## Invariants
- Positive interval duration; interval energy must not be mistakenly scaled by 1h if delivery is 15 or 30 minutes.
- Revenue = accepted/scheduled energy times relevant settlement price and netting conventions, followed by explicit fees and imbalances.
- Summed intervals reconcile to daily/monthly annual energy; settlement journal balances.
- No conflicting duplicate revision keys; raw records preserved.
- Reject or flag missing publication-time provenance where it affects backtesting.
- On-site meter, inverter output and grid export are distinct measurement boundaries.
- Use integer cents or Python `Decimal` for settlement; floats may be used in forecasting research but not as exact final ledger accounting.

## Earnings report definitions (Step 2)
- `energy_mwh`: modeled exported MWh summed over the priced hours (MODELED-PROVISIONAL).
- `revenue_eur`: sum over hours of MWh x ALPEX AL day-ahead price. Gross sales value before any cost (SIMULATED-HISTORICAL, not realized).
- `capture_eur_mwh`: revenue_eur / energy_mwh, generation-weighted and gross.
- `baseload_eur_mwh`: simple mean of hourly prices over the same hours. `capture_rate` = capture / baseload.
- `curtailed_*`: the same figures if the plant exported nothing in hours with price < 0. This assumes the plant can curtail, which is not verified.
- P50 / P90 / P10 across weather years: P90 is the value exceeded in 90% of weather years (the 10th percentile). P10 is the 90th percentile.
- Money is `Decimal`, rounded to cents only at the end. Model MWh is rounded to 0.001 MWh before money arithmetic.
