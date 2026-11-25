"""Plant configuration with an explicit certainty status on every parameter."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

Status = Literal["CONFIRMED", "PROVISIONAL", "UNKNOWN"]


class Param(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float | str | None
    status: Status
    source: str

    @model_validator(mode="after")
    def unknown_has_no_value(self) -> Param:
        if self.status == "UNKNOWN" and self.value is not None:
            raise ValueError("UNKNOWN parameters must not carry a value")
        if self.status != "UNKNOWN" and self.value is None:
            raise ValueError("a parameter with a value status needs a value")
        return self


class PlantParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Param
    company: Param
    latitude: Param
    longitude: Param
    capacity_dc_mwp: Param
    capacity_ac_mw: Param
    grid_export_limit_mw: Param
    mounting: Param
    battery_power_mw: Param
    battery_energy_mwh: Param
    commercial_operation: Param


class ModelDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dc_ac_ratio_scenarios: list[float]
    mounting_scenarios: list[Literal["fixed", "single_axis"]]
    fixed_tilt_deg: float
    fixed_azimuth_deg: float
    tracker_max_angle_deg: float
    tracker_gcr: float
    gamma_pdc_per_c: float
    dc_losses_pct: float
    inverter_efficiency: float
    ac_losses_pct: float


class PlantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plant: PlantParams
    model_defaults: ModelDefaults

    def num(self, name: str) -> float | None:
        p: Param = getattr(self.plant, name)
        return None if p.value is None else float(p.value)

    def provisional_or_unknown(self) -> list[tuple[str, Param]]:
        return [(k, v) for k, v in self.plant if isinstance(v, Param) and v.status != "CONFIRMED"]


def load_plant_config(path: Path) -> PlantConfig:
    return PlantConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
