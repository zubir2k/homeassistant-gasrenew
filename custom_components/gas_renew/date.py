"""Last and previous change dates for Gas Renew."""
from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GasRenewConfigEntry
from .entity import GasRenewEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GasRenewConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    tank = entry.runtime_data
    async_add_entities(
        [GasRenewLastChange(tank, "last_change"), GasRenewPreviousChange(tank, "previous_change")]
    )


class GasRenewLastChange(GasRenewEntity, DateEntity):
    """Editable, for backdating a renew you forgot to press."""

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> date:
        return self.tank.last_change

    async def async_set_value(self, value: date) -> None:
        await self.tank.async_set_last_change(value)


class GasRenewPreviousChange(GasRenewEntity, DateEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> date | None:
        return self.tank.previous_change

    async def async_set_value(self, value: date) -> None:
        await self.tank.async_set_previous_change(value)
