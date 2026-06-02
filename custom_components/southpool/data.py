"""Custom types for Southpool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import SouthpoolDataUpdateCoordinator


type SouthpoolConfigEntry = ConfigEntry[SouthpoolData]


@dataclass
class SouthpoolData:
    """Data for the Southpool integration."""

    coordinator: SouthpoolDataUpdateCoordinator
