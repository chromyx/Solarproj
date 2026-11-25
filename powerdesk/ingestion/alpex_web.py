"""ALPEX public market-results tables (alpex.al/market-results).

Data route chosen by the owner on 2026-11-25 ("free, no emailing"). Licence status: the ALPEX site
states "(c) ALPEX. All rights reserved." and publishes no data terms; no permission has been
obtained. Data is therefore labeled for INTERNAL USE ONLY and must not be redistributed or
committed to git. See docs/DATA_SOURCES.md.

How the site works (verified 2026-11-25): the page embeds wpDataTables tables that load rows
server-side via POST to /wp-admin/admin-ajax.php (allowed by alpex.al/robots.txt). Filtering the
`date` column with "DD Mon YYYY|DD Mon YYYY" for a single day returns that day's rows; multi-day
ranges do NOT work reliably, so we request one delivery day per call.
"""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from powerdesk.canonical import CanonicalValue, UpsertStats, coverage_by_day, store_values
from powerdesk.ingestion.base import PoliteHttp, store_raw_payload
from powerdesk.timeutil import Interval, alpex_hourly_mtu_map

log = logging.getLogger(__name__)

SOURCE_NAME = "ALPEX_WEB"
LICENSE_STATUS = "ALPEX_PUBLIC_WEB_ALL_RIGHTS_RESERVED_INTERNAL_USE"
RESULTS_PAGE_URL = "https://alpex.al/market-results/"
AJAX_URL = "https://alpex.al/wp-admin/admin-ajax.php?action=get_wdtable&table_id={table_id}"

# Table order on the page is DAM, CRIDA-1, CRIDA-2, CRIDA-3 (tab labels). Mapping to table ids is
# INFERRED from that order (table 109 shows 12 rows per page, consistent with a 12-hour CRIDA-3).
TABLE_ID_BY_PRODUCT = {"DAM": 89, "CRIDA-1": 103, "CRIDA-2": 104, "CRIDA-3": 109}

REQUIRED_COLUMNS = (
    "mtu", "date", "almcpmwh", "alvolumemwh", "alnetpositionmwh",
    "ksmcpmwh", "ksvolumemwh", "ksnetpositionmwh", "datetime",
)
VALUE_COLUMNS = {
    ("AL", "price"): "almcpmwh",
    ("AL", "volume"): "alvolumemwh",
    ("AL", "net_position"): "alnetpositionmwh",
    ("KS", "price"): "ksmcpmwh",
    ("KS", "volume"): "ksvolumemwh",
    ("KS", "net_position"): "ksnetpositionmwh",
}
DATE_FORMAT = "%d %b %Y"  # e.g. "25 Oct 2026" (datepickFormat "dd M yy")


class AlpexSchemaError(RuntimeError):
    """The site's table layout changed; refuse to guess."""


class AlpexBadResponse(RuntimeError):
    """A response that is not the expected JSON (seen transiently); retried, then reported."""


@dataclass(frozen=True)
class TableConfig:
    table_id: int
    nonce: str
    columns: tuple[str, ...]


def parse_results_page(page_html: str) -> dict[int, TableConfig]:
    """Extract table ids, column names and request nonces from the results page HTML."""
    out: dict[int, TableConfig] = {}
    for m in re.finditer(r'id="table_\d+_desc"\s*value=\'(.*?)\'', page_html, re.S):
        desc = json.loads(html.unescape(m.group(1)))
        table_id = int(desc["tableWpId"])
        columns = tuple(c["name"] for c in desc["dataTableParams"]["columnDefs"])
        nm = re.search(rf'id="wdtNonceFrontendEdit_{table_id}"[^>]*value="([^"]+)"', page_html)
        if nm is None:
            raise AlpexSchemaError(f"No request nonce found for table {table_id}")
        out[table_id] = TableConfig(table_id, nm.group(1), columns)
    if not out:
        raise AlpexSchemaError("No wpDataTables found on results page")
    return out


def build_day_request(cfg: TableConfig, day: date, length: int = 100) -> dict[str, str]:
    missing = [c for c in REQUIRED_COLUMNS if c not in cfg.columns]
    if missing:
        raise AlpexSchemaError(f"Table {cfg.table_id} is missing columns {missing}")
    day_s = day.strftime(DATE_FORMAT)
    data = {
        "draw": "1", "start": "0", "length": str(length),
        "order[0][column]": "0", "order[0][dir]": "asc",
        "search[value]": "", "search[regex]": "false",
        "wdtNonce": cfg.nonce,
    }
    for i, name in enumerate(cfg.columns):
        data[f"columns[{i}][data]"] = str(i)
        data[f"columns[{i}][name]"] = name
        data[f"columns[{i}][searchable]"] = "true"
        data[f"columns[{i}][orderable]"] = "true"
        data[f"columns[{i}][search][value]"] = f"{day_s}|{day_s}" if name == "date" else ""
        data[f"columns[{i}][search][regex]"] = "false"
    return data


