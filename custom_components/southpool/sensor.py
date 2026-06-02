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
from homeassistant.const import UnitOfEnergy

from .const import (
    CONF_INTERVALS,
    CONF_REGION,
    DEFAULT_INTERVALS,
    INTERVAL_15MIN,
    INTERVAL_HOURLY,
)
from .entity import SouthpoolEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SouthpoolDataUpdateCoordinator
    from .data import SouthpoolConfigEntry

_HOURLY_PREFIX = "hourly_"
_HOURLY_PREFIX_LEN = len(_HOURLY_PREFIX)

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    # 15-minute interval descriptions
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
        native_unit_of_measurement="EUR/MWh",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="traded_volume",
        name="Traded Volume",
        icon="mdi:chart-line",
        native_unit_of_measurement=UnitOfEnergy.MEGA_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="baseload_price",
        name="Baseload Price",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/MWh",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="status",
        name="Status",
        icon="mdi:check-circle",
    ),
    # Hourly interval descriptions (with "hourly_" prefix)
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
        native_unit_of_measurement="EUR/MWh",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="hourly_traded_volume",
        name="Hourly Traded Volume",
        icon="mdi:chart-line",
        native_unit_of_measurement=UnitOfEnergy.MEGA_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="hourly_baseload_price",
        name="Hourly Baseload Price",
        icon="mdi:currency-eur",
        native_unit_of_measurement="EUR/MWh",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="hourly_status",
        name="Hourly Status",
        icon="mdi:check-circle",
    ),
)

# Sensor keys that hold integer values (quarter-hour or hour index)
_INTEGER_KEYS: frozenset[str] = frozenset({"quarter_hour", "hour"})
# Sensor keys that hold float values (price, volume)
_FLOAT_KEYS: frozenset[str] = frozenset({"price", "traded_volume", "baseload_price"})


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SouthpoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    enabled: list[str] = entry.options.get(
        CONF_INTERVALS,
        entry.data.get(CONF_INTERVALS, DEFAULT_INTERVALS),
    )

    async_add_entities(
        SouthpoolSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
            region=entry.data.get(CONF_REGION, "Unknown"),
        )
        for entity_description in SENSOR_DESCRIPTIONS
        if _is_sensor_enabled(entity_description, enabled)
    )


def _is_sensor_enabled(
    desc: SensorEntityDescription,
    enabled: list[str],
) -> bool:
    """Return True if this sensor should be created based on user options."""
    if desc.key.startswith(_HOURLY_PREFIX):
        return INTERVAL_HOURLY in enabled
    return INTERVAL_15MIN in enabled


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
        self._is_hourly = entity_description.key.startswith(_HOURLY_PREFIX)
        self._attr_unique_id = f"{region}_{entity_description.key}"
        self._attr_name = f"Southpool {region} {entity_description.name}"

    # ------------------------------------------------------------------
    # Helpers for resolving interval-specific data from the coordinator
    # ------------------------------------------------------------------

    @property
    def _data_key(self) -> str:
        """
        Return the sensor key stripped of the ``hourly_`` prefix.

        For a 15-min sensor ``price`` this is ``"price"``; for an hourly
        sensor ``hourly_price`` this is ``"price"``.
        """
        key = self.entity_description.key
        if self._is_hourly:
            return key[_HOURLY_PREFIX_LEN:]
        return key

    def _current_values(self) -> dict[str, Any]:
        """Return the current-values dict for this sensor's interval type."""
        data = self.coordinator.data or {}
        key = "current_values_hourly" if self._is_hourly else "current_values_15min"
        return data.get(key, {})

    def _forecast(self) -> dict[str, Any]:
        """Return the forecast dict for this sensor's interval type."""
        data = self.coordinator.data or {}
        key = "forecast_48h_hourly" if self._is_hourly else "forecast_48h_15min"
        return data.get(key, {})

    # ------------------------------------------------------------------
    # Coordinator update / entity lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Process coordinator data immediately after entity is registered."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self._compute_native_value()
        self._attr_extra_state_attributes = self._compute_attributes()
        super()._handle_coordinator_update()

    # ------------------------------------------------------------------
    # Native value computation
    # ------------------------------------------------------------------

    def _compute_native_value(self) -> str | int | float | datetime | None:
        if not self.coordinator.data:
            return None

        current = self._current_values()
        data_key = self._data_key

        if data_key == "timestamp":
            return self._parse_timestamp(current)

        return self._coerce_value(current.get(data_key))

    @staticmethod
    def _parse_timestamp(current: dict[str, Any]) -> datetime | None:
        """
        Parse a timestamp from coordinator data.

        Prefers the pre-computed ``period_start`` datetime; falls back to
        parsing the ISO string in ``timestamp``.
        """
        period_start = current.get("period_start")
        if isinstance(period_start, datetime):
            return period_start
        iso = current.get("timestamp")
        if iso:
            try:
                return datetime.fromisoformat(iso)
            except ValueError, TypeError:
                return None
        return None

    # ------------------------------------------------------------------
    # Value coercion helpers
    # ------------------------------------------------------------------

    def _coerce_value(self, value: object) -> str | int | float | None:
        """Coerce a raw value to the appropriate Python type for this sensor."""
        if value in (None, ""):
            return None

        data_key = self._data_key
        if data_key in _INTEGER_KEYS:
            return _try_int(value)
        if data_key in _FLOAT_KEYS:
            return _try_float(value)
        return str(value)

    def _coerce_forecast(self, values: list[object]) -> list[object]:
        """Coerce a list of forecast values to the appropriate Python types."""
        data_key = self._data_key
        if data_key in _INTEGER_KEYS:
            return [_try_int(v) for v in values]
        if data_key in _FLOAT_KEYS:
            return [_try_float(v) for v in values]
        return values

    # ------------------------------------------------------------------
    # Extra state attributes
    # ------------------------------------------------------------------

    def _compute_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}

        forecast = self._forecast()
        data_key = self._data_key

        attributes: dict[str, Any] = {
            "region": self._region,
            "last_update": self.coordinator.data.get("last_update"),
        }

        if data_key == "timestamp":
            timestamps = list(forecast.get("timestamp", []))
            attributes["forecast_48h"] = timestamps
            attributes["forecast_count"] = len(timestamps)
        elif data_key in forecast:
            forecast_values = self._coerce_forecast(forecast[data_key])
            attributes["forecast_48h"] = forecast_values
            attributes["forecast_count"] = len(forecast_values)

        return attributes


# ------------------------------------------------------------------
# Module-level conversion helpers
# ------------------------------------------------------------------


def _try_int(value: object) -> int | None:
    """Try to convert *value* to an integer, returning None on failure."""
    try:
        return int(str(value))
    except ValueError, TypeError:
        return None


def _try_float(value: object) -> float | None:
    """Try to convert *value* to a float, returning None on failure."""
    try:
        return float(str(value))
    except ValueError, TypeError:
        return None
