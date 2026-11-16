"""Tests for Gas Renew config flow."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gas_renew.const import (
    CONF_AUTO_LEARN,
    CONF_CYLINDER_KG,
    CONF_DURATION,
    CONF_LAST_CHANGE,
    CONF_PREVIOUS_CHANGE,
    DOMAIN,
)


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """Test full successful user config flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Kitchen Cylinder",
            CONF_CYLINDER_KG: "14",
            CONF_DURATION: 60,
            CONF_LAST_CHANGE: "2026-11-01",
            CONF_PREVIOUS_CHANGE: "2026-09-01",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kitchen Cylinder"
    assert result["data"][CONF_NAME] == "Kitchen Cylinder"
    assert result["data"][CONF_CYLINDER_KG] == 14.0
    assert result["data"][CONF_DURATION] == 60
    await hass.async_block_till_done()


async def test_user_flow_duplicate_abort(hass: HomeAssistant) -> None:
    """Test duplicate cylinder names abort."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kitchen Cylinder",
        data={
            CONF_NAME: "Kitchen Cylinder",
            CONF_CYLINDER_KG: 14.0,
            CONF_DURATION: 60,
            CONF_LAST_CHANGE: "2026-11-01",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Kitchen Cylinder",
            CONF_CYLINDER_KG: "14",
            CONF_DURATION: 60,
            CONF_LAST_CHANGE: "2026-11-01",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_validation_errors(hass: HomeAssistant) -> None:
    """Test validation errors for invalid size, future date, and previous after last."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    # Invalid cylinder size
    res = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Invalid Size",
            CONF_CYLINDER_KG: "0",
            CONF_DURATION: 60,
            CONF_LAST_CHANGE: "2026-11-01",
        },
    )
    assert res["type"] is FlowResultType.FORM
    assert res["errors"][CONF_CYLINDER_KG] == "invalid_size"

    # Future date
    tomorrow = (dt_util.now().date() + dt_util.dt.timedelta(days=1)).isoformat()
    res = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Future Date",
            CONF_CYLINDER_KG: "14",
            CONF_DURATION: 60,
            CONF_LAST_CHANGE: tomorrow,
        },
    )
    assert res["type"] is FlowResultType.FORM
    assert res["errors"][CONF_LAST_CHANGE] == "future_date"

    # Previous after last
    res = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Bad Previous",
            CONF_CYLINDER_KG: "14",
            CONF_DURATION: 60,
            CONF_LAST_CHANGE: "2026-11-01",
            CONF_PREVIOUS_CHANGE: "2026-11-02",
        },
    )
    assert res["type"] is FlowResultType.FORM
    assert res["errors"][CONF_PREVIOUS_CHANGE] == "previous_after_last"


async def test_reconfigure_flow(hass: HomeAssistant) -> None:
    """Test reconfiguring cylinder size."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kitchen Cylinder",
        data={
            CONF_NAME: "Kitchen Cylinder",
            CONF_CYLINDER_KG: 14.0,
            CONF_DURATION: 60,
            CONF_LAST_CHANGE: "2026-11-01",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CYLINDER_KG: "12"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_CYLINDER_KG] == 12.0
    await hass.async_block_till_done()
