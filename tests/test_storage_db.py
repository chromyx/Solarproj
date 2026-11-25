"""Revision-safe storage on PostgreSQL. Uses SYNTHETIC values only."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from powerdesk.canonical import CanonicalValue, coverage_by_day, current_values_query, store_values
from powerdesk.db.models import MarketIntervalValue, RawPayload
from powerdesk.ingestion.base import Fetched, store_raw_payload
from powerdesk.timeutil import day_intervals

pytestmark = pytest.mark.db
DAY = date(2026, 1, 15)


def _raw(s: Session, content: bytes = b"synthetic") -> RawPayload:
    f = Fetched("https://example.invalid/x", {"a": "b"}, 200, "text/plain", content, datetime.now(UTC))
    return store_raw_payload(s, "FIXTURE", f, "SYNTHETIC_TEST_DATA")


def _vals(
    raw_id: int, price: str = "60", day: date = DAY, hours: range | None = None
) -> list[CanonicalValue]:
    ivs = day_intervals(day, 60)
    idx = hours if hours is not None else range(len(ivs))
    return [
        CanonicalValue(ivs[i], day, "AL", "DAM", "price", Decimal(price), "FIXTURE", str(i), i + 1,
                       True, "SYNTHETIC_TEST_DATA", raw_id)
        for i in idx
    ]


def test_same_values_twice_are_not_duplicated(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as s:
        st1 = store_values(s, _vals(_raw(s).id))
    with session_factory.begin() as s:
        st2 = store_values(s, _vals(_raw(s).id))
    assert (st1.inserted_new, st2.inserted_new, st2.unchanged) == (24, 0, 24)
    with session_factory() as s:
        assert s.scalar(select(text("count(*)")).select_from(MarketIntervalValue)) == 24


def test_changed_value_creates_revision_and_keeps_old(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as s:
        store_values(s, _vals(_raw(s).id, "60"))
    with session_factory.begin() as s:
        st = store_values(s, _vals(_raw(s).id, "61.5", hours=range(3, 4)))
    assert st.inserted_revision == 1
    with session_factory() as s:
        hist = s.scalars(select(MarketIntervalValue).where(MarketIntervalValue.source_mtu_label == 4)
                         .order_by(MarketIntervalValue.revision_id)).all()
        assert [(h.revision_id, h.value) for h in hist] == [(1, Decimal("60")), (2, Decimal("61.5"))]
        current = s.scalars(current_values_query("FIXTURE", "AL", "DAM", "price")).all()
        assert len(current) == 24
        assert current[3].value == Decimal("61.5")


def test_rows_are_append_only(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as s:
        store_values(s, _vals(_raw(s).id))
    for stmt in ("UPDATE market_interval_value SET value = 0", "DELETE FROM market_interval_value",
                 "UPDATE raw_payload SET content = 'x'", "DELETE FROM raw_payload"):
        with pytest.raises(DBAPIError, match="append-only"), session_factory.begin() as s:
            s.execute(text(stmt))


def test_raw_payload_preserved_exactly(session_factory: sessionmaker[Session]) -> None:
    body = b'{"exact": "bytes \xc3\xab"}'
    with session_factory.begin() as s:
        rid = _raw(s, body).id
    with session_factory() as s:
        raw = s.get(RawPayload, rid)
        assert raw is not None and raw.content == body
        import hashlib
        assert raw.content_sha256 == hashlib.sha256(body).hexdigest()


def test_out_of_range_prices_flagged(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as s:
        rid = _raw(s).id
        vals = _vals(rid)
        vals[0] = CanonicalValue(**{**vals[0].__dict__, "value": Decimal("950")})
        vals[1] = CanonicalValue(**{**vals[1].__dict__, "value": Decimal("-80")})
        vals[2] = CanonicalValue(**{**vals[2].__dict__, "value": Decimal("99999")})
        st = store_values(s, vals)
    assert (st.warn, st.bad) == (2, 1)
    with session_factory() as s:
        cov = coverage_by_day(s, "FIXTURE", "AL", "DAM", "price", DAY, DAY)
        assert cov[0].received == 24 and cov[0].bad == 1 and not cov[0].complete


def test_coverage_reports_missing_and_dst_expectations(session_factory: sessionmaker[Session]) -> None:
    spring = date(2026, 3, 29)
    with session_factory.begin() as s:
        rid = _raw(s).id
        store_values(s, _vals(rid, day=spring))
        store_values(s, _vals(rid, hours=range(0, 20)))
    with session_factory() as s:
        cov = {c.day: c for c in coverage_by_day(s, "FIXTURE", "AL", "DAM", "price", DAY, spring)}
    assert cov[spring].expected == 23 and cov[spring].complete
    assert cov[DAY].received == 20 and not cov[DAY].complete
    assert cov[date(2026, 2, 1)].received == 0


def test_forced_bad_and_label_change_create_revisions(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as s:
        store_values(s, _vals(_raw(s).id))
    with session_factory.begin() as s:
        rid = _raw(s).id
        bad = [CanonicalValue(**{**v.__dict__, "forced_status": "BAD"}) for v in _vals(rid)]
        st = store_values(s, bad)
    assert (st.inserted_revision, st.bad) == (24, 24)
    with session_factory.begin() as s:
        rid = _raw(s).id
        relabeled = [CanonicalValue(**{**v.__dict__, "source_mtu_label": 99}) for v in _vals(rid)[:1]]
        st = store_values(s, relabeled)
    assert st.inserted_revision == 1
    with session_factory() as s:
        cur = s.scalars(current_values_query("FIXTURE", "AL", "DAM", "price")).all()
        assert cur[0].revision_id == 3 and cur[0].quality_status == "OK" and cur[0].source_mtu_label == 99
        assert all(c.quality_status == "BAD" for c in cur[1:])


def test_monthly_cross_check_uses_all_published_values(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    from powerdesk.analysis.checks import cross_check_passes, monthly_cross_check
    from powerdesk.ingestion import alpex_web

    with session_factory.begin() as s:
        rid = _raw(s).id
        src = alpex_web.SOURCE_NAME
        vals = [CanonicalValue(**{**v.__dict__, "source_name": src}) for v in _vals(rid, "60")]
        vals[0] = CanonicalValue(**{**vals[0].__dict__, "value": Decimal("84"), "forced_status": "BAD"})
        store_values(s, vals)
    ref = tmp_path / "ref.yaml"
    # mean over all 24 published values: (84 + 23*60)/24 = 61.00
    ref.write_text('months:\n  - {month: "2026-01", zone: AL, avg_eur_mwh: 61.00, source: test}\n')
    rows = monthly_cross_check(session_factory, ref)
    assert rows[0]["computed"] == "61.00" and rows[0]["match"] and cross_check_passes(rows)
