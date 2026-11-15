"""Diagnostics support for Gas Renew."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import GasRenewConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GasRenewConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "data": dict(entry.data),
        "options": dict(entry.options),
        "tank": entry.runtime_data._data_to_save(),
    }
