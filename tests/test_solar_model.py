"""Physical plausibility of the PV model on SYNTHETIC clear-sky weather (no external data)."""

import pandas as pd
import pvlib
import pytest

from powerdesk.solar.model import PVSpec, export_power_mw, hourly_export_mwh

LAT, LON = 40.996, 19.529


def clear_sky_weather(day: str = "2024-06-21", temp: float = 25.0, scale: float = 1.0) -> pd.DataFrame:
    times = pd.date_range(f"{day} 00:30", periods=24, freq="h", tz="UTC")
    loc = pvlib.location.Location(LAT, LON)
    cs = loc.get_clearsky(times)
    sp = loc.get_solarposition(times)
    import numpy as np
    beam_h = cs["dni"] * np.cos(np.radians(sp["zenith"])).clip(lower=0)
    w = pd.DataFrame({"beam_horizontal": beam_h * scale, "dhi": cs["dhi"] * scale,
                      "temp_air": temp, "wind_speed": 2.0}, index=times)
    w["ghi"] = w["beam_horizontal"] + w["dhi"]
    w["interval_start_utc"] = w.index.floor("h")
    return w


def spec(**kw: object) -> PVSpec:
    base: dict[str, object] = {"latitude": LAT, "longitude": LON, "dc_mwp": 15.5, "ac_mw": 15.5,
                               "export_limit_mw": None, "mounting": "fixed"}
    base.update(kw)
    return PVSpec(**base)  # type: ignore[arg-type]


def test_zero_at_night() -> None:
    p = export_power_mw(clear_sky_weather(), spec())
    night = p[(p.index.hour < 3) | (p.index.hour > 19)]
    assert (night == 0).all()


@pytest.mark.parametrize("mounting", ["fixed", "single_axis"])
def test_clipping_at_ac_rating_and_export_limit(mounting: str) -> None:
    w = clear_sky_weather(temp=5.0, scale=1.1)
    small_inverter = export_power_mw(w, spec(ac_mw=8.0, mounting=mounting))
    assert small_inverter.max() <= 8.0 * (1 - 0.015) + 1e-9
    assert (small_inverter > 7.8).sum() >= 3  # clipping plateau around midday
    limited = export_power_mw(w, spec(export_limit_mw=6.0, mounting=mounting))
    assert limited.max() == pytest.approx(6.0)


def test_never_exceeds_dc_nameplate_and_is_plausible() -> None:
    p = export_power_mw(clear_sky_weather(), spec())
    assert 0 < p.max() < 15.5
    # clear June day at 41N, fixed 30 deg south: roughly 6-8 equivalent full-load hours
    assert 6 * 15.5 < p.sum() < 8.5 * 15.5


def test_tracker_produces_more_than_fixed_on_clear_summer_day() -> None:
    w = clear_sky_weather()
    assert export_power_mw(w, spec(mounting="single_axis")).sum() > export_power_mw(w, spec()).sum()


def test_hourly_mwh_equals_average_mw_times_one_hour() -> None:
    w = clear_sky_weather()
    mwh = hourly_export_mwh(w, spec())
    mw = export_power_mw(w, spec())
    assert list(mwh.to_numpy()) == list(mw.to_numpy())
    assert mwh.index[0].minute == 0


def test_invalid_spec_rejected() -> None:
    with pytest.raises(ValueError):
        spec(ac_mw=0)
    with pytest.raises(ValueError):
        spec(export_limit_mw=-1)
