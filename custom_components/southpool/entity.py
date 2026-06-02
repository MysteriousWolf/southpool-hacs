"""SouthpoolEntity class."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_REGION, REGIONS
from .coordinator import SouthpoolDataUpdateCoordinator

_MANIFEST_PATH = Path(__file__).parent / "manifest.json"
_MANIFEST_VERSION: str = json.loads(_MANIFEST_PATH.read_text()).get("version", "0.0.0")


class SouthpoolEntity(CoordinatorEntity[SouthpoolDataUpdateCoordinator]):
    """SouthpoolEntity class."""

    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: SouthpoolDataUpdateCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)

        # Get region info for device naming
        region = coordinator.config_entry.data.get(CONF_REGION, "Unknown")
        region_name = next(
            (r["label"] for r in REGIONS if r["value"] == region),
            region,
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
            sw_version=_MANIFEST_VERSION,
            configuration_url="https://labs.hupx.hu",
        )
