"""Base entity for Gas Renew."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .tank import GasTank


class GasRenewEntity(Entity):
    """Shared device and update wiring."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, tank: GasTank, key: str) -> None:
        self.tank = tank
        entry = tank.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Gas Renew",
            model=f"{tank.cylinder_kg:g} kg LPG cylinder",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.tank.async_add_listener(self.async_write_ha_state))
