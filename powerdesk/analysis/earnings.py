"""'What would the plant have earned' arithmetic. Money in Decimal; definitions below.

Definitions (also in docs/DATA_CONTRACTS.md):
- energy_mwh            = sum of exported MWh over priced hours.
- revenue_eur           = sum(MWh_h x price_h). Gross DAM sales value before any cost.
- capture_eur_mwh       = revenue_eur / energy_mwh (generation-weighted price). Gross basis.
- baseload_eur_mwh      = simple mean of hourly prices over the same priced hours.
- capture_rate          = capture / baseload.
- curtailed_* variants  = the same, if the plant produced nothing in hours with price < 0
                          (a sell order with a 0 EUR/MWh price limit). Requires that the plant can
                          curtail; not verified.
- variable_fees_eur     = energy_mwh x ALPEX DAM trading + clearing charge per MWh.

Production is MODELED (provisional plant parameters); prices are ACTUAL ALPEX results. The
combination is a SIMULATED HISTORICAL estimate, not realized revenue.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

CENT = Decimal("0.01")
KWH = Decimal("0.001")


def to_mwh(x: float) -> Decimal:
    """Float model output -> Decimal MWh rounded to the kWh (model precision is far coarser)."""
    return Decimal(repr(round(float(x), 3))).quantize(KWH)


@dataclass(frozen=True)
class Outcome:
    hours: int
    energy_mwh: Decimal
    revenue_eur: Decimal
    baseload_eur_mwh: Decimal
    neg_price_hours_producing: int
    neg_price_mwh: Decimal
    neg_price_revenue_eur: Decimal
    low_price_hours_producing: int  # price < 10 EUR/MWh
    low_price_mwh: Decimal
    curtailed_energy_mwh: Decimal
    curtailed_revenue_eur: Decimal
    variable_fees_eur: Decimal

    @property
    def capture_eur_mwh(self) -> Decimal:
        return (self.revenue_eur / self.energy_mwh).quantize(CENT) if self.energy_mwh else Decimal(0)

    @property
    def capture_rate(self) -> Decimal:
        if not self.baseload_eur_mwh:
            return Decimal(0)
        return (self.capture_eur_mwh / self.baseload_eur_mwh).quantize(Decimal("0.001"))

    @property
    def curtailment_gain_eur(self) -> Decimal:
        return self.curtailed_revenue_eur - self.revenue_eur


def compute_outcome(
    prices: Sequence[Decimal], energy: Sequence[Decimal], variable_fee_eur_mwh: Decimal,
    low_price_threshold: Decimal = Decimal(10),
) -> Outcome:
    if len(prices) != len(energy):
        raise ValueError("prices and energy must align hour by hour")
    if not prices:
        raise ValueError("no priced hours")
    if any(e < 0 for e in energy):
        raise ValueError("exported energy cannot be negative")
    energy_total = sum(energy, Decimal(0))
    revenue = sum((p * e for p, e in zip(prices, energy, strict=True)), Decimal(0))
    neg = [(p, e) for p, e in zip(prices, energy, strict=True) if p < 0 and e > 0]
    low = [(p, e) for p, e in zip(prices, energy, strict=True) if p < low_price_threshold and e > 0]
    neg_mwh = sum((e for _, e in neg), Decimal(0))
    neg_rev = sum((p * e for p, e in neg), Decimal(0))
    return Outcome(
        hours=len(prices),
        energy_mwh=energy_total,
        revenue_eur=revenue.quantize(CENT, ROUND_HALF_UP),
        baseload_eur_mwh=(sum(prices, Decimal(0)) / len(prices)).quantize(CENT, ROUND_HALF_UP),
        neg_price_hours_producing=len(neg),
        neg_price_mwh=neg_mwh,
        neg_price_revenue_eur=neg_rev.quantize(CENT, ROUND_HALF_UP),
        low_price_hours_producing=len(low),
        low_price_mwh=sum((e for _, e in low), Decimal(0)),
        curtailed_energy_mwh=energy_total - neg_mwh,
        curtailed_revenue_eur=(revenue - neg_rev).quantize(CENT, ROUND_HALF_UP),
        variable_fees_eur=(energy_total * variable_fee_eur_mwh).quantize(CENT, ROUND_HALF_UP),
    )


def align_weather_year(
    price_hours: pd.DatetimeIndex, production: pd.Series, weather_year: int
) -> list[Decimal]:
    """Production for each price hour taken from `weather_year` at the same UTC month/day/hour.

    Feb 29 price hours use Feb 28 of a non-leap weather year. Raises if any hour is missing.
    """
    prod = production[production.index.year == weather_year]
    lookup = {(t.month, t.day, t.hour): v for t, v in zip(prod.index, prod.to_numpy(), strict=True)}
    out: list[Decimal] = []
    for t in price_hours:
        key = (t.month, t.day, t.hour)
        if key not in lookup and t.month == 2 and t.day == 29:
            key = (2, 28, t.hour)
        out.append(to_mwh(lookup[key]))
    return out


@dataclass(frozen=True)
class Window:
    label: str
    first_day: date  # local delivery days, inclusive
    last_day: date


def window_prices(prices: pd.Series, w: Window) -> pd.Series:
    """Prices (Decimal values, UTC interval-start index) whose local delivery day is in the window."""
    local_days = prices.index.tz_convert("Europe/Tirane").date
    mask = (local_days >= w.first_day) & (local_days <= w.last_day)
    return prices[mask]


def percentile(values: Sequence[Decimal], q: float) -> Decimal:
    """Linear-interpolated percentile (q in 0..100) of Decimal values, kept in Decimal."""
    xs = sorted(values)
    if not xs:
        raise ValueError("empty")
    pos = (len(xs) - 1) * Decimal(str(q)) / Decimal(100)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def utc_hours(ts: Sequence[datetime]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(list(ts), utc=True))
