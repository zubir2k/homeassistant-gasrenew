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
    CONF_RATE_KG_H,
    CONF_RUNTIME_ENTITY,
    CONF_RUNTIME_THRESHOLD,
    CONF_USAGE_SOURCE,
    DEFAULT_RATE_KG_H,
    DEFAULT_RUNTIME_THRESHOLD,
    DEFAULT_USAGE_SOURCE,
    CONF_AUTO_RENEW,
    CONF_TARE_KG,
    CONF_WEIGHT_ENTITY,
    CONF_WEIGHT_METHOD,
    DEFAULT_AUTO_RENEW,
    DEFAULT_TARE_KG,
    DEFAULT_WEIGHT_METHOD,
    SOURCE_RUNTIME,
    SOURCE_WEIGHT,
    SOURCES,
    WEIGHT_ABSOLUTE,
    WEIGHT_DELTA,
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


def _as_list(value: Any) -> list[str]:
    """Older versions stored a single entity id."""
    if not value:
        return []
    return [value] if isinstance(value, str) else list(value)


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
    """Step 1: common settings and the usage source. Step 2: that source's fields only."""

    def __init__(self) -> None:
        self._opts: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        o = self.config_entry.options
        if user_input is not None:
            med = user_input[CONF_THRESHOLD_MEDIUM]
            low = user_input[CONF_THRESHOLD_LOW]
            crit = user_input[CONF_THRESHOLD_CRITICAL]
            if not crit < low < med:
                errors["base"] = "thresholds_order"
            else:
                # Keep the other sources' settings so switching back restores them.
                self._opts = {**o, **user_input}
                source = user_input[CONF_USAGE_SOURCE]
                if source == SOURCE_RUNTIME:
                    return await self.async_step_runtime()
                if source == SOURCE_WEIGHT:
                    return await self.async_step_weight()
                return self.async_create_entry(data=self._opts)

        schema = vol.Schema(
            {
                vol.Required(CONF_USAGE_SOURCE, default=o.get(CONF_USAGE_SOURCE, DEFAULT_USAGE_SOURCE)): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=SOURCES,
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="usage_source",
                    )
                ),
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
        schema = self.add_suggested_values_to_schema(schema, user_input or {})
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_runtime(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self._opts, **user_input})
        o = self._opts
        schema = vol.Schema(
            {
                vol.Required(CONF_RUNTIME_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "sensor", "switch", "input_boolean", "fan", "light"],
                        multiple=True,
                    )
                ),
                vol.Required(CONF_RUNTIME_THRESHOLD, default=o.get(CONF_RUNTIME_THRESHOLD, DEFAULT_RUNTIME_THRESHOLD)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=10000, step=0.1, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_RATE_KG_H, default=o.get(CONF_RATE_KG_H, DEFAULT_RATE_KG_H)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.01, max=3, step=0.01, unit_of_measurement="kg/h", mode=selector.NumberSelectorMode.BOX)
                ),
            }
        )
        schema = self.add_suggested_values_to_schema(schema, {CONF_RUNTIME_ENTITY: _as_list(o.get(CONF_RUNTIME_ENTITY))})
        return self.async_show_form(step_id="runtime", data_schema=schema)

    async def async_step_weight(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self._opts, **user_input})
        o = self._opts
        schema = vol.Schema(
            {
                vol.Required(CONF_WEIGHT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_WEIGHT_METHOD, default=o.get(CONF_WEIGHT_METHOD, DEFAULT_WEIGHT_METHOD)): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[WEIGHT_DELTA, WEIGHT_ABSOLUTE],
                        mode=selector.SelectSelectorMode.LIST,
                        translation_key="weight_method",
                    )
                ),
                vol.Required(CONF_TARE_KG, default=o.get(CONF_TARE_KG, DEFAULT_TARE_KG)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=200, step=0.1, unit_of_measurement="kg", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_AUTO_RENEW, default=o.get(CONF_AUTO_RENEW, DEFAULT_AUTO_RENEW)): selector.BooleanSelector(),
            }
        )
        schema = self.add_suggested_values_to_schema(schema, {CONF_WEIGHT_ENTITY: o.get(CONF_WEIGHT_ENTITY)})
        return self.async_show_form(step_id="weight", data_schema=schema)
