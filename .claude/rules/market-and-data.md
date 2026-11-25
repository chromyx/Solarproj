# Market and data integrity

- Always identify the source, effective version, publication time, retrieval time, trading zone, product and unit.
- Verify market rules against primary documents; document source URLs and dates. Do not invent ALPEX APIs, available historical feeds, fees or gate closure procedures.
- Store time intervals with UTC start/end; display Europe/Tirane local periods. Handle DST, partial intervals and product-specific granularity.
- Store raw payloads and revision lineage; keep forecasts as they were known at each decision timestamp.
- Never silently fill unavailable actuals with fictional market data. Label synthetic, estimated, forecast and verified actual data distinctly.
- DC MWp, inverter AC MW, grid-export MW, hourly/interval MWh and annual GWh are different quantities. Enforce units in data contracts and tests.
