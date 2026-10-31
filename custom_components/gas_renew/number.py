"""Expected duration number for Gas Renew."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GasRenewConfigEntry
from .const import MAX_DURATION, MIN_DURATION
from .entity import GasRenewEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GasRenewConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([GasRenewDuration(entry.runtime_data, "duration")])


class GasRenewDuration(GasRenewEntity, NumberEntity):
    """How many days a full cylinder lasts. Auto-learn updates it on each renew."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_DURATION
    _attr_native_max_value = MAX_DURATION
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    @property
    def native_value(self) -> float:
        return self.tank.duration

    async def async_set_native_value(self, value: float) -> None:
        await self.tank.async_set_duration(int(value))
