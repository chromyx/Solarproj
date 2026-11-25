"""Physical PV model (pvlib): weather -> exported energy per hourly interval.

Chain: irradiance -> plane-of-array (fixed tilt or single-axis tracker) -> beam incidence-angle
loss -> cell temperature (Faiman) -> DC power (PVWatts) -> lumped DC losses -> inverter
(PVWatts, clips at AC rating) -> AC losses -> grid export limit -> MWh per interval.

All parameters are PROVISIONAL engineering defaults until plant design documents exist.
Output is labeled MODELED, never actual generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
import pvlib

Mounting = Literal["fixed", "single_axis"]


@dataclass(frozen=True)
class PVSpec:
    latitude: float
    longitude: float
    dc_mwp: float
    ac_mw: float
    export_limit_mw: float | None
    mounting: Mounting
    fixed_tilt_deg: float = 30.0
    fixed_azimuth_deg: float = 180.0
    tracker_max_angle_deg: float = 60.0
    tracker_gcr: float = 0.35
    gamma_pdc_per_c: float = -0.0035
    dc_losses_pct: float = 10.0
    inverter_efficiency: float = 0.98
    ac_losses_pct: float = 1.5
    albedo: float = 0.2

    def __post_init__(self) -> None:
        if self.dc_mwp <= 0 or self.ac_mw <= 0:
            raise ValueError("capacities must be positive")
        if self.export_limit_mw is not None and self.export_limit_mw <= 0:
            raise ValueError("export limit must be positive")

    @property
    def label(self) -> str:
        return f"{self.mounting}, DC/AC {self.dc_mwp / self.ac_mw:.2f} ({self.ac_mw:.2f} MW AC)"


def export_power_mw(weather: pd.DataFrame, spec: PVSpec) -> pd.Series:
    """Average export power (MW) for each weather row.

    `weather` needs columns ghi, dhi, beam_horizontal, temp_air, wind_speed and a UTC DatetimeIndex
    of the times at which the sun position is evaluated.
    """
    times = weather.index
    sp = pvlib.solarposition.get_solarposition(times, spec.latitude, spec.longitude)
    zen = sp["apparent_zenith"].to_numpy()
    cosz = np.cos(np.radians(sp["zenith"].to_numpy()))
    # DNI from beam-on-horizontal; ignore beam when the sun is within ~3 degrees of the horizon.
    dni = np.where(cosz > 0.05, weather["beam_horizontal"].to_numpy() / np.maximum(cosz, 0.05), 0.0)
    dni_s = pd.Series(dni, index=times)

    if spec.mounting == "fixed":
        tilt = pd.Series(spec.fixed_tilt_deg, index=times)
        azim = pd.Series(spec.fixed_azimuth_deg, index=times)
    else:
        trk = pvlib.tracking.singleaxis(
            sp["apparent_zenith"], sp["azimuth"], axis_tilt=0, axis_azimuth=180,
            max_angle=spec.tracker_max_angle_deg, backtrack=True, gcr=spec.tracker_gcr,
        )
        tilt = trk["surface_tilt"].fillna(0.0)
        azim = trk["surface_azimuth"].fillna(180.0)

    poa = pvlib.irradiance.get_total_irradiance(
        tilt, azim, sp["apparent_zenith"], sp["azimuth"], dni_s, weather["ghi"], weather["dhi"],
        dni_extra=pvlib.irradiance.get_extra_radiation(times), model="haydavies", albedo=spec.albedo,
    )
    aoi = pvlib.irradiance.aoi(tilt, azim, sp["apparent_zenith"], sp["azimuth"])
    iam = pvlib.iam.ashrae(aoi)
    effective = (poa["poa_direct"].fillna(0.0) * iam.fillna(0.0)
                 + poa["poa_diffuse"].fillna(0.0)).clip(lower=0.0)
    effective[zen >= 90] = 0.0

    temp_cell = pvlib.temperature.faiman(effective, weather["temp_air"], weather["wind_speed"])
    pdc0_w = spec.dc_mwp * 1e6
    pdc = pvlib.pvsystem.pvwatts_dc(effective, temp_cell, pdc0_w, spec.gamma_pdc_per_c)
    pdc = pdc.clip(lower=0.0) * (1.0 - spec.dc_losses_pct / 100.0)

    pac0_w = spec.ac_mw * 1e6
    pac = pvlib.inverter.pvwatts(pdc, pdc0=pac0_w / spec.inverter_efficiency,
                                 eta_inv_nom=spec.inverter_efficiency)
    pac = pac.clip(lower=0.0, upper=pac0_w)
    export_w = pac * (1.0 - spec.ac_losses_pct / 100.0)
    if spec.export_limit_mw is not None:
        export_w = export_w.clip(upper=spec.export_limit_mw * 1e6)
    return (export_w / 1e6).rename("export_mw")


def hourly_export_mwh(weather: pd.DataFrame, spec: PVSpec) -> pd.Series:
    """Exported MWh per hourly interval, indexed by interval start (UTC).

    Each weather row is an hourly average, so MWh = average MW x 1 h.
    """
    mw = export_power_mw(weather, spec)
    starts = pd.DatetimeIndex(weather["interval_start_utc"])
    return pd.Series(mw.to_numpy() * 1.0, index=starts, name="export_mwh")
