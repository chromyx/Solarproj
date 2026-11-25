# ALPEX and Albanian market facts used by POWERDESK

Each fact has a status and a source. Re-check before any real trading decision.
Checked 2026-11-25 unless stated.

| Fact | Status | Source / note |
|---|---|---|
| ALPEX runs the day-ahead market (DAM) for the Albania (AL) and Kosovo (KS) bidding zones, coupled. Prices converge in over 99% of hours | VERIFIED (published) | ERE Board Decision 156/2026; ALPEX monthly reports |
| First DAM delivery day in the public results: 12 Apr 2023 | VERIFIED (data) | alpex.al/market-results |
| DAM results are hourly. On DST days there are 23 MTUs (label 3 skipped) or 25 MTUs | VERIFIED (data, 2026-03-29 and 2026-10-25) | alpex.al/market-results |
| On 25-hour days, labels 3 and 4 are the first and second 02:00-03:00 local hour (sequential) | ASSUMED | Not confirmed by an ALPEX document; `powerdesk/timeutil.py` |
| A move to 15-minute MTU is being tested | UNVERIFIED (details) | ERE Board Decisions 2026 (e.g. 177/2026) mention 15-minute resolution testing |
| DAM price limits: floor -50 EUR/MWh (lowered from 0, reported July 2026), cap 900 EUR/MWh | LIMITED (secondary source) | Balkan Green Energy News, 2026-07-31; not yet checked in the ALPEX rules text |
| Intraday is auction-based: CRIDA-1, CRIDA-2, CRIDA-3 | LIMITED | Tab names on alpex.al/intraday-market. Gate times not checked. Table ids 103/104/109 inferred from page order |
| 52 exchange members (Oct 2026). 38 also active intraday. 6 general clearing members | VERIFIED (published) | ALPEX October 2026 monthly report; alpex.al/exchange-members |
| Fees: entrance EUR 10,000; DAM membership EUR 14,000/yr; intraday EUR 8,000/yr; direct clearing EUR 3,000/yr; DAM trading EUR 0.09/MWh and clearing EUR 0.02/MWh; VAT applies | VERIFIED (published schedule v6, Feb 2025) | `data/reference/alpex_fees.yaml`. Supersedes ERE 287/2023 (EUR 7,000 / 0.07 / 0.02) |
| Albanian fees are settled in Lek at the Bank of Albania rate (residents) | VERIFIED (published) | Fee schedule v6 |
| ERE: the DAM is "not yet ready" as a reference price for CfD support (Nov 2024 to Oct 2025 review) | VERIFIED (published) | ERE Board Decision 156/2026; AEA summary |
| Liquidity: in 25% of hours the DAM could absorb only about 146 MW of extra zero-cost supply; median bid-ask spread 9.7% | VERIFIED (secondary summary of the ERE assessment) | aea-al.org, 2026-04-20 |
| Balance responsibility and imbalance settlement for a new solar plant | UNVERIFIED | Albanian Balancing Market Rules (ERE 2021/2023); 2026 changes not checked |
| Collateral: euro cash at 100%, Lek cash at 130% of equivalent value, or letters of guarantee. The margin requirement is based on net position; a net claim (e.g. a seller's proceeds) counts as available cover | VERIFIED (published page) | https://alpex.al/risk-management-for-day-ahead-and-intraday-markets (Technical Decision 3-C not read) |
| Default fund initial contribution: EUR 30,000 (direct clearing member), EUR 150,000 (general clearing member), recalculated monthly | VERIFIED (published page) | same page |
