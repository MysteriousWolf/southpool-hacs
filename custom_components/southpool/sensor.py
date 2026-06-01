"""Sensor platform for Southpool."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower

from .entity import SouthpoolEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SouthpoolDataUpdateCoordinator
    from .data import SouthpoolConfigEntry


def get_entity_descriptions() -> tuple[SensorEntityDescription, ...]:
    """Get all entity descriptions for both 15-minute and hourly intervals."""
    # 15-minute interval descriptions (original names)
    descriptions_15min = [
        SensorEntityDescription(
            key="timestamp",
            name="Timestamp",
            icon="mdi:clock",
            device_class=SensorDeviceClass.TIMESTAMP,
        ),
        SensorEntityDescription(
            key="quarter_hour",
            name="Quarter Hour",
            icon="mdi:clock-outline",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="price",
            name="Price",
            icon="mdi:currency-eur",
            unit_of_measurement="EUR/MWh",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="traded_volume",
            name="Traded Volume",
            icon="mdi:chart-line",
            unit_of_measurement=UnitOfPower.MEGA_WATT,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="baseload_price",
            name="Baseload Price",
            icon="mdi:currency-eur",
            unit_of_measurement="EUR/MWh",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="status",
            name="Status",
            icon="mdi:check-circle",
        ),
    ]

    # Hourly interval descriptions (with "hourly" prefix)
    descriptions_hourly = [
        SensorEntityDescription(
            key="hourly_timestamp",
            name="Hourly Timestamp",
            icon="mdi:clock",
            device_class=SensorDeviceClass.TIMESTAMP,
        ),
        SensorEntityDescription(
            key="hourly_hour",
            name="Hourly Hour",
            icon="mdi:clock-outline",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="hourly_price",
            name="Hourly Price",
            icon="mdi:currency-eur",
            unit_of_measurement="EUR/MWh",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="hourly_traded_volume",
            name="Hourly Traded Volume",
            icon="mdi:chart-line",
            unit_of_measurement=UnitOfPower.MEGA_WATT,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="hourly_baseload_price",
            name="Hourly Baseload Price",
            icon="mdi:currency-eur",
            unit_of_measurement="EUR/MWh",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        SensorEntityDescription(
            key="hourly_status",
            name="Hourly Status",
            icon="mdi:check-circle",
        ),
    ]

    return tuple(descriptions_15min + descriptions_hourly)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: SouthpoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    entity_descriptions = get_entity_descriptions()

    async_add_entities(
        SouthpoolSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
            region=entry.data.get("region", "Unknown"),
        )
        for entity_description in entity_descriptions
    )


class SouthpoolSensor(SouthpoolEntity, SensorEntity):
    """Southpool Sensor class."""

    def __init__(
        self,
        coordinator: SouthpoolDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        region: str,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._region = region
        self._is_hourly = entity_description.key.startswith("hourly_")
        self._attr_unique_id = f"{region}_{entity_description.key}"
        self._attr_name = f"Southpool {region} {entity_description.name}"

    @property
    def native_value(self) -> str | int | float | datetime | None:
        """Return the current native value of the sensor."""
        if not self.coordinator.data:
            return None

        # Select appropriate data source based on sensor type
        if self._is_hourly:
            current_values = self.coordinator.data.get("current_values_hourly", {})
            key_suffix = self.entity_description.key[7:]  # Remove "hourly_" prefix
        else:
            current_values = self.coordinator.data.get("current_values_15min", {})
            key_suffix = self.entity_description.key

        if key_suffix == "timestamp":
            return self._get_timestamp_value(current_values)

        return self._get_regular_value(current_values, key_suffix)

    @staticmethod
    def _get_timestamp_value(current_values: dict[str, Any]) -> datetime | None:
        """Return the UTC period-start datetime from the current values."""
        period_start = current_values.get("period_start")
        if isinstance(period_start, datetime):
            return period_start
        # Fall back to parsing the ISO string if the datetime object was lost
        # somewhere along the way (e.g., serialised through HA storage).
        iso = current_values.get("timestamp")
        if iso:
            try:
                return datetime.fromisoformat(iso)
            except ValueError, TypeError:
                return None
        return None

    def _get_regular_value(
        self, current_values: dict[str, Any], key_suffix: str
    ) -> str | int | float | None:
        """Get regular value with appropriate type conversion."""
        if key_suffix not in current_values:
            return None

        value = current_values[key_suffix]
        if value in (None, ""):
            return None

        # Convert numeric values for appropriate sensors
        if key_suffix in ("quarter_hour", "hour"):
            return self._convert_to_int(value)
        if key_suffix in ("price", "traded_volume", "baseload_price"):
            return self._convert_to_float(value)
        return value

    @staticmethod
    def _convert_to_int(value: Any) -> int | None:
        """Convert value to int, return None on error."""
        try:
            return int(value)
        except ValueError, TypeError:
            return None

    @staticmethod
    def _convert_to_float(value: Any) -> float | None:
        """Convert value to float, return None on error."""
        try:
            return float(value)
        except ValueError, TypeError:
            return None

    def _convert_forecast_values(
        self, forecast_list: list[Any], key_suffix: str
    ) -> list[Any]:
        """Convert forecast values to appropriate types."""
        if key_suffix in ("quarter_hour", "hour"):
            return [self._convert_to_int(v) for v in forecast_list]

        if key_suffix in ("price", "traded_volume", "baseload_price"):
            return [self._convert_to_float(v) for v in forecast_list]

        return forecast_list

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes with 48h forecast."""
        if not self.coordinator.data:
            return {}

        # Select appropriate forecast data based on sensor type
        if self._is_hourly:
            forecast_data = self.coordinator.data.get("forecast_48h_hourly", {})
            key_suffix = self.entity_description.key[7:]  # Remove "hourly_" prefix
        else:
            forecast_data = self.coordinator.data.get("forecast_48h_15min", {})
            key_suffix = self.entity_description.key

        attributes: dict[str, Any] = {
            "region": self._region,
            "last_update": self.coordinator.data.get("last_update"),
        }

        if key_suffix == "timestamp":
            timestamp_list = list(forecast_data.get("timestamp", []))
            attributes["forecast_48h"] = timestamp_list
            attributes["forecast_count"] = len(timestamp_list)
        elif key_suffix in forecast_data:
            forecast_list = self._convert_forecast_values(
                forecast_data[key_suffix], key_suffix
            )
            attributes["forecast_48h"] = forecast_list
            attributes["forecast_count"] = len(forecast_list)

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success and self.coordinator.data is not None
        )
