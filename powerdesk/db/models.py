"""Database schema: raw payloads (never modified) and canonical market interval values.

Invariants (docs/DATA_CONTRACTS.md):
- Every canonical value points to the raw payload it was parsed from.
- Values are never overwritten: a changed value is stored as a new revision.
- Timestamps are timezone-aware UTC.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RawPayload(Base):
    """Exact bytes received from a source, with request details. Append-only."""

    __tablename__ = "raw_payload"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64))
    request_url: Mapped[str] = mapped_column(Text)
    request_params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fetched_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(128))
    content_sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    license_status: Mapped[str] = mapped_column(String(96))
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_raw_payload_source_fetched", "source_name", "fetched_at_utc"),)


class MarketIntervalValue(Base):
    """One market value (price, volume, net position) for one delivery interval and zone."""

    __tablename__ = "market_interval_value"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    delivery_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivery_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivery_day_local: Mapped[date] = mapped_column(Date)
    market_zone: Mapped[str] = mapped_column(String(8))  # e.g. AL, KS
    product: Mapped[str] = mapped_column(String(16))  # e.g. DAM, CRIDA-1
    quantity: Mapped[str] = mapped_column(String(32))  # price | volume | net_position
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    unit: Mapped[str] = mapped_column(String(16))  # EUR/MWh | MWh
    source_name: Mapped[str] = mapped_column(String(64))
    source_record_id: Mapped[str | None] = mapped_column(String(64))
    source_mtu_label: Mapped[int | None] = mapped_column(Integer)
    published_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision_id: Mapped[int] = mapped_column(Integer)
    quality_status: Mapped[str] = mapped_column(String(8))  # OK | WARN | BAD
    quality_notes: Mapped[str | None] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(Boolean)
    source_license_status: Mapped[str] = mapped_column(String(96))
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw_payload.id"))

    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "market_zone",
            "product",
            "quantity",
            "delivery_start_utc",
            "revision_id",
            name="uq_market_interval_value_key_revision",
        ),
        CheckConstraint("delivery_end_utc > delivery_start_utc", name="ck_positive_duration"),
        CheckConstraint("revision_id >= 1", name="ck_revision_positive"),
        CheckConstraint("quality_status IN ('OK','WARN','BAD')", name="ck_quality_status"),
        Index(
            "ix_miv_lookup",
            "market_zone",
            "product",
            "quantity",
            "delivery_start_utc",
        ),
    )
