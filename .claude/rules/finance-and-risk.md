# Financial correctness, risk and authorization

- Physical capacity, energy, market revenue, incremental trading edge, project EBITDA and equity cash flows must not be conflated.
- Capture price must be energy weighted and must define its net/gross basis.
- Money calculations require decimal-safe precision and independently calculated reconciliation fixtures.
- Count exchange fees, intraday/auction execution, liquidity, imbalance/balancing, BRP/clearing and software costs where applicable; explicitly disclose missing costs.
- Never compare trading strategies using different hindsight information or different asset conditions.
- Default execution mode is `SIMULATION_ONLY`; live order entry must be unavailable in the baseline build.
- Do not access real exchange credentials, submit orders, spend money or deploy to production without specific explicit authorization and documented controls.
- Require independent risk engine, approvals, position/credit limits, duplicate protection and audit trail before any real order adapter is enabled.
- Report tests exactly: pass/fail/skipped and the commands actually executed.
