"""
Custom integration to integrate Southpool with Home Assistant.

For more details about this integration, please refer to
https://github.com/mysteriouswolf/southpool-hacs
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import SouthpoolApiClient
from .const import CONF_REGION, DOMAIN, LOGGER, UPDATE_INTERVAL_MINUTES
from .coordinator import SouthpoolDataUpdateCoordinator
from .data import SouthpoolData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import SouthpoolConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: SouthpoolConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    api_client = SouthpoolApiClient(
        region=entry.data[CONF_REGION],
        session=async_get_clientsession(hass),
    )
    coordinator = SouthpoolDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        api_client=api_client,
    )
    entry.runtime_data = SouthpoolData(
        client=api_client,
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
    )

    # https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SouthpoolConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: SouthpoolConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
