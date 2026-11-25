"""Hand-worked fixtures for the earnings arithmetic (independently calculated by hand)."""

from decimal import Decimal as D

import pandas as pd
import pytest

from powerdesk.analysis.earnings import align_weather_year, compute_outcome, percentile, to_mwh


def test_three_interval_hand_worked_example() -> None:
    # Hour 1: 2 MWh @ 100 = 200; hour 2: 4 MWh @ 50 = 200; hour 3: 0 MWh @ 150 = 0
    # revenue 400, energy 6, capture 66.67, baseload (100+50+150)/3 = 100, capture rate 0.667
    o = compute_outcome([D(100), D(50), D(150)], [D(2), D(4), D(0)], D("0.11"))
    assert o.revenue_eur == D("400.00")
    assert o.energy_mwh == D(6)
    assert o.capture_eur_mwh == D("66.67")
    assert o.baseload_eur_mwh == D("100.00")
    assert o.capture_rate == D("0.667")
    assert o.variable_fees_eur == D("0.66")  # 6 MWh x 0.11


def test_negative_price_hours_reduce_revenue_and_curtailment_recovers_it() -> None:
    # 3 MWh @ -20 = -60; 5 MWh @ 80 = 400 -> revenue 340; curtailed: 400 on 5 MWh
    o = compute_outcome([D(-20), D(80)], [D(3), D(5)], D(0))
    assert o.revenue_eur == D("340.00")
    assert (o.neg_price_hours_producing, o.neg_price_mwh, o.neg_price_revenue_eur) == (1, D(3), D("-60.00"))
    assert (o.curtailed_energy_mwh, o.curtailed_revenue_eur) == (D(5), D("400.00"))
    assert o.curtailment_gain_eur == D("60.00")


def test_zero_price_is_low_but_not_negative() -> None:
    o = compute_outcome([D(0), D(5), D(40)], [D(1), D(1), D(1)], D(0))
    assert o.neg_price_hours_producing == 0
    assert o.low_price_hours_producing == 2 and o.low_price_mwh == D(2)


def test_input_validation() -> None:
    with pytest.raises(ValueError):
        compute_outcome([D(1)], [D(1), D(2)], D(0))
    with pytest.raises(ValueError):
        compute_outcome([], [], D(0))
    with pytest.raises(ValueError):
        compute_outcome([D(1)], [D(-1)], D(0))


def test_annual_gwh_is_sum_of_interval_mwh_over_1000() -> None:
    hourly = [D("1.234")] * 8760
    o = compute_outcome([D(50)] * 8760, hourly, D(0))
    assert o.energy_mwh / 1000 == D("10.80984")  # GWh


def test_align_weather_year_uses_same_utc_hour_and_handles_feb29() -> None:
    idx = pd.date_range("2023-01-01", "2023-12-31 23:00", freq="h", tz="UTC")
    prod = pd.Series(range(len(idx)), index=idx, dtype=float)
    price_hours = pd.DatetimeIndex(pd.to_datetime(
        ["2024-02-29 11:00", "2024-02-28 11:00", "2025-07-01 00:00"], utc=True))
    got = align_weather_year(price_hours, prod, 2023)
    feb28_11 = (31 + 27) * 24 + 11
    assert got == [to_mwh(feb28_11), to_mwh(feb28_11), to_mwh((181) * 24)]


def test_percentile_decimal() -> None:
    xs = [D(10), D(20), D(30), D(40)]
    assert percentile(xs, 50) == D(25)
    assert percentile(xs, 0) == D(10) and percentile(xs, 100) == D(40)