@dataclass(frozen=True)
class ParsedRow:
    mtu: int
    interval: Interval
    record_id: str
    values: dict[tuple[str, str], Decimal]
    notes: tuple[str, ...] = ()


@dataclass
class ParsedDay:
    day: date
    rows: list[ParsedRow]
    issues: list[str] = field(default_factory=list)


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), DATE_FORMAT).date()  # noqa: DTZ007 - a date, not a time
    except ValueError:
        return None


def parse_day_response(content: bytes, day: date, columns: tuple[str, ...]) -> ParsedDay:
    """Parse one day's server response into validated rows. Never invents values."""
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise AlpexSchemaError(f"Missing columns {missing}")
    idx = {name: i for i, name in enumerate(columns)}
    try:
        payload: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AlpexBadResponse(f"response is not JSON ({len(content)} bytes): {exc}") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise AlpexBadResponse("response has no 'data' list")

    result = ParsedDay(day=day, rows=[])
    filtered = int(payload.get("recordsFiltered", len(data)))
    if filtered != len(data):
        result.issues.append(f"server reported {filtered} rows but returned {len(data)}")

    mtu_map = alpex_hourly_mtu_map(day)
    by_mtu: dict[int, list[ParsedRow]] = {}
    for raw_row in data:
        if not isinstance(raw_row, list) or len(raw_row) != len(columns):
            result.issues.append(f"malformed row {raw_row!r}")
            continue
        row_day = _parse_date(str(raw_row[idx["date"]]))
        if row_day != day:
            result.issues.append(f"dropped row dated {raw_row[idx['date']]!r} (requested {day})")
            continue
        try:
            mtu = int(str(raw_row[idx["mtu"]]))
        except ValueError:
            result.issues.append(f"non-integer MTU {raw_row[idx['mtu']]!r}")
            continue
        if mtu not in mtu_map:
            result.issues.append(f"MTU label {mtu} does not exist on {day} ({len(mtu_map)}h day)")
            continue
        # The hidden secondary 'datetime' column is NOT used: it is unreliable at the source
        # (e.g. '25 Oct 3026' on the 12:00 row, '01 Jan 1900' in 2023). The visible 'date' column
        # is authoritative; the raw payload keeps everything.
        notes: list[str] = []
        values: dict[tuple[str, str], Decimal] = {}
        for key, col in VALUE_COLUMNS.items():
            cell = raw_row[idx[col]]
            if cell is None or str(cell).strip() == "":
                result.issues.append(f"MTU {mtu}: empty {col}")
                continue
            try:
                values[key] = Decimal(str(cell).replace(",", ""))
            except InvalidOperation:
                result.issues.append(f"MTU {mtu}: unparseable {col}={cell!r}")
        by_mtu.setdefault(mtu, []).append(
            ParsedRow(mtu, mtu_map[mtu], str(raw_row[idx["wdt_ID"]]) if "wdt_ID" in idx else "",
                      values, tuple(notes))
        )

    for mtu, rows in sorted(by_mtu.items()):
        if len(rows) == 1:
            result.rows.append(rows[0])
        elif all(r.values == rows[0].values for r in rows):
            result.rows.append(rows[0])
            result.issues.append(f"MTU {mtu}: {len(rows)} identical duplicate rows collapsed")
        else:
            result.issues.append(f"MTU {mtu}: {len(rows)} conflicting rows; none stored")
    missing_mtus = sorted(set(mtu_map) - {r.mtu for r in result.rows})
    if missing_mtus:
        result.issues.append(f"missing MTU labels {missing_mtus}")
    return result


def to_canonical(
    parsed: ParsedDay, product: str, raw_payload_id: int,
    source_name: str = SOURCE_NAME, is_simulated: bool = False,
    license_status: str = LICENSE_STATUS,
) -> list[CanonicalValue]:
    out: list[CanonicalValue] = []
    for row in parsed.rows:
        for (zone, quantity), value in row.values.items():
            out.append(CanonicalValue(
                interval=row.interval, delivery_day_local=parsed.day, market_zone=zone,
                product=product, quantity=quantity, value=value, source_name=source_name,
                source_record_id=row.record_id or None, source_mtu_label=row.mtu,
                is_simulated=is_simulated, source_license_status=license_status,
                raw_payload_id=raw_payload_id, extra_notes=row.notes,
            ))
    return out


