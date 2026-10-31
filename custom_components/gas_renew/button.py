"""Renew button for Gas Renew."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GasRenewConfigEntry
from .entity import GasRenewEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GasRenewConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([GasRenewButton(entry.runtime_data, "renew")])


class GasRenewButton(GasRenewEntity, ButtonEntity):
    """Press when a fresh cylinder is fitted."""

    async def async_press(self) -> None:
        await self.tank.async_renew()
