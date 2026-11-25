"""PVGIS (EU Joint Research Centre) hourly irradiance and weather history.

Source: https://re.jrc.ec.europa.eu/api/v5_3/seriescalc (no key). Radiation: PVGIS-SARAH3
(satellite), temperature/wind: ERA5. Values are HOURLY AVERAGES; timestamps are UTC with a
minute offset (e.g. 12:10). Terms: free use if the source is acknowledged
("PVGIS (c) European Communities, 2001-2026"); commercial use is not explicitly addressed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from powerdesk.db.models import RawPayload
from powerdesk.ingestion.base import PoliteHttp, store_raw_payload

SOURCE_NAME = "PVGIS"
LICENSE_STATUS = "PVGIS_JRC_FREE_USE_WITH_ATTRIBUTION"
ATTRIBUTION = "PVGIS (c) European Communities, 2001-2026 (radiation PVGIS-SARAH3, meteo ERA5)"
API = "https://re.jrc.ec.europa.eu/api/v5_3/seriescalc"
FIRST_YEAR, LAST_YEAR = 2005, 2023


def request_params(lat: float, lon: float) -> dict[str, str]:
    """Horizontal-plane components (angle=0) so we can do our own transposition for any mounting."""
    return {
        "lat": f"{lat:.4f}", "lon": f"{lon:.4f}",
        "startyear": str(FIRST_YEAR), "endyear": str(LAST_YEAR),
        "outputformat": "json", "components": "1", "angle": "0", "aspect": "0",
        "usehorizon": "1", "raddatabase": "PVGIS-SARAH3",
    }


def fetch_and_store(session: Session, http: PoliteHttp, lat: float, lon: float) -> RawPayload:
    params = request_params(lat, lon)
    url = API + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    fetched = http.request("GET", url)
    return store_raw_payload(session, SOURCE_NAME, fetched, LICENSE_STATUS,
                             note=ATTRIBUTION, params_for_record=params)


def latest_payload(session: Session, lat: float, lon: float) -> RawPayload | None:
    params = request_params(lat, lon)
    return session.scalars(
        select(RawPayload)
        .where(RawPayload.source_name == SOURCE_NAME, RawPayload.request_params == params)
        .order_by(RawPayload.fetched_at_utc.desc())
        .limit(1)
    ).first()


def parse_hourly(content: bytes) -> pd.DataFrame:
    """Return a UTC-indexed frame: ghi, dhi, beam_horizontal (W/m2), temp_air (C), wind_speed (m/s).

    The index is the PVGIS timestamp (e.g. 12:10 UTC). `interval_start_utc` is the hour it
    averages over, taken as [hh:00, hh+1:00) UTC.
    """
    hourly = json.loads(content)["outputs"]["hourly"]
    df = pd.DataFrame(hourly)
    times = pd.to_datetime(df["time"], format="%Y%m%d:%H%M", utc=True)
    out = pd.DataFrame(
        {
            "beam_horizontal": df["Gb(i)"].astype(float).to_numpy(),
            "dhi": df["Gd(i)"].astype(float).to_numpy(),
            "temp_air": df["T2m"].astype(float).to_numpy(),
            "wind_speed": df["WS10m"].astype(float).to_numpy(),
        },
        index=pd.DatetimeIndex(times, name="pvgis_time_utc"),
    )
    out["ghi"] = out["beam_horizontal"] + out["dhi"]
    out["interval_start_utc"] = out.index.floor("h")
    if out["interval_start_utc"].duplicated().any():
        raise ValueError("PVGIS series has duplicate hours")
    return out


def fetched_at(payload: RawPayload) -> datetime:
    return payload.fetched_at_utc.astimezone(UTC)
