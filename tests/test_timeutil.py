import itertools
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from powerdesk.timeutil import (
    Interval,
    alpex_hourly_mtu_map,
    day_intervals,
    hours_in_day,
    local_midnight_utc,
    resolve_alpex_hourly_labels,
)

SPRING_2026 = date(2026, 3, 29)  # Europe/Tirane: 02:00 -> 03:00
AUTUMN_2026 = date(2026, 10, 25)  # Europe/Tirane: 03:00 -> 02:00
AUTUMN_2025 = date(2025, 10, 26)
NORMAL = date(2026, 1, 15)


def test_local_midnight_winter_and_summer() -> None:
    assert local_midnight_utc(NORMAL) == datetime(2026, 1, 14, 23, 0, tzinfo=UTC)
    assert local_midnight_utc(date(2026, 7, 1)) == datetime(2026, 6, 30, 22, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("day", "hourly", "quarter_hourly"),
    [(NORMAL, 24, 96), (SPRING_2026, 23, 92), (AUTUMN_2026, 25, 100), (AUTUMN_2025, 25, 100)],
)
def test_interval_counts(day: date, hourly: int, quarter_hourly: int) -> None:
    assert len(day_intervals(day, 60)) == hourly
    assert len(day_intervals(day, 15)) == quarter_hourly
    assert hours_in_day(day) == hourly


@pytest.mark.parametrize("day", [NORMAL, SPRING_2026, AUTUMN_2026])
@pytest.mark.parametrize("mtu", [15, 60])
def test_intervals_are_contiguous_and_cover_the_day(day: date, mtu: int) -> None:
    ivs = day_intervals(day, mtu)
    assert ivs[0].start_utc == local_midnight_utc(day)
    assert ivs[-1].end_utc == local_midnight_utc(day + timedelta(days=1))
    for a, b in itertools.pairwise(ivs):
        assert a.end_utc == b.start_utc
        assert a.duration == timedelta(minutes=mtu)


def test_quarter_hour_interval_is_quarter_of_an_hour() -> None:
    iv = day_intervals(NORMAL, 15)[0]
    assert iv.hours == Decimal("0.25")
    # energy for 10 MW over a 15-minute interval is 2.5 MWh, not 10 MWh
    assert Decimal(10) * iv.hours == Decimal("2.5")


def test_unsupported_mtu_rejected() -> None:
    with pytest.raises(ValueError):
        day_intervals(NORMAL, 30)


def test_interval_requires_utc_and_positive_duration() -> None:
    t = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError):
        Interval(t, t)
    with pytest.raises(ValueError):
        Interval(datetime(2026, 1, 1), datetime(2026, 1, 1, 1))  # noqa: DTZ001 - naive on purpose


def test_alpex_labels_normal_day() -> None:
    m = alpex_hourly_mtu_map(NORMAL)
    assert sorted(m) == list(range(1, 25))
    assert m[1].start_utc == datetime(2026, 1, 14, 23, 0, tzinfo=UTC)
    assert m[24].end_utc == datetime(2026, 1, 15, 23, 0, tzinfo=UTC)


def test_alpex_labels_spring_day_skip_label_3() -> None:
    # Observed in ALPEX results for 29 Mar 2026: labels 1,2,4..24
    m = alpex_hourly_mtu_map(SPRING_2026)
    assert sorted(m) == [1, 2, *range(4, 25)]
    assert m[2].end_utc == m[4].start_utc  # 02:00 CET == 03:00 CEST
    assert m[4].start_local.hour == 3


def test_alpex_labels_autumn_day_sequential_25() -> None:
    m = alpex_hourly_mtu_map(AUTUMN_2026)
    assert sorted(m) == list(range(1, 26))
    # labels 3 and 4 both start at 02:00 local, one hour apart in UTC
    assert m[3].start_local.hour == 2 and m[4].start_local.hour == 2
    assert m[4].start_utc - m[3].start_utc == timedelta(hours=1)
    assert m[25].end_utc == local_midnight_utc(date(2026, 10, 26))


def test_resolver_picks_convention_from_published_labels() -> None:
    skip3, why = resolve_alpex_hourly_labels(SPRING_2026, {1, 2, *range(4, 25)})
    assert why is None and skip3[4].start_local.hour == 3
    seq, why = resolve_alpex_hourly_labels(SPRING_2026, set(range(1, 24)))
    assert why is None and seq[3].start_local.hour == 3 and seq[4].start_local.hour == 4
    _, why = resolve_alpex_hourly_labels(SPRING_2026, set(range(1, 25)))
    assert why is not None
    full, why = resolve_alpex_hourly_labels(AUTUMN_2026, set(range(1, 26)))
    assert why is None and len(full) == 25
    _, why = resolve_alpex_hourly_labels(AUTUMN_2026, set(range(1, 25)))
    assert why is not None and "ambiguous" in why
    normal, why = resolve_alpex_hourly_labels(NORMAL, set(range(1, 25)))
    assert why is None and len(normal) == 24
