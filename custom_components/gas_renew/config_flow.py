"""Config flow for Gas Renew."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUTO_LEARN,
    CONF_CYLINDER_KG,
    CONF_DURATION,
    CONF_LAST_CHANGE,
    CONF_LEARN_SAMPLES,
    CONF_M3_PER_KG,
    CONF_PREVIOUS_CHANGE,
    CONF_THRESHOLD_CRITICAL,
    CONF_THRESHOLD_LOW,
    CONF_THRESHOLD_MEDIUM,
    DEFAULT_AUTO_LEARN,
    DEFAULT_CYLINDER_KG,
    DEFAULT_DURATION,
    DEFAULT_LEARN_SAMPLES,
    DEFAULT_M3_PER_KG,
    DEFAULT_NAME,
    DEFAULT_THRESHOLD_CRITICAL,
    DEFAULT_THRESHOLD_LOW,
    DEFAULT_THRESHOLD_MEDIUM,
    DOMAIN,
    MAX_DURATION,
    MIN_DURATION,
)

CYLINDER_SIZES = ["12", "14", "50"]


def _pct() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX)
    )


class GasRenewConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            last = user_input[CONF_LAST_CHANGE]
            prev = user_input.get(CONF_PREVIOUS_CHANGE)
            try:
                size = float(user_input[CONF_CYLINDER_KG])
            except (TypeError, ValueError):
                size = 0
            if not 1 <= size <= 100:
                errors[CONF_CYLINDER_KG] = "invalid_size"
            elif last > dt_util.now().date().isoformat():
                errors[CONF_LAST_CHANGE] = "future_date"
            elif prev and prev >= last:
                errors[CONF_PREVIOUS_CHANGE] = "previous_after_last"
            else:
                data = {
                    CONF_CYLINDER_KG: size,
                    CONF_DURATION: int(user_input[CONF_DURATION]),
                    CONF_LAST_CHANGE: last,
                    CONF_PREVIOUS_CHANGE: prev,
                }
                return self.async_create_entry(title=user_input[CONF_NAME], data=data)

        today = dt_util.now().date().isoformat()
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
                vol.Required(CONF_CYLINDER_KG, default=str(int(DEFAULT_CYLINDER_KG))): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=CYLINDER_SIZES,
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="cylinder_kg",
                    )
                ),
                vol.Required(CONF_DURATION, default=DEFAULT_DURATION): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_DURATION, max=MAX_DURATION, step=1, unit_of_measurement="d",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_LAST_CHANGE, default=today): selector.DateSelector(),
                vol.Optional(CONF_PREVIOUS_CHANGE): selector.DateSelector(),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, user_input), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GasRenewOptionsFlow()


class GasRenewOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            med = user_input[CONF_THRESHOLD_MEDIUM]
            low = user_input[CONF_THRESHOLD_LOW]
            crit = user_input[CONF_THRESHOLD_CRITICAL]
            if not crit < low < med:
                errors["base"] = "thresholds_order"
            else:
                return self.async_create_entry(data=user_input)

        o = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_THRESHOLD_MEDIUM, default=o.get(CONF_THRESHOLD_MEDIUM, DEFAULT_THRESHOLD_MEDIUM)): _pct(),
                vol.Required(CONF_THRESHOLD_LOW, default=o.get(CONF_THRESHOLD_LOW, DEFAULT_THRESHOLD_LOW)): _pct(),
                vol.Required(CONF_THRESHOLD_CRITICAL, default=o.get(CONF_THRESHOLD_CRITICAL, DEFAULT_THRESHOLD_CRITICAL)): _pct(),
                vol.Required(CONF_M3_PER_KG, default=o.get(CONF_M3_PER_KG, DEFAULT_M3_PER_KG)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.3, max=0.6, step=0.001, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_AUTO_LEARN, default=o.get(CONF_AUTO_LEARN, DEFAULT_AUTO_LEARN)): selector.BooleanSelector(),
                vol.Required(CONF_LEARN_SAMPLES, default=o.get(CONF_LEARN_SAMPLES, DEFAULT_LEARN_SAMPLES)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=12, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
