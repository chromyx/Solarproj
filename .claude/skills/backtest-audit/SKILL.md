---
name: backtest-audit
description: Audit quantitative electricity strategies for leakage, false profitability, settlement errors and unrealistic execution.
---

# Backtest audit procedure

1. Define decision time, outcome time, interval, delivery product, target asset and market rules.
2. Freeze available-as-of dataset versions; verify no future weather or market revisions leak backward.
3. Define a passive benchmark with identical physical output and market conditions.
4. Model accepted/rejected bids, liquidity, fees, imbalances, BRP/clearing and collateral constraints.
5. Test chronologically, with never-tuned holdout and walk-forward folds; include seasonal stress periods.
6. Reconcile interval MWh, transaction ledger, capture price and monetary P&L independently.
7. Report improvement as incremental **net** €/MWh and € with downside, drawdown and uncertainty.
8. State limitations. A strong backtest is research evidence, not proof of actual trading profit.
