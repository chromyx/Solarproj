"""Canonical market interval values: validation, revision-safe storage, and source status.

Never overwrite: if a source later reports a different value for the same interval, it is stored
as revision N+1 and the old row stays. "Current" value = highest revision.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from powerdesk.db.models import MarketIntervalValue
from powerdesk.timeutil import Interval, hours_in_day

# ALPEX DAM limits reported for 2026: floor -50 EUR/MWh, cap 900 EUR/MWh. Limits have changed over
# time (the data contains -500 and +4000 EUR/MWh in 2024), so values outside are flagged, not dropped.
PRICE_WARN_RANGE = (Decimal(-50), Decimal(900))
# Values outside this wider range are treated as data errors.
PRICE_BAD_RANGE = (Decimal(-500), Decimal(4000))

UNITS = {"price": "EUR/MWh", "volume": "MWh", "net_position": "MWh"}


@dataclass(frozen=True)
class CanonicalValue:
    interval: Interval
    delivery_day_local: date
    market_zone: str
    product: str
    quantity: str
    value: Decimal
    source_name: str
    source_record_id: str | None
    source_mtu_label: int | None
    is_simulated: bool
    source_license_status: str
    raw_payload_id: int
    published_at_utc: datetime | None = None
    extra_notes: tuple[str, ...] = ()
    forced_status: str | None = None  # e.g. "BAD" when the source makes the interval unknowable

    @property
    def unit(self) -> str:
        return UNITS[self.quantity]


def validate(quantity: str, value: Decimal) -> tuple[str, list[str]]:
    """Return (quality_status, notes) for a single value."""
    if quantity not in UNITS:
        raise ValueError(f"Unknown quantity {quantity!r}")
    notes: list[str] = []
    status = "OK"
    if quantity == "price":
        lo, hi = PRICE_BAD_RANGE
        if not lo <= value <= hi:
            return "BAD", [f"price {value} outside plausible range [{lo}, {hi}]"]
        lo, hi = PRICE_WARN_RANGE
        if not lo <= value <= hi:
            status = "WARN"
            notes.append(f"price {value} outside the [{lo}, {hi}] limits reported for 2026")
    elif quantity == "volume" and value < 0:
        return "BAD", [f"negative volume {value}"]
    return status, notes


@dataclass
class UpsertStats:
    inserted_new: int = 0
    inserted_revision: int = 0
    unchanged: int = 0
    bad: int = 0
    warn: int = 0
    revised_keys: list[str] = field(default_factory=list)


def _key(v: CanonicalValue) -> tuple[str, str, str, str, datetime]:
    return (v.source_name, v.market_zone, v.product, v.quantity, v.interval.start_utc)


def store_values(session: Session, values: Sequence[CanonicalValue]) -> UpsertStats:
    """Insert values, creating a new revision only when the value or quality changed."""
    stats = UpsertStats()
    if not values:
        return stats
    starts = [v.interval.start_utc for v in values]
    sources = {v.source_name for v in values}
    existing_rows = session.scalars(
        select(MarketIntervalValue).where(
            MarketIntervalValue.source_name.in_(sources),
            MarketIntervalValue.delivery_start_utc >= min(starts),
            MarketIntervalValue.delivery_start_utc <= max(starts),
        )
    ).all()
    latest: dict[tuple[str, str, str, str, datetime], MarketIntervalValue] = {}
    for row in existing_rows:
        k = (row.source_name, row.market_zone, row.product, row.quantity,
             row.delivery_start_utc.astimezone(UTC))
        if k not in latest or row.revision_id > latest[k].revision_id:
            latest[k] = row

    now = datetime.now(UTC)
    for v in values:
        status, notes = validate(v.quantity, v.value)
        notes.extend(v.extra_notes)
        if notes and status == "OK":
            status = "WARN"
        if v.forced_status is not None:
            status = v.forced_status
        prev = latest.get(_key(v))
        if (prev is not None and prev.value == v.value and prev.quality_status == status
                and prev.source_mtu_label == v.source_mtu_label):
            stats.unchanged += 1
            continue
        revision = 1 if prev is None else prev.revision_id + 1
        row = MarketIntervalValue(
            delivery_start_utc=v.interval.start_utc,
            delivery_end_utc=v.interval.end_utc,
            delivery_day_local=v.delivery_day_local,
            market_zone=v.market_zone,
            product=v.product,
            quantity=v.quantity,
            value=v.value,
            unit=v.unit,
            source_name=v.source_name,
            source_record_id=v.source_record_id,
            source_mtu_label=v.source_mtu_label,
            published_at_utc=v.published_at_utc,
            ingested_at_utc=now,
            revision_id=revision,
            quality_status=status,
            quality_notes="; ".join(notes) or None,
            is_simulated=v.is_simulated,
            source_license_status=v.source_license_status,
            raw_payload_id=v.raw_payload_id,
        )
        session.add(row)
        latest[_key(v)] = row
        if revision == 1:
            stats.inserted_new += 1
        else:
            stats.inserted_revision += 1
            stats.revised_keys.append(f"{v.market_zone}/{v.product}/{v.quantity}@{v.interval.start_utc.isoformat()}")
        if status == "BAD":
            stats.bad += 1
        elif status == "WARN":
            stats.warn += 1
    session.flush()
    return stats


def current_values_query(source_name: str, market_zone: str, product: str, quantity: str):  # type: ignore[no-untyped-def]
    """SELECT of the latest revision per interval (one row per delivery interval)."""
    m = MarketIntervalValue
    latest_rev = (
        select(m.delivery_start_utc, func.max(m.revision_id).label("rev"))
        .where(m.source_name == source_name, m.market_zone == market_zone,
               m.product == product, m.quantity == quantity)
        .group_by(m.delivery_start_utc)
        .subquery()
    )
    return (
        select(m)
        .join(latest_rev, (m.delivery_start_utc == latest_rev.c.delivery_start_utc)
              & (m.revision_id == latest_rev.c.rev))
        .where(m.source_name == source_name, m.market_zone == market_zone,
               m.product == product, m.quantity == quantity)
        .order_by(m.delivery_start_utc)
    )


@dataclass
class DayCoverage:
    day: date
    expected: int
    received: int
    bad: int

    @property
    def complete(self) -> bool:
        return self.received == self.expected and self.bad == 0


def coverage_by_day(
    session: Session, source_name: str, market_zone: str, product: str, quantity: str,
    start: date, end: date,
) -> list[DayCoverage]:
    m = MarketIntervalValue
    rows = session.execute(
        select(
            m.delivery_day_local,
            func.count(func.distinct(m.delivery_start_utc)),
            func.count().filter(m.quality_status == "BAD"),
        )
        .where(m.source_name == source_name, m.market_zone == market_zone,
               m.product == product, m.quantity == quantity,
               m.delivery_day_local >= start, m.delivery_day_local <= end)
        .group_by(m.delivery_day_local)
    ).all()
    found = {r[0]: (int(r[1]), int(r[2])) for r in rows}
    out: list[DayCoverage] = []
    d = start
    while d <= end:
        received, bad = found.get(d, (0, 0))
        out.append(DayCoverage(d, hours_in_day(d), received, bad))
        d += timedelta(days=1)
    return out


def days(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)
