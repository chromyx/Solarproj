"""Parser tests on SYNTHETIC responses in the ALPEX table format (no real ALPEX data in git)."""

from datetime import date
from decimal import Decimal

import pytest

from powerdesk.ingestion.alpex_web import (
    AlpexBadResponse,
    AlpexSchemaError,
    TableConfig,
    build_day_request,
    parse_day_response,
    parse_results_page,
    to_canonical,
)
from powerdesk.ingestion.fixtures import (
    FIXTURE_COLUMNS,
    synthetic_day_response,
    synthetic_row,
)

NORMAL = date(2026, 1, 15)
SPRING = date(2026, 3, 29)
AUTUMN = date(2026, 10, 25)


@pytest.mark.parametrize(("day", "n"), [(NORMAL, 24), (SPRING, 23), (AUTUMN, 25)])
def test_complete_day_parses_all_intervals(day: date, n: int) -> None:
    parsed = parse_day_response(synthetic_day_response(day), day, FIXTURE_COLUMNS)
    assert len(parsed.rows) == n
    assert parsed.issues == []
    starts = [r.interval.start_utc for r in parsed.rows]
    assert starts == sorted(starts) and len(set(starts)) == n


def test_values_are_exact_decimals_per_zone() -> None:
    parsed = parse_day_response(synthetic_day_response(NORMAL), NORMAL, FIXTURE_COLUMNS)
    row = parsed.rows[0]
    assert row.values[("AL", "price")] == Decimal("51.00")
    assert row.values[("AL", "volume")] == Decimal("100.00")
    assert row.values[("KS", "net_position")] == Decimal("10.00")


def test_rows_for_other_days_are_dropped() -> None:
    rows = [synthetic_row(NORMAL, m, m) for m in range(1, 25)] + [synthetic_row(AUTUMN, 25, 99)]
    parsed = parse_day_response(synthetic_day_response(NORMAL, rows), NORMAL, FIXTURE_COLUMNS)
    assert len(parsed.rows) == 24
    assert any("dropped row dated" in i for i in parsed.issues)


def test_nonexistent_spring_label_rejected_and_missing_reported() -> None:
    rows = [synthetic_row(SPRING, m, m) for m in range(1, 25)]  # includes label 3, which can't exist
    parsed = parse_day_response(synthetic_day_response(SPRING, rows), SPRING, FIXTURE_COLUMNS)
    assert len(parsed.rows) == 23
    assert any("MTU label 3 does not exist" in i for i in parsed.issues)


def test_missing_hour_is_reported_not_invented() -> None:
    rows = [synthetic_row(NORMAL, m, m) for m in range(1, 25) if m != 13]
    parsed = parse_day_response(synthetic_day_response(NORMAL, rows), NORMAL, FIXTURE_COLUMNS)
    assert len(parsed.rows) == 23
    assert "missing MTU labels [13]" in parsed.issues


def test_conflicting_duplicates_are_not_stored() -> None:
    rows = [synthetic_row(NORMAL, m, m) for m in range(1, 25)]
    rows.append(synthetic_row(NORMAL, 5, 500, price="999.00"))
    parsed = parse_day_response(synthetic_day_response(NORMAL, rows), NORMAL, FIXTURE_COLUMNS)
    assert 5 not in {r.mtu for r in parsed.rows}
    assert any("conflicting" in i for i in parsed.issues)


def test_identical_duplicates_collapse() -> None:
    rows = [synthetic_row(NORMAL, m, m) for m in range(1, 25)] + [synthetic_row(NORMAL, 5, 500)]
    parsed = parse_day_response(synthetic_day_response(NORMAL, rows), NORMAL, FIXTURE_COLUMNS)
    assert len(parsed.rows) == 24
    assert any("identical duplicate" in i for i in parsed.issues)


def test_hidden_datetime_column_is_ignored() -> None:
    # The hidden 'datetime' column holds junk at the source ('25 Oct 3026', '01 Jan 1900').
    rows = [synthetic_row(NORMAL, m, m) for m in range(1, 25)]
    rows[12][13] = "15 Jan 3026"
    rows[13][13] = "01 Jan 1900"
    parsed = parse_day_response(synthetic_day_response(NORMAL, rows), NORMAL, FIXTURE_COLUMNS)
    assert len(parsed.rows) == 24 and parsed.issues == []
    assert all(r.notes == () for r in parsed.rows)


def test_schema_change_raises() -> None:
    cols = tuple(c for c in FIXTURE_COLUMNS if c != "almcpmwh")
    with pytest.raises(AlpexSchemaError):
        parse_day_response(synthetic_day_response(NORMAL), NORMAL, cols)
    with pytest.raises(AlpexBadResponse):
        parse_day_response(b"<html>not json</html>", NORMAL, FIXTURE_COLUMNS)
    with pytest.raises(AlpexBadResponse):
        parse_day_response(b"", NORMAL, FIXTURE_COLUMNS)


def test_canonical_rows_are_labeled() -> None:
    parsed = parse_day_response(synthetic_day_response(NORMAL), NORMAL, FIXTURE_COLUMNS)
    vals = to_canonical(parsed, "DAM", raw_payload_id=1, source_name="FIXTURE", is_simulated=True,
                        license_status="SYNTHETIC_TEST_DATA")
    assert len(vals) == 24 * 6
    assert all(v.is_simulated and v.source_name == "FIXTURE" for v in vals)
    assert {v.unit for v in vals if v.quantity == "price"} == {"EUR/MWh"}


def fake_results_page(table_id: int = 89, nonce: str = "abc123") -> str:
    import html as h
    import json

    desc = {"tableWpId": table_id, "dataTableParams": {"columnDefs": [{"name": c} for c in FIXTURE_COLUMNS]}}
    return (f"<input type=\"hidden\" id=\"table_1_desc\" value='{h.escape(json.dumps(desc), quote=False)}'>"
            f'<input type="hidden" id="wdtNonceFrontendEdit_{table_id}" value="{nonce}">')


def test_results_page_parsing_and_request_building() -> None:
    cfgs = parse_results_page(fake_results_page())
    cfg = cfgs[89]
    assert cfg == TableConfig(89, "abc123", FIXTURE_COLUMNS)
    form = build_day_request(cfg, AUTUMN)
    assert form["columns[6][search][value]"] == "25 Oct 2026|25 Oct 2026"
    assert form["wdtNonce"] == "abc123"


def test_results_page_without_tables_raises() -> None:
    with pytest.raises(AlpexSchemaError):
        parse_results_page("<html></html>")
