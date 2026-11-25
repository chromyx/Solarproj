from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from powerdesk.settings import database_url

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def upgrade_to_head(url: str | None = None) -> None:
    """Apply all Alembic migrations to the database."""
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url or database_url())
    command.upgrade(cfg, "head")
