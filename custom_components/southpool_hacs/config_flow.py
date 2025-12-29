"""Adds config flow for Southpool HACS."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import CONF_REGION, DOMAIN, REGIONS


class SouthpoolConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Southpool integration."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            # Use region as unique ID since only one instance per region is allowed
            await self.async_set_unique_id(user_input[CONF_REGION])
            self._abort_if_unique_id_configured()

            # Get the region name for the title
            region_name = next(
                (region["label"] for region in REGIONS if region["value"] == user_input[CONF_REGION]),
                user_input[CONF_REGION]
            )

            return self.async_create_entry(
                title=f"Southpool {region_name}",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REGION): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=region["value"],
                                    label=region["label"],
                                )
                                for region in REGIONS
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            ),
        )