@dataclass
class DayResult:
    day: date
    skipped: bool = False
    rows: int = 0
    issues: list[str] = field(default_factory=list)
    stats: UpsertStats | None = None
    error: str | None = None


def _ingest_one_day(
    session_factory: sessionmaker[Session], client: PoliteHttp, cfg: TableConfig, product: str, day: date,
    attempts: int, bad_response_pause_s: float = 30.0,
) -> DayResult:
    """Fetch -> store raw bytes (always, even if unparseable) -> parse -> store canonical values."""
    res = DayResult(day)
    form = build_day_request(cfg, day)
    for attempt in range(1, attempts + 1):
        fetched = client.request(
            "POST", AJAX_URL.format(table_id=cfg.table_id), data=form,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": RESULTS_PAGE_URL},
        )
        with session_factory.begin() as s:
            raw = store_raw_payload(
                s, SOURCE_NAME, fetched, LICENSE_STATUS,
                note=f"{product} delivery day {day.isoformat()} attempt {attempt}",
                params_for_record={"table_id": cfg.table_id, "product": product,
                                   "delivery_day": day.isoformat()},
            )
            try:
                parsed = parse_day_response(fetched.content, day, cfg.columns)
            except AlpexBadResponse as exc:
                log.warning("bad response day=%s attempt=%d raw_payload_id=%d: %s",
                            day, attempt, raw.id, exc)
                if attempt == attempts:
                    raise
                client.pause(bad_response_pause_s)  # give the site's own database time to recover
                continue
            res.stats = store_values(s, to_canonical(parsed, product, raw.id))
        res.rows = len(parsed.rows)
        res.issues = parsed.issues
        return res
    raise AssertionError("unreachable")  # pragma: no cover


def ingest_range(
    session_factory: sessionmaker[Session],
    start: date,
    end: date,
    product: str = "DAM",
    http: PoliteHttp | None = None,
    refresh: bool = False,
    on_day: Callable[[DayResult], None] | None = None,
    max_consecutive_failures: int = 5,
    bad_response_attempts: int = 3,
    bad_response_pause_s: float = 30.0,
) -> list[DayResult]:
    """Fetch and store one delivery day at a time. Days already complete are skipped unless refresh.

    Fails safe: stops after `max_consecutive_failures` failed days (e.g. if the site blocks us).
    """
    if product not in TABLE_ID_BY_PRODUCT:
        raise ValueError(f"Unknown product {product}")
    table_id = TABLE_ID_BY_PRODUCT[product]
    own_http = http is None
    client = http or PoliteHttp()
    results: list[DayResult] = []
    try:
        with session_factory() as s:
            todo = [c.day for c in coverage_by_day(s, SOURCE_NAME, "AL", product, "price", start, end)
                    if refresh or not c.complete]
        if not todo:
            return results
        page = client.request("GET", RESULTS_PAGE_URL)
        configs = parse_results_page(page.content.decode("utf-8", errors="replace"))
        if table_id not in configs:
            raise AlpexSchemaError(f"Table {table_id} ({product}) not found on results page")
        cfg = configs[table_id]
        with session_factory.begin() as s:
            layout = replace(
                page, params={}, content_type="application/json",
                content=json.dumps({"table_id": cfg.table_id, "columns": cfg.columns}).encode(),
            )
            store_raw_payload(
                s, SOURCE_NAME, layout, LICENSE_STATUS,
                note=f"table layout extracted from results page (page sha256 {page.sha256})",
            )
        consecutive_failures = 0
        for day in todo:
            res = DayResult(day)
            try:
                res = _ingest_one_day(session_factory, client, cfg, product, day, bad_response_attempts,
                                      bad_response_pause_s)
            except AlpexSchemaError as exc:
                res.error = f"AlpexSchemaError: {exc}"
                results.append(res)
                raise  # layout changed: stop rather than guess
            except Exception as exc:  # the day stays incomplete and is retried next run
                res.error = f"{type(exc).__name__}: {exc}"
                log.error("day failed day=%s error=%s", day, res.error)
            results.append(res)
            if on_day:
                on_day(res)
            consecutive_failures = consecutive_failures + 1 if res.error else 0
            if consecutive_failures >= max_consecutive_failures:
                log.error("stopping: %d consecutive failed days", consecutive_failures)
                break
    finally:
        if own_http:
            client.close()
    return results
