"""Sensors for Gas Renew."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GasRenewConfigEntry
from .const import DOMAIN, LEVELS
from .entity import GasRenewEntity
from .tank import GasTank


@dataclass(frozen=True, kw_only=True)
class GasRenewSensorDescription(SensorEntityDescription):
    value_fn: Callable[[GasTank], Any]


SENSORS: tuple[GasRenewSensorDescription, ...] = (
    GasRenewSensorDescription(
        key="level",
        device_class=SensorDeviceClass.ENUM,
        options=LEVELS,
        value_fn=lambda t: t.level,
    ),
    GasRenewSensorDescription(
        key="remaining",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda t: t.percentage,
    ),
    GasRenewSensorDescription(
        key="remaining_gas",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda t: t.remaining_kg,
    ),
    GasRenewSensorDescription(
        key="consumption",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda t: t.consumption_m3,
    ),
    GasRenewSensorDescription(
        key="daily_usage",
        native_unit_of_measurement="m³/d",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda t: t.daily_rate_m3,
    ),
    GasRenewSensorDescription(
        key="expected_empty",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda t: t.expected_empty,
    ),
    GasRenewSensorDescription(
        key="days_in_use",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda t: t.days_in_use,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GasRenewConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    tank = entry.runtime_data
    async_add_entities(GasRenewSensor(tank, d) for d in SENSORS)


class GasRenewSensor(GasRenewEntity, SensorEntity):
    entity_description: GasRenewSensorDescription

    def __init__(self, tank: GasTank, description: GasRenewSensorDescription) -> None:
        super().__init__(tank, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.tank)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """The level sensor carries everything the card needs in one place."""
        if self.entity_description.key != "level":
            return None
        t = self.tank
        registry = er.async_get(self.hass)
        renew_button = registry.async_get_entity_id(
            "button", DOMAIN, f"{t.entry.entry_id}_renew"
        )
        expected: datetime = t.expected_empty
        return {
            "percentage": t.percentage,
            "remaining_kg": t.remaining_kg,
            "cylinder_kg": t.cylinder_kg,
            "days_in_use": t.days_in_use,
            "days_left": t.days_left,
            "duration": t.duration,
            "learned_duration": t.learned_duration,
            "history": t.history,
            "last_change": t.last_change.isoformat(),
            "previous_change": t.previous_change.isoformat() if t.previous_change else None,
            "expected_empty": expected.date().isoformat(),
            "daily_usage_m3": t.daily_rate_m3,
            "usage_source": "weight" if t.weight_mode else "runtime" if t.runtime_mode else "duration",
            "running": t.running if t.runtime_mode else None,
            "running_count": t.active_count if t.runtime_mode else None,
            "runtime_hours": round(t.cylinder_runtime_h, 2) if t.runtime_mode else None,
            "rate_kg_h": round(t.rate_kg_h, 3) if t.runtime_mode else None,
            "scale_kg": round(t.gross_kg, 2) if t.weight_mode and t.gross_kg is not None else None,
            "scale_stale": t.weight_stale if t.weight_mode else None,
            "renew_entity": renew_button,
        }
