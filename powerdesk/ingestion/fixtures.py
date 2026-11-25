"""SYNTHETIC test data in the ALPEX results-table response format.

Every value produced here is invented for tests. It must never be shown as market data:
rows ingested from these fixtures carry source_name="FIXTURE" and is_simulated=True.
"""

from __future__ import annotations

import json
from datetime import date

from powerdesk.ingestion.alpex_web import DATE_FORMAT
from powerdesk.timeutil import alpex_hourly_mtu_map

FIXTURE_SOURCE_NAME = "FIXTURE"
FIXTURE_LICENSE = "SYNTHETIC_TEST_DATA"
FIXTURE_COLUMNS = (
    "wdt_ID", "wdt_created_by", "wdt_created_at", "wdt_last_edited_by", "wdt_last_edited_at",
    "mtu", "date", "almcpmwh", "alvolumemwh", "alnetpositionmwh",
    "ksmcpmwh", "ksvolumemwh", "ksnetpositionmwh", "datetime",
)


def synthetic_price(mtu: int) -> str:
    """Obviously artificial price pattern: 50.00 + MTU label."""
    return f"{50 + mtu:.2f}"


def synthetic_row(day: date, mtu: int, record_id: int, price: str | None = None) -> list[str | None]:
    d = day.strftime(DATE_FORMAT)
    p = price if price is not None else synthetic_price(mtu)
    return [str(record_id), None, "", None, "", str(mtu), d, p, "100.00", "-10.00",
            p, "90.00", "10.00", d]


def synthetic_day_response(day: date, rows: list[list[str | None]] | None = None) -> bytes:
    if rows is None:
        rows = [synthetic_row(day, mtu, 1000 + i) for i, mtu in enumerate(sorted(alpex_hourly_mtu_map(day)))]
    payload = {"draw": 1, "recordsTotal": "999", "recordsFiltered": str(len(rows)), "data": rows}
    return json.dumps(payload).encode()
