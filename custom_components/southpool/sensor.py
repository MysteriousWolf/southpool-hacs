"""Sensor platform for Southpool."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower

from .const import CET_TZ, MINUTES_PER_QUARTER_HOUR
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
    def native_value(self) -> str | int | float | None:
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

    def _get_timestamp_value(self, current_values: dict) -> datetime | None:
        """Get timestamp value from delivery day and interval value."""
        delivery_day = current_values.get("delivery_day", "")

        if self._is_hourly:
            interval_value = current_values.get("hour", "")
        else:
            interval_value = current_values.get("quarter_hour", "")

        if not delivery_day or not interval_value:
            return None

        try:
            # Parse delivery day as CET (always assume CET format)
            base_date = datetime.fromisoformat(delivery_day[:10]).replace(tzinfo=CET_TZ)

            if self._is_hourly:
                # For hourly data, hour is the actual hour (1-24, convert to 0-based)
                hour_offset = int(interval_value) - 1
                return base_date + timedelta(hours=hour_offset)
            # Calculate minutes from quarter hour (1-based, 15-minute intervals)
            minutes_offset = (int(interval_value) - 1) * MINUTES_PER_QUARTER_HOUR
            return base_date + timedelta(minutes=minutes_offset)
        except (ValueError, TypeError):
            return None

    def _get_regular_value(
        self, current_values: dict, key_suffix: str
    ) -> str | int | float | None:
        """Get regular value with appropriate type conversion."""
        if key_suffix not in current_values:
            return None

        value = current_values[key_suffix]
        if not value:
            return None

        # Convert numeric values for appropriate sensors
        if key_suffix in ["quarter_hour", "hour"]:
            return self._convert_to_int(value)
        if key_suffix in [
            "price",
            "traded_volume",
            "baseload_price",
        ]:
            return self._convert_to_float(value)
        return value

    def _convert_to_int(self, value: str) -> int | None:
        """Convert value to int, return None on error."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _convert_to_float(self, value: str) -> float | None:
        """Convert value to float, return None on error."""
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _build_timestamp_forecast(self, forecast_data: dict) -> list[str]:
        """Build timestamp forecast list."""
        delivery_days = forecast_data.get("delivery_day", [])
        interval_values = (
            forecast_data.get("hour", [])
            if self._is_hourly
            else forecast_data.get("quarter_hour", [])
        )

        timestamp_list = []
        for delivery_day, interval_value in zip(
            delivery_days, interval_values, strict=False
        ):
            if delivery_day and interval_value:
                try:
                    base_date = datetime.fromisoformat(delivery_day[:10]).replace(
                        tzinfo=CET_TZ
                    )
                    if self._is_hourly:
                        hour_offset = int(interval_value) - 1
                        timestamp = base_date + timedelta(hours=hour_offset)
                    else:
                        minutes_offset = (
                            int(interval_value) - 1
                        ) * MINUTES_PER_QUARTER_HOUR
                        timestamp = base_date + timedelta(minutes=minutes_offset)
                    timestamp_list.append(timestamp.isoformat())
                except (ValueError, TypeError):
                    timestamp_list.append("")
            else:
                timestamp_list.append(None)

        return timestamp_list

    def _convert_forecast_values(self, forecast_list: list, key_suffix: str) -> list:
        """Convert forecast values to appropriate types."""
        if key_suffix in ["quarter_hour", "hour"]:
            return [int(v) if v and str(v).isdigit() else v for v in forecast_list]

        if key_suffix in ["price", "traded_volume", "baseload_price"]:
            converted_list = []
            for v in forecast_list:
                try:
                    converted_list.append(float(v) if v else None)
                except (ValueError, TypeError):
                    converted_list.append(None)
            return converted_list

        return forecast_list

    @property
    def extra_state_attributes(self) -> dict[str, any]:
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

        attributes = {
            "region": self._region,
            "last_update": self.coordinator.data.get("last_update"),
        }

        if key_suffix == "timestamp":
            timestamp_list = self._build_timestamp_forecast(forecast_data)
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
