"""Gas Renew: estimate how much LPG is left in a cylinder."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_DATE, CARD_FILENAME, CARD_URL, DOMAIN, SERVICE_RENEW
from .tank import GasTank

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.DATE,
    Platform.CALENDAR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type GasRenewConfigEntry = ConfigEntry[GasTank]

RENEW_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(ATTR_DATE): cv.date,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the bundled Lovelace card and register the renew action."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_URL,
                str(Path(__file__).parent / "frontend" / CARD_FILENAME),
                cache_headers=False,
            )
        ]
    )
    add_extra_js_url(hass, CARD_URL)

    async def handle_renew(call: ServiceCall) -> None:
        registry = er.async_get(hass)
        entry_ids: set[str] = set()
        for entity_id in call.data[ATTR_ENTITY_ID]:
            reg = registry.async_get(entity_id)
            if reg is None or reg.platform != DOMAIN or reg.config_entry_id is None:
                raise ServiceValidationError(
                    f"{entity_id} is not a Gas Renew entity",
                    translation_domain=DOMAIN,
                    translation_key="not_gas_renew_entity",
                    translation_placeholders={"entity_id": entity_id},
                )
            entry_ids.add(reg.config_entry_id)
        for entry_id in entry_ids:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None or not hasattr(entry, "runtime_data"):
                continue
            await entry.runtime_data.async_renew(call.data.get(ATTR_DATE))

    hass.services.async_register(DOMAIN, SERVICE_RENEW, handle_renew, schema=RENEW_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GasRenewConfigEntry) -> bool:
    tank = GasTank(hass, entry)
    await tank.async_load()
    entry.runtime_data = tank
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GasRenewConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete stored state when the entry is removed."""
    from homeassistant.helpers.storage import Store

    from .const import STORAGE_KEY, STORAGE_VERSION

    await Store(hass, STORAGE_VERSION, STORAGE_KEY.format(entry_id=entry.entry_id)).async_remove()


async def _async_update_listener(hass: HomeAssistant, entry: GasRenewConfigEntry) -> None:
    """Options changed: recalculate everything."""
    await hass.config_entries.async_reload(entry.entry_id)
