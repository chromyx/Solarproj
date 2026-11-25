from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from powerdesk.db.session import make_engine, make_session_factory, upgrade_to_head

TEST_DB_ENV = "POWERDESK_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"{TEST_DB_ENV} not set; database tests need PostgreSQL")
    upgrade_to_head(url)
    eng = make_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    # TRUNCATE bypasses the row-level append-only triggers (test cleanup only).
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE market_interval_value, raw_payload RESTART IDENTITY CASCADE"))
    yield make_session_factory(engine)
