"""Fixtures for Gas Renew tests."""
from unittest.mock import patch
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.gas_renew.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


@pytest.fixture(autouse=True)
def no_http_server():
    """The card needs http and frontend components; don't open a real port."""
    with patch("homeassistant.components.http.HomeAssistantHTTP.start"):
        yield


@pytest.fixture(autouse=True)
async def cleanup_entries(hass: HomeAssistant):
    """Clean up and unload any config entries after each test to prevent lingering timers."""
    yield
    for entry in list(hass.config_entries.async_entries(DOMAIN)):
        if entry.state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
