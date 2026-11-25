# Evidence-based validation plan

## Absolute rules
- A completed frontend is not evidence of profitable trading.
- Simulated records are not actual generation, accepted exchange orders or settled profits.
- Forecast accuracy is necessary but not sufficient for net financial uplift.
- Model decisions must be reconstructable from information available **before** delivery and auction deadlines.

## Baseline
Use a predeclared passive day-ahead scheduling/selling policy for the same 15.5 MW plant, actual delivered MWh and relevant ALPEX market conditions. Price acceptance, fees, BRP/imbalance settlement and other costs must be modeled comparably. If settlement data is unavailable, distinguish an incomplete economic proxy from audited net returns.

## Staged evidence
1. Software: unit/integration/property/reconciliation tests for all critical data and money transforms.
2. Forecasts: time-separated walk-forward tests, baselines, errors, probability calibration, error by month and season.
3. Historical strategies: decision timestamp snapshots, fees, execution, imbalance, stress testing, no leakage.
4. Forward paper: immutable daily orders and predictions; no retroactive revisions; minimum initial 90 days with clear limits.
5. Live controlled: market eligibility, risk approval, manual oversight, finance settlements, operational incident logs.
6. Financial proof: realized incremental net €/MWh and total € against baseline; uncertainty, drawdown, bad regimes and independent verification.

## Reporting metrics
Source coverage and staleness; production MAE/bias; price MAE/bias and probabilistic calibration; order acceptance and fill assumptions; balancing €/MWh; net realized capture €/MWh; incremental net trading €/MWh and €; max drawdown; control breaches; unsettled discrepancies; model version and deployed strategy version.

## Prohibited shortcuts
Never use data published after the historical decision, pretend orders fill without liquidity, ignore rejection or transaction fees, double count trading uplift, tune repeatedly on the same holdout, fabricate values, or claim a statistically meaningful edge from a short lucky streak.
