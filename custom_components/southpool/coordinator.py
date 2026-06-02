"""DataUpdateCoordinator for Southpool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SouthpoolApiClientAuthenticationError,
    SouthpoolApiClientError,
)
from .const import (
    DEFAULT_UPDATE_INTERVAL,
    FIELD_BASELOAD_PRICE,
    FIELD_DELIVERY_DAY,
    FIELD_HOUR,
    FIELD_PRICE,
    FIELD_QUARTER_HOUR,
    FIELD_STATUS,
    FIELD_TRADED_VOLUME,
    FORECAST_HOURS,
    INTERVAL_HOURLY,
    MINUTES_PER_QUARTER_HOUR,
)

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

    from .api import SouthpoolApiClient
    from .data import SouthpoolConfigEntry


class SouthpoolDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    config_entry: SouthpoolConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        *,
        api_client: SouthpoolApiClient,
        update_interval_minutes: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, logger, name=name)
        self._api_client = api_client
        self._cached_api_data: dict[str, Any] | None = None
        self._last_api_fetch: datetime | None = None
        self._unsub_update: Callable[[], None] | None = None
        self._update_interval_minutes = update_interval_minutes

    def _schedule_next_update(self) -> None:
        """Schedule the next boundary-aligned refresh."""
        if self._unsub_update is not None:
            self._unsub_update()

        now = datetime.now(UTC)
        interval = self._update_interval_minutes

        # Compute the next boundary that is strictly in the future.
        # e.g. interval=15 → boundaries at :00, :15, :30, :45
        current_boundary_minute = (now.minute // interval) * interval
        next_boundary = now.replace(
            minute=current_boundary_minute, second=0, microsecond=0
        ) + timedelta(minutes=interval)

        delay_seconds = max(1.0, (next_boundary - now).total_seconds())

        self.logger.debug(
            "Next data update scheduled for %s (in %d seconds)",
            next_boundary.strftime("%Y-%m-%d %H:%M:%S UTC"),
            int(delay_seconds),
        )
        self._unsub_update = async_call_later(
            self.hass,
            delay_seconds,
            self._async_boundary_refresh,
        )

    async def _async_boundary_refresh(self, _now: datetime) -> None:
        """Handle a boundary-aligned timer fire."""
        await self.async_refresh()
        self._schedule_next_update()

    async def async_config_entry_first_refresh(self) -> None:
        """Fetch initial data and schedule the first boundary-aligned update."""
        await super().async_config_entry_first_refresh()
        self._schedule_next_update()

    async def async_shutdown(self) -> None:
        """Cancel pending updates and shut down the coordinator."""
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None
        await super().async_shutdown()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data if stale, then compute current values from cache."""
        if self._should_refresh_api():
            await self._fetch_api_data()

        if self._cached_api_data is None:
            msg = "No API data available yet"
            raise UpdateFailed(msg)

        result = self._update_current_values(self._cached_api_data)
        self.logger.debug(
            "Current quarter hour: %s, hour: %s",
            result.get("current_values_15min", {}).get("quarter_hour", "Unknown"),
            result.get("current_values_hourly", {}).get("hour", "Unknown"),
        )
        return result

    def _should_refresh_api(self) -> bool:
        """Return True if the API cache is missing or older than 1 hour."""
        if self._cached_api_data is None or self._last_api_fetch is None:
            return True
        return datetime.now(UTC) - self._last_api_fetch >= timedelta(hours=1)

    async def _fetch_api_data(self) -> dict[str, Any]:
        """Fetch fresh data from the API and update the cache."""
        self.logger.debug("Fetching fresh data from Southpool API")
        try:
            data = await self._api_client.async_get_data()
        except SouthpoolApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except SouthpoolApiClientError as exception:
            raise UpdateFailed(exception) from exception
        self._cached_api_data = data
        self._last_api_fetch = datetime.now(UTC)
        return data

    @staticmethod
    def _period_length(interval_type: str) -> timedelta:
        if interval_type == INTERVAL_HOURLY:
            return timedelta(hours=1)
        return timedelta(minutes=MINUTES_PER_QUARTER_HOUR)

    def _find_current_record(
        self,
        sorted_rows: list[dict[str, Any]],
        now_utc: datetime,
        interval_type: str,
    ) -> dict[str, Any] | None:
        """Find the record whose trading period contains ``now_utc``."""
        period_length = self._period_length(interval_type)
        for row in sorted_rows:
            start = row.get("period_start")
            if not isinstance(start, datetime):
                continue
            if start <= now_utc < start + period_length:
                self.logger.debug(
                    "Found current %s record starting at %s",
                    interval_type,
                    start.isoformat(),
                )
                return row
        return None

    def _get_fallback_record(
        self,
        sorted_rows: list[dict[str, Any]],
        now_utc: datetime,
        interval_type: str,
    ) -> dict[str, Any] | None:
        """Return the latest record whose period has already started."""
        started_rows = [
            r
            for r in sorted_rows
            if isinstance(r.get("period_start"), datetime)
            and r["period_start"] <= now_utc
        ]
        if started_rows:
            record = started_rows[-1]
            self.logger.debug(
                "No exact match found, using latest started %s record at %s",
                interval_type,
                record["period_start"].isoformat(),
            )
            return record
        for row in sorted_rows:
            if isinstance(row.get("period_start"), datetime):
                self.logger.debug(
                    "No started %s records yet, using earliest at %s",
                    interval_type,
                    row["period_start"].isoformat(),
                )
                return row
        return None

    def _build_current_values(
        self,
        record: dict[str, Any],
        interval_type: str,
    ) -> dict[str, Any]:
        interval_key = (
            FIELD_HOUR if interval_type == INTERVAL_HOURLY else FIELD_QUARTER_HOUR
        )
        interval_field = "hour" if interval_type == INTERVAL_HOURLY else "quarter_hour"
        return {
            "timestamp": record.get("period_start_iso", ""),
            "period_start": record.get("period_start"),
            "delivery_day": record.get(FIELD_DELIVERY_DAY, ""),
            interval_field: record.get(interval_key, ""),
            "price": record.get(FIELD_PRICE, ""),
            "traded_volume": record.get(FIELD_TRADED_VOLUME, ""),
            "baseload_price": record.get(FIELD_BASELOAD_PRICE, ""),
            "status": record.get(FIELD_STATUS, ""),
        }

    def _build_forecast_data(
        self,
        sorted_rows: list[dict[str, Any]],
        current_record: dict[str, Any],
        interval_type: str,
    ) -> dict[str, Any]:
        try:
            current_index = sorted_rows.index(current_record)
        except ValueError:
            current_index = 0

        records_count = (
            FORECAST_HOURS if interval_type == INTERVAL_HOURLY else FORECAST_HOURS * 4
        )
        next_records = sorted_rows[current_index : current_index + records_count]

        interval_key = (
            FIELD_HOUR if interval_type == INTERVAL_HOURLY else FIELD_QUARTER_HOUR
        )
        interval_field = "hour" if interval_type == INTERVAL_HOURLY else "quarter_hour"

        return {
            "timestamp": [r.get("period_start_iso", "") for r in next_records],
            "delivery_day": [r.get(FIELD_DELIVERY_DAY, "") for r in next_records],
            "price": [r.get(FIELD_PRICE, "") for r in next_records],
            "traded_volume": [r.get(FIELD_TRADED_VOLUME, "") for r in next_records],
            "baseload_price": [r.get(FIELD_BASELOAD_PRICE, "") for r in next_records],
            "status": [r.get(FIELD_STATUS, "") for r in next_records],
            interval_field: [r.get(interval_key, "") for r in next_records],
        }

    def _process_interval(
        self,
        records: list[dict[str, Any]],
        now_utc: datetime,
        interval_type: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not records:
            return {}, {}

        sentinel = datetime.max.replace(tzinfo=UTC)
        sorted_rows = sorted(
            records,
            key=lambda r: r.get("period_start") or sentinel,
        )

        current_record = self._find_current_record(sorted_rows, now_utc, interval_type)
        if current_record is None:
            current_record = self._get_fallback_record(
                sorted_rows,
                now_utc,
                interval_type,
            )

        if current_record is None:
            return {}, {}

        current_values = self._build_current_values(current_record, interval_type)
        forecast = self._build_forecast_data(sorted_rows, current_record, interval_type)
        return current_values, forecast

    def _update_current_values(self, api_data: dict[str, Any]) -> dict[str, Any]:
        if not api_data:
            return api_data

        now_utc = datetime.now(UTC)

        data_15min = api_data.get("data_15min") or {}
        data_hourly = api_data.get("data_hourly") or {}

        current_values_15min, forecast_48h_15min = self._process_interval(
            data_15min.get("records", []),
            now_utc,
            "15min",
        )
        current_values_hourly, forecast_48h_hourly = self._process_interval(
            data_hourly.get("records", []),
            now_utc,
            "hourly",
        )

        return {
            "region": api_data.get("region", ""),
            "current_values_15min": current_values_15min,
            "current_values_hourly": current_values_hourly,
            "forecast_48h_15min": forecast_48h_15min,
            "forecast_48h_hourly": forecast_48h_hourly,
            "last_update": now_utc.isoformat(),
            "last_api_fetch": self._last_api_fetch.isoformat()
            if self._last_api_fetch
            else None,
        }
