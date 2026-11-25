"""End-to-end ingest against a FAKE ALPEX server (httpx MockTransport). No network, synthetic data."""

from datetime import date

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from powerdesk.db.models import MarketIntervalValue, RawPayload
from powerdesk.ingestion import alpex_web
from powerdesk.ingestion.base import PoliteHttp
from powerdesk.ingestion.fixtures import synthetic_day_response
from tests.test_alpex_parse import fake_results_page

pytestmark = pytest.mark.db


def make_handler(calls: list[str], fail_first_post: bool = False, junk_posts: int = 0):  # type: ignore[no-untyped-def]
    state = {"failed": False, "junk": junk_posts}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, text=fake_results_page())
        if fail_first_post and not state["failed"]:
            state["failed"] = True
            return httpx.Response(503)
        if state["junk"]:
            state["junk"] -= 1
            return httpx.Response(200, content=b"")
        form = dict(httpx.QueryParams(request.content.decode()))
        day_s = form["columns[6][search][value]"].split("|")[0]
        from datetime import datetime
        day = datetime.strptime(day_s, "%d %b %Y").date()  # noqa: DTZ007
        return httpx.Response(200, content=synthetic_day_response(day))

    return handler


def test_ingest_range_stores_raw_and_values_then_skips_complete_days(
    session_factory: sessionmaker[Session],
) -> None:
    calls: list[str] = []
    http = PoliteHttp(min_interval_s=0, backoff_base_s=0, sleep=lambda s: None,
                      transport=httpx.MockTransport(make_handler(calls, fail_first_post=True)))
    res = alpex_web.ingest_range(session_factory, date(2026, 10, 24), date(2026, 10, 26), http=http)
    assert [r.rows for r in res] == [24, 25, 24]
    assert all(r.error is None and r.issues == [] for r in res)
    assert calls.count("POST") == 4  # one 503 retried
    with session_factory() as s:
        n = s.scalar(select(func.count()).select_from(MarketIntervalValue)
                     .where(MarketIntervalValue.quantity == "price", MarketIntervalValue.market_zone == "AL"))
        assert n == 73
        assert s.scalar(select(func.count()).select_from(RawPayload)) == 4  # layout + 3 days
        assert s.scalars(select(MarketIntervalValue.source_license_status).distinct()).all() == [
            alpex_web.LICENSE_STATUS]

    calls.clear()
    res2 = alpex_web.ingest_range(session_factory, date(2026, 10, 24), date(2026, 10, 26), http=http)
    assert res2 == [] and calls == []  # nothing re-fetched


def _http(handler) -> PoliteHttp:  # type: ignore[no-untyped-def]
    return PoliteHttp(min_interval_s=0, backoff_base_s=0, sleep=lambda s: None,
                      transport=httpx.MockTransport(handler))


def test_bad_response_is_kept_as_raw_and_retried(session_factory: sessionmaker[Session]) -> None:
    calls: list[str] = []
    res = alpex_web.ingest_range(session_factory, date(2026, 1, 5), date(2026, 1, 5),
                                 http=_http(make_handler(calls, junk_posts=1)))
    assert res[0].error is None and res[0].rows == 24
    with session_factory() as s:
        raws = s.scalars(select(RawPayload).order_by(RawPayload.id)).all()
        assert [r.content == b"" for r in raws] == [False, True, False]  # layout, junk, good


def test_run_stops_after_consecutive_failures(session_factory: sessionmaker[Session]) -> None:
    calls: list[str] = []
    res = alpex_web.ingest_range(session_factory, date(2026, 1, 1), date(2026, 1, 31),
                                 http=_http(make_handler(calls, junk_posts=10_000)),
                                 max_consecutive_failures=2, bad_response_attempts=2)
    assert len(res) == 2 and all(r.error for r in res)
    assert calls.count("POST") == 4
