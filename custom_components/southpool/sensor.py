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

from .const import CET_TZ
from .entity import SouthpoolEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SouthpoolDataUpdateCoordinator
    from .data import SouthpoolConfigEntry

ENTITY_DESCRIPTIONS = (
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
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: SouthpoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    async_add_entities(
        SouthpoolSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
            region=entry.data.get("region", "Unknown"),
        )
        for entity_description in ENTITY_DESCRIPTIONS
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
        self._attr_unique_id = f"{region}_{entity_description.key}"
        self._attr_name = f"Southpool {region} {entity_description.name}"

    @property
    def native_value(self) -> str | int | float | None:
        """Return the current native value of the sensor."""
        if not self.coordinator.data:
            return None

        current_values = self.coordinator.data.get("current_values", {})

        if self.entity_description.key == "timestamp":
            return self._get_timestamp_value(current_values)

        return self._get_regular_value(current_values)

    def _get_timestamp_value(self, current_values: dict) -> datetime | None:
        """Get timestamp value from delivery day and quarter hour."""
        delivery_day = current_values.get("delivery_day", "")
        quarter_hour = current_values.get("quarter_hour", "")

        if not delivery_day or not quarter_hour:
            return None

        try:
            # Parse delivery day as CET (always assume CET format)
            base_date = datetime.fromisoformat(delivery_day[:10]).replace(tzinfo=CET_TZ)
            # Calculate minutes from quarter hour (1-based, 15-minute intervals)
            minutes_offset = (int(quarter_hour) - 1) * 15
            return base_date + timedelta(minutes=minutes_offset)
        except (ValueError, TypeError):
            return None

    def _get_regular_value(self, current_values: dict) -> str | int | float | None:
        """Get regular value with appropriate type conversion."""
        if self.entity_description.key not in current_values:
            return None

        value = current_values[self.entity_description.key]
        if not value:
            return None

        # Convert numeric values for appropriate sensors
        if self.entity_description.key == "quarter_hour":
            return self._convert_to_int(value)
        if self.entity_description.key in [
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

    @property
    def extra_state_attributes(self) -> dict[str, any]:
        """Return additional state attributes with 48h forecast."""
        if not self.coordinator.data:
            return {}

        forecast_data = self.coordinator.data.get("forecast_48h", {})

        attributes = {
            "region": self._region,
            "last_update": self.coordinator.data.get("last_update"),
        }

        # Add 48-hour forecast for this specific column
        if self.entity_description.key == "timestamp":
            # Calculate timestamps for forecast
            delivery_days = forecast_data.get("delivery_day", [])
            quarter_hours = forecast_data.get("quarter_hour", [])

            timestamp_list = []
            for delivery_day, quarter_hour in zip(
                delivery_days, quarter_hours, strict=False
            ):
                if delivery_day and quarter_hour:
                    try:
                        # Parse delivery day as CET (always assume CET format)
                        base_date = datetime.fromisoformat(delivery_day[:10]).replace(
                            tzinfo=CET_TZ
                        )
                        minutes_offset = (int(quarter_hour) - 1) * 15
                        timestamp = base_date + timedelta(minutes=minutes_offset)
                        timestamp_list.append(timestamp.isoformat())
                    except (ValueError, TypeError):
                        timestamp_list.append("")
                else:
                    timestamp_list.append(None)

            attributes["forecast_48h"] = timestamp_list
            attributes["forecast_count"] = len(timestamp_list)
        elif self.entity_description.key in forecast_data:
            forecast_list = forecast_data[self.entity_description.key]

            # Convert values to appropriate types if needed
            if self.entity_description.key == "quarter_hour":
                forecast_list = [
                    int(v) if v and str(v).isdigit() else v for v in forecast_list
                ]
            elif self.entity_description.key in [
                "price",
                "traded_volume",
                "baseload_price",
            ]:
                converted_list = []
                for v in forecast_list:
                    try:
                        converted_list.append(float(v) if v else None)
                    except (ValueError, TypeError):
                        converted_list.append(None)
                forecast_list = converted_list

            attributes["forecast_48h"] = forecast_list
            attributes["forecast_count"] = len(forecast_list)

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success and self.coordinator.data is not None
        )
