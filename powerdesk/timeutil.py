"""Delivery-day and market-time-unit (MTU) handling.

Rules (see docs/DATA_CONTRACTS.md):
- Storage is always UTC. Market delivery days are defined in Europe/Tirane local time.
- A delivery day has 23, 24 or 25 hours (DST). Interval length comes from the product's MTU
  (60 or 15 minutes); never assume one hour.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("Europe/Tirane")
SUPPORTED_MTU_MINUTES = (15, 60)


@dataclass(frozen=True, order=True)
class Interval:
    """A half-open delivery interval [start_utc, end_utc) in UTC."""

    start_utc: datetime
    end_utc: datetime

    def __post_init__(self) -> None:
        for ts in (self.start_utc, self.end_utc):
            if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
                raise ValueError(f"Interval timestamps must be timezone-aware UTC, got {ts!r}")
        if self.end_utc <= self.start_utc:
            raise ValueError("Interval must have positive duration")

    @property
    def duration(self) -> timedelta:
        return self.end_utc - self.start_utc

    @property
    def hours(self) -> Decimal:
        """Exact duration in hours as Decimal (0.25 for a 15-minute MTU)."""
        return Decimal(int(self.duration.total_seconds())) / Decimal(3600)

    @property
    def start_local(self) -> datetime:
        return self.start_utc.astimezone(MARKET_TZ)


def local_midnight_utc(day: date) -> datetime:
    """UTC instant of 00:00 Europe/Tirane on ``day`` (never ambiguous: DST switches at 02:00/03:00)."""
    return datetime.combine(day, time(0, 0), tzinfo=MARKET_TZ).astimezone(UTC)


def day_intervals(day: date, mtu_minutes: int = 60) -> list[Interval]:
    """All delivery intervals of a local delivery day, in UTC, in chronological order.

    Gives 23/24/25 intervals for a 60-minute MTU and 92/96/100 for a 15-minute MTU.
    """
    if mtu_minutes not in SUPPORTED_MTU_MINUTES:
        raise ValueError(f"Unsupported MTU {mtu_minutes} min; supported: {SUPPORTED_MTU_MINUTES}")
    start = local_midnight_utc(day)
    end = local_midnight_utc(day + timedelta(days=1))
    step = timedelta(minutes=mtu_minutes)
    out: list[Interval] = []
    t = start
    while t < end:
        out.append(Interval(t, t + step))
        t += step
    if t != end:  # pragma: no cover - cannot happen for 15/60-min MTUs in this zone
        raise AssertionError("Day length is not a multiple of the MTU")
    return out


def hours_in_day(day: date) -> int:
    return len(day_intervals(day, 60))


def alpex_hourly_mtu_map(day: date) -> dict[int, Interval]:
    """Map ALPEX hourly MTU labels to UTC intervals for one delivery day.

    Labeling convention, as observed in ALPEX published results (alpex.al/market-results,
    checked 2026-11-25):
    - Normal 24-hour day: labels 1..24, label = local start hour + 1.
    - 23-hour day (spring DST): labels 1, 2, 4, ..., 24; label 3 (02:00-03:00 local) does not exist.
      Observed on 2026-03-29.
    - 25-hour day (autumn DST): labels 1..25 in chronological order. Observed on 2026-10-25 (25 rows).
      ASSUMPTION (not confirmed by an ALPEX document): labels are sequential, so label 3 is the first
      02:00-03:00 (CEST) and label 4 the repeated 02:00-03:00 (CET).
    """
    intervals = day_intervals(day, 60)
    if len(intervals) == 25:
        return {i + 1: iv for i, iv in enumerate(intervals)}
    return {iv.start_local.hour + 1: iv for iv in intervals}


def resolve_alpex_hourly_labels(day: date, labels: set[int]) -> tuple[dict[int, Interval], str | None]:
    """Choose the MTU-label convention for one day from the labels ALPEX actually published.

    Returns (label -> interval map, ambiguity reason or None). ALPEX has used different conventions
    on DST days (verified in the raw data, 2026-11-25):
    - 23-hour days: 2024-03-31 and 2026-03-29 skip label 3; 2025-03-30 uses 1..23 sequentially.
    - 25-hour days: 2025-10-26 and 2026-10-25 use 1..25; 2023-10-29 and 2024-10-27 were published
      with only labels 1..24, so which hour is which cannot be known -> ambiguous.
    """
    intervals = day_intervals(day, 60)
    sequential = {i + 1: iv for i, iv in enumerate(intervals)}
    if len(intervals) == 24:
        return sequential, None
    if len(intervals) == 23:
        if 3 in labels and 24 not in labels:
            return sequential, None
        skip3 = {iv.start_local.hour + 1: iv for iv in intervals}
        if 3 in labels and 24 in labels:
            return skip3, "23-hour DST day published with both labels 3 and 24; hour mapping ambiguous"
        return skip3, None
    if 25 in labels or not labels:
        return sequential, None
    return sequential, "25-hour DST day published with only 24 labels; hour mapping ambiguous"
