"""SouthpoolEntity class."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_REGION, REGIONS
from .coordinator import SouthpoolDataUpdateCoordinator


class SouthpoolEntity(CoordinatorEntity[SouthpoolDataUpdateCoordinator]):
    """SouthpoolEntity class."""

    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: SouthpoolDataUpdateCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.config_entry.entry_id

        # Get region info for device naming
        region = coordinator.config_entry.data.get(CONF_REGION, "Unknown")
        region_name = next(
            (r["label"] for r in REGIONS if r["value"] == region),
            region
        )

        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    coordinator.config_entry.domain,
                    coordinator.config_entry.entry_id,
                ),
            },
            name=f"Southpool {region_name}",
            manufacturer="Southpool",
            model=f"Power Grid {region}",
            sw_version="1.0",
            configuration_url="https://labs.hupx.hu",
        )
