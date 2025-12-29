"""Custom types for southpool_hacs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import SouthpoolApiClient
    from .coordinator import SouthpoolDataUpdateCoordinator


type SouthpoolConfigEntry = ConfigEntry[SouthpoolData]


@dataclass
class SouthpoolData:
    """Data for the Southpool integration."""

    client: SouthpoolApiClient
    coordinator: SouthpoolDataUpdateCoordinator
    integration: Integration
