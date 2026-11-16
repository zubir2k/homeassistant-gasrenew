"""Tests for Gas Renew initialization, setup, and services."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gas_renew.const import (
    CONF_CYLINDER_KG,
    CONF_DURATION,
    CONF_LAST_CHANGE,
    DOMAIN,
)
from custom_components.gas_renew.diagnostics import async_get_config_entry_diagnostics


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """Test setting up and unloading Gas Renew config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kitchen Gas",
        data={
            CONF_NAME: "Kitchen Gas",
            CONF_CYLINDER_KG: 14.0,
            CONF_DURATION: 60,
            CONF_LAST_CHANGE: "2026-11-01",
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    # Verify sensor state exists
    level_state = hass.states.get("sensor.kitchen_gas_level")
    assert level_state is not None

    # Test diagnostics
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["data"][CONF_NAME] == "Kitchen Gas"
    assert "tank" in diag

    # Test service call gas_renew.renew
    await hass.services.async_call(
        DOMAIN,
        "renew",
        {"entity_id": "sensor.kitchen_gas_level"},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Test unload
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
