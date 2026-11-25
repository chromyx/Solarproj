"""End-to-end earnings report on SYNTHETIC prices and SYNTHETIC clear-sky weather (no network)."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pvlib
import pytest
from sqlalchemy.orm import Session, sessionmaker

from powerdesk.analysis import report
from powerdesk.canonical import CanonicalValue, store_values
from powerdesk.ingestion import alpex_web
from powerdesk.ingestion.base import Fetched, store_raw_payload
from powerdesk.timeutil import day_intervals

pytestmark = pytest.mark.db
REPO = Path(__file__).resolve().parents[1]


def synthetic_pvgis_json(lat: float, lon: float, years: list[int]) -> bytes:
    times = pd.date_range(f"{years[0]}-01-01 00:10", f"{years[-1]}-12-31 23:10", freq="h", tz="UTC")
    loc = pvlib.location.Location(lat, lon)
    cs = loc.get_clearsky(times)
    cosz = np.cos(np.radians(loc.get_solarposition(times)["zenith"])).clip(lower=0)
    rows = [{"time": t.strftime("%Y%m%d:%H%M"), "Gb(i)": float(b), "Gd(i)": float(d), "Gr(i)": 0.0,
             "H_sun": 0.0, "T2m": 20.0, "WS10m": 2.0, "Int": 0.0}
            for t, b, d in zip(times, (cs["dni"] * cosz).to_numpy(), cs["dhi"].to_numpy(), strict=True)]
    return json.dumps({"outputs": {"hourly": rows}}).encode()


def test_earnings_report_end_to_end(session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch,
                                    tmp_path: Path) -> None:
    import os
    monkeypatch.setenv("POWERDESK_DATABASE_URL", os.environ["POWERDESK_TEST_DATABASE_URL"])
    # Synthetic prices: 100 EUR/MWh at night, 40 at 10-15 UTC, one -5 hour per day at 12 UTC.
    with session_factory.begin() as s:
        raw = store_raw_payload(s, alpex_web.SOURCE_NAME, Fetched("https://example.invalid", {}, 200, None,
                                b"synthetic", datetime.now(UTC)), "SYNTHETIC_TEST_DATA")
        vals = []
        d = date(2024, 11, 1)
        while d <= date(2026, 10, 31):
            for i, iv in enumerate(day_intervals(d, 60)):
                h = iv.start_utc.hour
                p = Decimal(-5) if h == 12 else Decimal(40) if 10 <= h <= 15 else Decimal(100)
                vals.append(CanonicalValue(iv, d, "AL", "DAM", "price", p, alpex_web.SOURCE_NAME, None, i + 1,
                                           True, "SYNTHETIC_TEST_DATA", raw.id))
            d += timedelta(days=1)
        store_values(s, vals)

    payload = SimpleNamespace(content=synthetic_pvgis_json(40.996, 19.529, [2022, 2023]),
                              fetched_at_utc=datetime.now(UTC))
    monkeypatch.setattr(report.pvgis, "latest_payload", lambda s, lat, lon: payload)
    monkeypatch.setattr(report, "_pvcalc_check", lambda *a, **k: {
        "E_y_kwh_per_kwp": 1800.0, "H_i_y_kwh_m2": 2400.0, "loss_pct": 13.1})

    data = report.build(REPO / "config/plant.yaml", today=date(2026, 11, 25))
    labels = [w["label"] for w in data["windows"]]
    assert labels == ["Nov 2024 - Oct 2025", "Nov 2025 - Oct 2026"]  # only fully covered periods
    assert data["price_coverage"]["incomplete_days"] == []
    r = next(x for x in data["results"] if x["window"] == labels[-1] and x["scenario_key"] == "fixed|1.2")
    assert r["weather_years"] == 2
    # midday-heavy solar output must capture less than the baseload average in this price shape
    assert Decimal(r["capture_eur_mwh"]["p50"]) < Decimal(r["baseload_eur_mwh"])
    assert int(Decimal(r["neg_price_hours_producing_p50"])) >= 300  # one producing -5 hour per day
    assert Decimal(r["curtailment_gain_eur_p50"]) > 0
    # tracker > fixed energy
    t = next(x for x in data["results"]
             if x["window"] == labels[-1] and x["scenario_key"] == "single_axis|1.2")
    assert Decimal(t["energy_mwh"]["p50"]) > Decimal(r["energy_mwh"]["p50"])

    md = report.render_markdown(data)
    assert "SIMULATED HISTORICAL ESTIMATE" in md and "ILLUSTRATIVE" in md
    assert "## 9. What a trader's offer must beat" in md
