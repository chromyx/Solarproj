---
name: market-source-audit
description: Verify official power-market rules and data feeds for POWERDESK; use before making market-rule or API integration decisions.
---

# Source audit procedure

1. Identify exact question, jurisdiction, bidding zone, product and effective date.
2. Find authoritative primary source and note title, URL, publish/effective date, version and access date.
3. Check source availability, API or download method, data licensing, historical range, update interval and revision history.
4. Confirm units, timestamps, delivery-time convention and DST behavior using sample records.
5. Classify: VERIFIED / LIMITED / UNVERIFIED / UNAVAILABLE.
6. Add concise evidence to `docs/DATA_SOURCES.md` or `docs/MARKET_RULES.md` when those files exist.
7. Where unavailable, design an explicit fixture-mode adapter, never a fictitious API.
