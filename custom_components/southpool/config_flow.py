"""Adds config flow for Southpool HACS."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_DST_CORRECTION,
    CONF_INTERVALS,
    CONF_REGION,
    CONF_TIME_OFFSET,
    CONF_UPDATE_INTERVAL,
    DEFAULT_DST_CORRECTION,
    DEFAULT_INTERVALS,
    DEFAULT_TIME_OFFSET,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    REGIONS,
    TIME_OFFSET_MAX,
    TIME_OFFSET_MIN,
    VALID_INTERVALS,
    VALID_UPDATE_INTERVALS,
)

_REGION_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value=r["value"], label=r["label"])
            for r in REGIONS
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    ),
)

_UPDATE_INTERVAL_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value=str(m), label=f"Every {m} minutes")
            for m in VALID_UPDATE_INTERVALS
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    ),
)

_SENSORS_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value=i["value"], label=i["label"])
            for i in VALID_INTERVALS
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
        multiple=True,
    ),
)

_DST_SELECTOR = selector.BooleanSelector()

_TIME_OFFSET_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=TIME_OFFSET_MIN,
        max=TIME_OFFSET_MAX,
        step=1,
        mode=selector.NumberSelectorMode.BOX,
    ),
)

_SETUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION): _REGION_SELECTOR,
        vol.Required(
            CONF_UPDATE_INTERVAL, default=str(DEFAULT_UPDATE_INTERVAL)
        ): _UPDATE_INTERVAL_SELECTOR,
        vol.Required(CONF_INTERVALS, default=DEFAULT_INTERVALS): _SENSORS_SELECTOR,
        vol.Required(
            CONF_DST_CORRECTION, default=DEFAULT_DST_CORRECTION
        ): _DST_SELECTOR,
        vol.Required(
            CONF_TIME_OFFSET, default=DEFAULT_TIME_OFFSET
        ): _TIME_OFFSET_SELECTOR,
    },
)

_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_UPDATE_INTERVAL): _UPDATE_INTERVAL_SELECTOR,
        vol.Required(CONF_INTERVALS): _SENSORS_SELECTOR,
        vol.Required(CONF_DST_CORRECTION): _DST_SELECTOR,
        vol.Required(CONF_TIME_OFFSET): _TIME_OFFSET_SELECTOR,
    },
)


def _region_label(value: str) -> str:
    """Return a human-readable label for a region code."""
    return next((r["label"] for r in REGIONS if r["value"] == value), value)


class SouthpoolConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Southpool integration."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # noqa: ARG004
    ) -> SouthpoolOptionsFlowHandler:
        """Get the options flow for this handler."""
        return SouthpoolOptionsFlowHandler()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_REGION])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Southpool {_region_label(user_input[CONF_REGION])}",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_SETUP_SCHEMA,
        )


class SouthpoolOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Southpool."""

    def _current(
        self,
        key: str,
        *,
        default: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Get current value: options -> entry data -> default."""
        return self.config_entry.options.get(
            key,
            self.config_entry.data.get(key, default),
        )

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage the Southpool options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = self.add_suggested_values_to_schema(
            _OPTIONS_SCHEMA,
            {
                CONF_UPDATE_INTERVAL: self._current(
                    CONF_UPDATE_INTERVAL, default=str(DEFAULT_UPDATE_INTERVAL)
                ),
                CONF_INTERVALS: self._current(
                    CONF_INTERVALS, default=DEFAULT_INTERVALS
                ),
                CONF_DST_CORRECTION: self._current(
                    CONF_DST_CORRECTION, default=DEFAULT_DST_CORRECTION
                ),
                CONF_TIME_OFFSET: self._current(
                    CONF_TIME_OFFSET, default=DEFAULT_TIME_OFFSET
                ),
            },
        )

        region_label = _region_label(
            self.config_entry.data.get(CONF_REGION, ""),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "region": region_label,
            },
        )
