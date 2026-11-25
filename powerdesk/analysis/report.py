"""Generate the 'what would the plant have earned on ALPEX' report (Markdown + JSON).

Labels used in the report:
  ACTUAL              ALPEX published day-ahead prices (Albania zone)
  MODELED-PROVISIONAL production from the pvlib model with provisional plant parameters
  SIMULATED-HISTORICAL revenue = modeled production x actual prices (not realized revenue)
  ILLUSTRATIVE        sensitivity inputs chosen for the decision table, not facts
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from powerdesk.analysis.earnings import (
    CENT,
    Outcome,
    Window,
    align_weather_year,
    compute_outcome,
    percentile,
    window_prices,
)
from powerdesk.canonical import coverage_by_day, current_values_query
from powerdesk.config import PlantConfig, load_plant_config
from powerdesk.db.session import make_engine, make_session_factory
from powerdesk.ingestion import alpex_web
from powerdesk.ingestion.base import PoliteHttp, store_raw_payload
from powerdesk.solar import pvgis
from powerdesk.solar.model import PVSpec, hourly_export_mwh

REPO = Path(__file__).resolve().parents[2]
FEES_PATH = REPO / "data/reference/alpex_fees.yaml"
MONTHLY_REF_PATH = REPO / "data/reference/alpex_monthly_reported.yaml"
PVCALC_API = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"

# Illustrative sensitivity inputs for the decision table (NOT facts; replace with real quotes).
ILLUSTRATIVE_OTHER_COSTS_EUR_MWH = (Decimal(2), Decimal(5), Decimal(8))
ILLUSTRATIVE_STAFF_IT_EUR_YR = (Decimal(0), Decimal(30000), Decimal(60000))


@dataclass(frozen=True)
class Scenario:
    mounting: str
    dc_ac_ratio: float

    @property
    def key(self) -> str:
        return f"{self.mounting}|{self.dc_ac_ratio:.1f}"

    @property
    def label(self) -> str:
        m = "fixed tilt 30 deg south" if self.mounting == "fixed" else "single-axis tracker"
        return f"{m}, DC/AC {self.dc_ac_ratio:.1f}"


def _windows(last_full_month_end: date) -> list[Window]:
    out = []
    for k in range(3):
        end_year = last_full_month_end.year - k
        end = last_full_month_end.replace(year=end_year)
        start = date(end_year - 1, end.month, 1)
        start = date(start.year + (start.month // 12), start.month % 12 + 1, 1)
        out.append(Window(f"{start:%b %Y} - {end:%b %Y}", start, end))
    return list(reversed(out))


def _last_full_month_end(last_day: date) -> date:
    nxt = date(last_day.year + (last_day.month // 12), last_day.month % 12 + 1, 1)
    if (nxt - last_day).days == 1:
        return last_day
    first = date(last_day.year, last_day.month, 1)
    return first.fromordinal(first.toordinal() - 1)


def load_prices(session_factory: Any) -> pd.Series:
    with session_factory() as s:
        rows = s.scalars(current_values_query(alpex_web.SOURCE_NAME, "AL", "DAM", "price")).all()
    if not rows:
        raise RuntimeError("No ALPEX AL DAM prices in the database; run `powerdesk ingest alpex` first")
    idx = pd.DatetimeIndex([r.delivery_start_utc for r in rows]).tz_convert("UTC")
    return pd.Series([r.value for r in rows], index=idx, dtype=object)


def _pvcalc_check(session_factory: Any, http: PoliteHttp, lat: float, lon: float,
                  loss_pct: float) -> dict[str, Any]:
    params = {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}", "peakpower": "1", "loss": f"{loss_pct:.1f}",
              "angle": "30", "aspect": "0", "mountingplace": "free", "pvtechchoice": "crystSi",
              "usehorizon": "1", "raddatabase": "PVGIS-SARAH3", "outputformat": "json"}
    url = PVCALC_API + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    fetched = http.request("GET", url)
    with session_factory.begin() as s:
        store_raw_payload(s, "PVGIS_PVCALC", fetched, pvgis.LICENSE_STATUS, note=pvgis.ATTRIBUTION,
                          params_for_record=params)
    totals = json.loads(fetched.content)["outputs"]["totals"]["fixed"]
    return {"E_y_kwh_per_kwp": totals["E_y"], "H_i_y_kwh_m2": totals["H(i)_y"], "loss_pct": loss_pct}


def _fmt(d: Decimal | float, nd: int = 0) -> str:
    return f"{float(d):,.{nd}f}"


def build(plant_path: Path, today: date | None = None) -> dict[str, Any]:
    cfg: PlantConfig = load_plant_config(plant_path)
    md = cfg.model_defaults
    lat, lon, dc = cfg.num("latitude"), cfg.num("longitude"), cfg.num("capacity_dc_mwp")
    if lat is None or lon is None or dc is None:
        raise RuntimeError("latitude, longitude and capacity_dc_mwp are needed (provisional is fine)")
    ac_known = cfg.num("capacity_ac_mw")
    export_limit = cfg.num("grid_export_limit_mw")
    fees = yaml.safe_load(FEES_PATH.read_text(encoding="utf-8"))
    var_fee = Decimal(str(fees["minimum_own_dam_membership"]["per_mwh"]))
    fixed_fee = Decimal(str(fees["minimum_own_dam_membership"]["annual"]))

    sf = make_session_factory(make_engine())
    prices = load_prices(sf)
    first_day = prices.index.min().tz_convert("Europe/Tirane").date()
    last_day = prices.index.max().tz_convert("Europe/Tirane").date()
    windows = _windows(_last_full_month_end(last_day))

    with sf() as s:
        cov = coverage_by_day(s, alpex_web.SOURCE_NAME, "AL", "DAM", "price", first_day, last_day)
    coverage = {
        "first_day": str(first_day), "last_day": str(last_day), "days": len(cov),
        "hours_expected": sum(c.expected for c in cov), "hours_received": sum(c.received for c in cov),
        "incomplete_days": [str(c.day) for c in cov if not c.complete],
    }

    http = PoliteHttp(min_interval_s=1.0)
    try:
        with sf() as s:
            payload = pvgis.latest_payload(s, lat, lon)
        if payload is None:
            with sf.begin() as s:
                payload = pvgis.fetch_and_store(s, http, lat, lon)
        weather = pvgis.parse_hourly(payload.content)
        pv_fetched = payload.fetched_at_utc
        total_loss = 100 * (1 - (1 - md.dc_losses_pct / 100) * md.inverter_efficiency
                            * (1 - md.ac_losses_pct / 100))
        pvcalc = _pvcalc_check(sf, http, lat, lon, round(total_loss, 1))
    finally:
        http.close()

    scenarios = [Scenario(m, r) for m in md.mounting_scenarios for r in md.dc_ac_ratio_scenarios]
    if ac_known is not None:
        scenarios = [Scenario(m, round(dc / ac_known, 2)) for m in md.mounting_scenarios]
    weather_years = sorted(set(weather.index.year))

    production: dict[str, pd.Series] = {}
    for sc in scenarios:
        spec = PVSpec(lat, lon, dc, dc / sc.dc_ac_ratio, export_limit, sc.mounting,  # type: ignore[arg-type]
                      md.fixed_tilt_deg, md.fixed_azimuth_deg, md.tracker_max_angle_deg, md.tracker_gcr,
                      md.gamma_pdc_per_c, md.dc_losses_pct, md.inverter_efficiency, md.ac_losses_pct)
        production[sc.key] = hourly_export_mwh(weather, spec)

    fixed_ref = production[Scenario("fixed", 1.0).key] if Scenario("fixed", 1.0).key in production \
        else production[scenarios[0].key]
    model_yield = float(fixed_ref.groupby(fixed_ref.index.year).sum().mean()) / dc
    yield_check = {
        "model_kwh_per_kwp": round(model_yield, 1),
        "pvgis_kwh_per_kwp": pvcalc["E_y_kwh_per_kwp"],
        "pvgis_poa_kwh_m2": pvcalc["H_i_y_kwh_m2"],
        "loss_pct_used_in_pvgis": pvcalc["loss_pct"],
        "diff_pct": round(100 * (model_yield / pvcalc["E_y_kwh_per_kwp"] - 1), 1),
    }
    yield_check["pass"] = abs(yield_check["diff_pct"]) <= 10.0

    # Only analyse 12-month periods with (near) complete price data; never fill gaps.
    usable = []
    for w in windows:
        expected = sum(c.expected for c in cov if w.first_day <= c.day <= w.last_day)
        have = len(window_prices(prices, w))
        if w.first_day >= first_day and expected and have >= 0.99 * expected:
            usable.append(w)
    if not usable:
        raise RuntimeError("No 12-month period with >= 99% price coverage yet")
    windows = usable

    results: list[dict[str, Any]] = []
    monthly_latest: dict[str, dict[str, Decimal]] = {}
    for w in windows:
        wp = window_prices(prices, w)
        expected = sum(c.expected for c in cov if w.first_day <= c.day <= w.last_day)
        p_list = list(wp.to_numpy())
        for sc in scenarios:
            outs: list[Outcome] = []
            for wy in weather_years:
                e = align_weather_year(wp.index, production[sc.key], wy)
                outs.append(compute_outcome(p_list, e, var_fee))
            results.append(_summarize(w, sc, outs, expected))
        if w is windows[-1]:
            monthly_latest = _monthly(wp, production, scenarios, weather_years)

    monthly_ref = yaml.safe_load(MONTHLY_REF_PATH.read_text(encoding="utf-8"))["months"]
    monthly_check = []
    for ref in monthly_ref:
        if ref["zone"] != "AL":
            continue
        y, m = map(int, ref["month"].split("-"))
        local = prices.index.tz_convert("Europe/Tirane")
        sel = prices[(local.year == y) & (local.month == m)]
        if len(sel):
            avg = (sum(sel.to_numpy(), Decimal(0)) / len(sel)).quantize(CENT)
            monthly_check.append({"month": ref["month"], "computed": str(avg), "reported": ref["avg_eur_mwh"],
                                  "hours": len(sel),
                                  "match": abs(avg - Decimal(str(ref["avg_eur_mwh"]))) <= CENT})

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "report_date": str(today or datetime.now(UTC).date()),
        "plant": {k: {"value": v.value, "status": v.status, "source": v.source} for k, v in cfg.plant},
        "model_defaults": cfg.model_defaults.model_dump(),
        "price_coverage": coverage,
        "monthly_check": monthly_check,
        "pvgis": {"fetched_at_utc": pv_fetched.isoformat(timespec="seconds"),
                  "years": [weather_years[0], weather_years[-1]], "attribution": pvgis.ATTRIBUTION},
        "yield_check": yield_check,
        "fees": {"per_mwh": str(var_fee), "annual_fixed": str(fixed_fee),
                 "one_off": fees["minimum_own_dam_membership"]["one_off"], "source_accessed": fees["accessed"]},
        "windows": [asdict(w) | {"first_day": str(w.first_day), "last_day": str(w.last_day)} for w in windows],
        "results": results,
        "monthly_latest_window": {k: {kk: str(vv) for kk, vv in v.items()} for k, v in monthly_latest.items()},
    }


def _summarize(w: Window, sc: Scenario, outs: list[Outcome], expected_hours: int) -> dict[str, Any]:
    def pct(attr: str, q: float) -> Decimal:
        vals = [getattr(o, attr) for o in outs]
        return percentile(vals, q)

    # P90 = exceeded in 90% of weather years = 10th percentile (and P10 = 90th percentile).
    return {
        "window": w.label, "scenario": sc.label, "scenario_key": sc.key,
        "hours_priced": outs[0].hours, "hours_expected": expected_hours,
        "weather_years": len(outs),
        "baseload_eur_mwh": str(outs[0].baseload_eur_mwh),
        "energy_mwh": {"p90": str(pct("energy_mwh", 10).quantize(Decimal(1))),
                       "p50": str(pct("energy_mwh", 50).quantize(Decimal(1))),
                       "p10": str(pct("energy_mwh", 90).quantize(Decimal(1)))},
        "revenue_eur": {"p90": str(pct("revenue_eur", 10).quantize(Decimal(1))),
                        "p50": str(pct("revenue_eur", 50).quantize(Decimal(1))),
                        "p10": str(pct("revenue_eur", 90).quantize(Decimal(1)))},
        "capture_eur_mwh": {"p90": str(pct("capture_eur_mwh", 10).quantize(CENT)),
                            "p50": str(pct("capture_eur_mwh", 50).quantize(CENT)),
                            "p10": str(pct("capture_eur_mwh", 90).quantize(CENT))},
        "capture_rate_p50": str(pct("capture_rate", 50).quantize(Decimal("0.001"))),
        "neg_price_hours_producing_p50": str(pct("neg_price_hours_producing", 50)),
        "neg_price_mwh_p50": str(pct("neg_price_mwh", 50).quantize(Decimal(1))),
        "neg_price_revenue_eur_p50": str(pct("neg_price_revenue_eur", 50).quantize(Decimal(1))),
        "low_price_hours_producing_p50": str(pct("low_price_hours_producing", 50)),
        "low_price_mwh_p50": str(pct("low_price_mwh", 50).quantize(Decimal(1))),
        "curtailment_gain_eur_p50": str(pct("curtailment_gain_eur", 50).quantize(Decimal(1))),
        "variable_fees_eur_p50": str(pct("variable_fees_eur", 50).quantize(Decimal(1))),
    }


def _monthly(wp: pd.Series, production: dict[str, pd.Series], scenarios: list[Scenario],
             weather_years: list[int]) -> dict[str, dict[str, Decimal]]:
    """P50 capture price per month for each scenario in the latest window."""
    local = wp.index.tz_convert("Europe/Tirane")
    out: dict[str, dict[str, Decimal]] = {}
    months = sorted(set(zip(local.year, local.month, strict=True)))
    for sc in scenarios:
        per_month: dict[str, Decimal] = {}
        for y, m in months:
            sel = wp[(local.year == y) & (local.month == m)]
            caps = []
            for wy in weather_years:
                e = align_weather_year(sel.index, production[sc.key], wy)
                o = compute_outcome(list(sel.to_numpy()), e, Decimal(0))
                caps.append(o.capture_eur_mwh)
            base = (sum(sel.to_numpy(), Decimal(0)) / len(sel)).quantize(CENT)
            per_month[f"{y}-{m:02d}"] = percentile(caps, 50).quantize(CENT)
            per_month[f"{y}-{m:02d}|baseload"] = base
        out[sc.key] = per_month
    return out


def decision_table(r: dict[str, Any], fixed_fee: Decimal, var_fee: Decimal) -> list[dict[str, str]]:
    """Net EUR/MWh kept by an own desk under illustrative cost assumptions (P50 weather)."""
    energy = Decimal(r["energy_mwh"]["p50"])
    capture = Decimal(r["capture_eur_mwh"]["p50"])
    rows = []
    for staff in ILLUSTRATIVE_STAFF_IT_EUR_YR:
        for other in ILLUSTRATIVE_OTHER_COSTS_EUR_MWH:
            cost_mwh = var_fee + (fixed_fee + staff) / energy + other
            net = capture - cost_mwh
            rows.append({"staff_it_eur_yr": _fmt(staff), "other_costs_eur_mwh": _fmt(other),
                         "all_costs_eur_mwh": _fmt(cost_mwh, 2), "net_eur_mwh": _fmt(net, 2),
                         "net_pct_of_capture": _fmt(100 * net / capture, 1)})
    return rows


def render_markdown(d: dict[str, Any]) -> str:
    fees = d["fees"]
    fixed_fee, var_fee = Decimal(fees["annual_fixed"]), Decimal(fees["per_mwh"])
    latest = d["windows"][-1]["label"]
    res = d["results"]
    central = next(r for r in res if r["window"] == latest and r["scenario_key"] == "fixed|1.2")
    tracker = next(r for r in res if r["window"] == latest and r["scenario_key"] == "single_axis|1.2")
    L: list[str] = []
    a = L.append
    a("# ONE SOLAR (Divjake) - what would the plant have earned on ALPEX?")
    a("")
    a(f"Report date {d['report_date']} - generated {d['generated_at_utc']} by `powerdesk report earnings`.")
    a("")
    a("> **SIMULATED HISTORICAL ESTIMATE - not realized revenue.** Production is MODELED with "
      "PROVISIONAL plant parameters (location, DC size and design are not confirmed). Prices are "
      "ACTUAL ALPEX day-ahead results for the Albania zone, collected from the public ALPEX website "
      "(all rights reserved; internal use only). Costs not listed as known are NOT included.")
    a("")
    a("## 1. Bottom line")
    a("")
    a(f"For the most recent 12 months ({latest}), with median (P50) weather:")
    a("")
    for r, name in ((central, "Fixed tilt, DC/AC 1.2"), (tracker, "Single-axis tracker, DC/AC 1.2")):
        a(f"- **{name}:** about **{_fmt(Decimal(r['energy_mwh']['p50']) / 1000, 1)} GWh**, "
          f"gross ALPEX sales value **EUR {_fmt(Decimal(r['revenue_eur']['p50']))}**, "
          f"capture price **{r['capture_eur_mwh']['p50']} EUR/MWh** vs. "
          f"{r['baseload_eur_mwh']} EUR/MWh average price (capture rate "
          f"{_fmt(100 * Decimal(r['capture_rate_p50']), 1)}%).")
    a("")
    a(f"- Known ALPEX membership costs for selling your own output: EUR {_fmt(fixed_fee)}/yr fixed "
      f"+ EUR {var_fee}/MWh + EUR {_fmt(Decimal(fees['one_off']))} one-off (excl. VAT). That is about "
      f"EUR {_fmt(var_fee + fixed_fee / Decimal(central['energy_mwh']['p50']), 2)}/MWh for this plant.")
    a("- Prices moved a lot between years (see section 5), so one year is not a forecast.")
    a("")
    a("## 2. What is known and what is assumed")
    a("")
    a("| Parameter | Value | Status | Source |")
    a("|---|---|---|---|")
    for k, v in d["plant"].items():
        a(f"| {k} | {v['value'] if v['value'] is not None else '-'} | {v['status']} | {v['source']} |")
    a("")
    md = d["model_defaults"]
    a(f"Engineering defaults (PROVISIONAL): DC/AC scenarios {md['dc_ac_ratio_scenarios']}, mounting "
      f"{md['mounting_scenarios']}, fixed tilt {md['fixed_tilt_deg']} deg, tracker +/-{md['tracker_max_angle_deg']} "
      f"deg (GCR {md['tracker_gcr']}), temperature coefficient {md['gamma_pdc_per_c']}/C, DC losses "
      f"{md['dc_losses_pct']}%, inverter efficiency {md['inverter_efficiency']}, AC losses {md['ac_losses_pct']}%. "
      "Grid export limit unknown: not applied. Battery: not modeled (size unknown).")
    a("")
    a("## 3. Price data (ACTUAL) and cross-check")
    a("")
    c = d["price_coverage"]
    a(f"ALPEX day-ahead, Albania zone, delivery days {c['first_day']} to {c['last_day']}: "
      f"{c['hours_received']:,} of {c['hours_expected']:,} hourly prices "
      f"({len(c['incomplete_days'])} incomplete days{': ' + ', '.join(c['incomplete_days'][:10]) if c['incomplete_days'] else ''}).")
    a("")
    a("Independent check: our monthly averages vs. the averages ALPEX publishes in its monthly reports.")
    a("")
    a("| Month | Computed from hourly data | ALPEX monthly report | Match |")
    a("|---|---|---|---|")
    for m in d["monthly_check"]:
        a(f"| {m['month']} | {m['computed']} | {m['reported']} | {'yes' if m['match'] else 'NO'} |")
    a("")
    a("## 4. Production model (MODELED-PROVISIONAL) and cross-check")
    a("")
    y = d["yield_check"]
    a(f"pvlib model on PVGIS hourly weather {d['pvgis']['years'][0]}-{d['pvgis']['years'][1]} "
      f"({d['pvgis']['attribution']}). Independent check against PVGIS's own calculator for the same "
      f"fixed system and comparable losses ({y['loss_pct_used_in_pvgis']}%): model "
      f"**{y['model_kwh_per_kwp']} kWh/kWp/yr** vs PVGIS **{y['pvgis_kwh_per_kwp']}** "
      f"({y['diff_pct']:+}%, {'within' if y['pass'] else 'OUTSIDE'} the +/-10% gate).")
    a("")
    a("## 5. Results by year and design (SIMULATED-HISTORICAL)")
    a("")
    a("Each row applies all 19 weather years to that period's actual hourly prices. "
      "P50 = median; P90 = level exceeded in 90% of weather years (a low year); P10 = a high year.")
    a("")
    a("| Period | Design | Energy GWh P50 (P90-P10) | Capture EUR/MWh P50 | Avg price | Capture rate | Gross value EUR P50 (P90-P10) |")
    a("|---|---|---|---|---|---|---|")
    for r in res:
        e, v = r["energy_mwh"], r["revenue_eur"]
        a(f"| {r['window']} | {r['scenario']} | {_fmt(Decimal(e['p50']) / 1000, 2)} "
          f"({_fmt(Decimal(e['p90']) / 1000, 2)}-{_fmt(Decimal(e['p10']) / 1000, 2)}) | "
          f"{r['capture_eur_mwh']['p50']} | {r['baseload_eur_mwh']} | "
          f"{_fmt(100 * Decimal(r['capture_rate_p50']), 1)}% | {_fmt(Decimal(v['p50']))} "
          f"({_fmt(Decimal(v['p90']))}-{_fmt(Decimal(v['p10']))}) |")
    a("")
    a("## 6. Low and negative price hours")
    a("")
    a("ALPEX's price floor was 0 EUR/MWh until it was lowered to -50 EUR/MWh (reported July 2026), "
      "so negative prices can only appear recently.")
    a("")
    a("| Period | Design | Producing hours < 10 EUR/MWh | MWh in them | Producing hours < 0 | Value lost in them EUR | Gain if curtailed below 0 EUR |")
    a("|---|---|---|---|---|---|---|")
    for r in res:
        if not r["scenario_key"].endswith("1.2"):
            continue
        a(f"| {r['window']} | {r['scenario']} | {_fmt(Decimal(r['low_price_hours_producing_p50']))} | "
          f"{_fmt(Decimal(r['low_price_mwh_p50']))} | {_fmt(Decimal(r['neg_price_hours_producing_p50']))} | "
          f"{_fmt(Decimal(r['neg_price_revenue_eur_p50']))} | {_fmt(Decimal(r['curtailment_gain_eur_p50']))} |")
    a("")
    a(f"## 7. Month by month, {latest} (P50 weather, fixed tilt DC/AC 1.2)")
    a("")
    a("| Month | Avg price EUR/MWh | Solar capture EUR/MWh | Capture rate |")
    a("|---|---|---|---|")
    mon = d["monthly_latest_window"]["fixed|1.2"]
    for k in sorted(x for x in mon if "|" not in x):
        base, cap = Decimal(mon[k + "|baseload"]), Decimal(mon[k])
        a(f"| {k} | {base} | {cap} | {_fmt(100 * cap / base, 1)}% |")
    a("")
    a("## 8. Costs")
    a("")
    a(f"Known (ALPEX fee schedule v6, accessed {fees['source_accessed']}, excl. VAT): EUR {_fmt(fixed_fee)}/yr "
      f"(DAM membership 14,000 + direct clearing 3,000 + account 100 + training 200), EUR {var_fee}/MWh, "
      f"EUR {_fmt(Decimal(fees['one_off']))} one-off. Intraday membership (EUR 8,000/yr) and API access "
      "(EUR 2,000/yr) only if used.")
    a("")
    a("**Not included (unknown, must be quoted):** imbalance/balance-responsibility costs (OST), "
      "collateral / bank guarantee cost, trader time, forecasting service, IT, licences, taxes, "
      "grid charges, any curtailment by the grid operator, plant outages.")
    a("")
    a(f"## 9. What a trader's offer must beat ({latest}, P50 weather, fixed tilt DC/AC 1.2)")
    a("")
    a("Net EUR/MWh an own desk would keep after costs. **Staff/IT and other costs are ILLUSTRATIVE "
      "inputs, not facts.** Compare with a trader's offer of the form 'X% of capture price, trader "
      "takes balancing': the own desk only wins if it keeps more than the offer.")
    a("")
    a("| Staff + IT EUR/yr | Other costs EUR/MWh (imbalance, collateral, forecasts) | All costs EUR/MWh | Net EUR/MWh kept | Net as % of capture |")
    a("|---|---|---|---|---|")
    for row in decision_table(central, fixed_fee, var_fee):
        a(f"| {row['staff_it_eur_yr']} | {row['other_costs_eur_mwh']} | {row['all_costs_eur_mwh']} | "
          f"{row['net_eur_mwh']} | {row['net_pct_of_capture']}% |")
    a("")
    a("## 10. Limitations")
    a("")
    a("- Weather years (2005-2023) and price years (2023-2026) were not observed together, so "
      "links between sunny days and low prices are only partly captured.")
    a("- Production assumes the plant always runs and the grid never curtails it.")
    a("- Assumes all output is sold at the day-ahead price (perfect day-ahead forecast, no imbalance).")
    a("- 15.5 MW treated as DC MWp (owner's best guess). If it is AC, energy is higher.")
    a("- PVGIS hourly values are hour averages; their timing is approximate (+/- 30 min).")
    a("- A bigger plant selling into a thin market can lower midday prices; not modeled.")
    a("")
    a("## Sources")
    a("")
    a("- ALPEX market results (public website): https://alpex.al/market-results/")
    a("- ALPEX monthly reports: https://alpex.al/monthly-reports/")
    a("- ALPEX fee schedule v6: https://alpex.al/wp-content/uploads/2025/02/LISTA-E-TARIFAVE-NE-WEB-ANGLISHT_V6.pdf")
    a(f"- {d['pvgis']['attribution']}: https://re.jrc.ec.europa.eu/pvg_tools/")
    a("")
    return "\n".join(L)


def write_earnings_report(plant_path: Path, out_dir: Path) -> Path:
    data = build(plant_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"earnings_{data['report_date']}"
    (out_dir / f"{stem}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    path = out_dir / f"{stem}.md"
    path.write_text(render_markdown(data), encoding="utf-8")
    return path
