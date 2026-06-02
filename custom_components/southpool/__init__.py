"""
Custom integration to integrate Southpool with Home Assistant.

For more details about this integration, please refer to
https://github.com/mysteriouswolf/southpool-hacs
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SouthpoolApiClient
from .const import (
    CONF_DST_CORRECTION,
    CONF_REGION,
    CONF_TIME_OFFSET,
    CONF_UPDATE_INTERVAL,
    DEFAULT_DST_CORRECTION,
    DEFAULT_TIME_OFFSET,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
)
from .coordinator import SouthpoolDataUpdateCoordinator
from .data import SouthpoolData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import SouthpoolConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SouthpoolConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    dst_correction = entry.options.get(
        CONF_DST_CORRECTION,
        entry.data.get(CONF_DST_CORRECTION, DEFAULT_DST_CORRECTION),
    )
    time_offset = int(
        entry.options.get(
            CONF_TIME_OFFSET,
            entry.data.get(CONF_TIME_OFFSET, DEFAULT_TIME_OFFSET),
        )
    )

    api_client = SouthpoolApiClient(
        region=entry.data[CONF_REGION],
        session=async_get_clientsession(hass),
        dst_correction=dst_correction,
        time_offset_hours=time_offset,
    )

    update_interval = int(
        entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
    )

    coordinator = SouthpoolDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        api_client=api_client,
        update_interval_minutes=update_interval,
    )
    entry.runtime_data = SouthpoolData(
        coordinator=coordinator,
    )

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SouthpoolConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    await entry.runtime_data.coordinator.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: SouthpoolConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
