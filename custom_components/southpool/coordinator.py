"""DataUpdateCoordinator for Southpool with efficient data fetching."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SouthpoolApiClientAuthenticationError,
    SouthpoolApiClientError,
)
from .const import (
    API_FETCH_INTERVAL_HOURS,
    API_FETCH_RECOVERY_THRESHOLD,
    CET_TZ,
    FORECAST_HOURS,
    MINUTES_PER_QUARTER_HOUR,
    QUARTER_HOUR_RECOVERY_THRESHOLD,
    SECONDS_PER_MINUTE,
)

if TYPE_CHECKING:
    import logging

    from homeassistant.core import HomeAssistant

    from .data import SouthpoolConfigEntry


class SouthpoolDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API with efficient scheduling."""

    config_entry: SouthpoolConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        *,
        update_interval: timedelta | None = None,  # noqa: ARG002 Unused function argument: `update_interval`
        api_client: Any = None,
    ) -> None:
        """Initialize the coordinator."""
        # Disable built-in updates - we use custom scheduling
        super().__init__(hass, logger, name=name, update_interval=None)
        self._api_client = api_client
        self._quarter_hour_task = None
        self._api_fetch_task = None
        self._cached_api_data = None
        self._last_api_fetch = None
        self._update_lock = asyncio.Lock()

    async def _async_update_data(self) -> Any:
        """Update current values from cached data without API call."""
        # If we don't have cached data, return empty structure
        if self._cached_api_data is None:
            self.logger.warning("No cached data available for sensor update")
            return {
                "region": self.config_entry.data.get("region", "Unknown"),
                "data_count": 0,
                "records": [],
                "current_values": {},
                "forecast_48h": {},
                "last_update": datetime.now(CET_TZ).isoformat(),
                "last_api_fetch": None,
            }

        # Recalculate current values from cached data
        self.logger.debug("Updating current values from cached data")
        result = self._update_current_values(self._cached_api_data)

        # Log current values for debugging
        current_values_15min = result.get("current_values_15min", {})
        current_values_hourly = result.get("current_values_hourly", {})
        quarter_hour = current_values_15min.get("quarter_hour", "Unknown")
        hour = current_values_hourly.get("hour", "Unknown")
        self.logger.debug("Current quarter hour: %s, hour: %s", quarter_hour, hour)

        return result

    async def _fetch_api_data(self) -> Any:
        """Fetch fresh data from the API."""
        try:
            self.logger.debug("Fetching fresh data from Southpool API")
            data = await self._api_client.async_get_data()
            self._cached_api_data = data
            self._last_api_fetch = datetime.now(CET_TZ)
        except SouthpoolApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except SouthpoolApiClientError as exception:
            raise UpdateFailed(exception) from exception
        else:
            return data

    def _find_current_record(
        self,
        sorted_rows: list[dict[str, Any]],
        today_str: str,
        current_interval: int,
        interval_type: str,
    ) -> dict[str, Any] | None:
        """Find current record for today's interval."""
        for row in sorted_rows:
            row_date = row.get("Delivery day", "")[:10]  # Extract date part

            if interval_type == "hourly":
                row_interval = int(row.get("Hour", 0))
                interval_name = "hour"
            else:
                row_interval = int(row.get("Quarter hour", 0))
                interval_name = "quarter hour"

            if row_date == today_str and row_interval == current_interval:
                self.logger.debug(
                    "Found exact match for %s %s", interval_name, current_interval
                )
                return row
        return None

    def _get_fallback_record(
        self, sorted_rows: list[dict[str, Any]], today_str: str, interval_type: str
    ) -> dict[str, Any] | None:
        """Get latest record for today if no exact match found."""
        today_records = [
            r for r in sorted_rows if r.get("Delivery day", "")[:10] == today_str
        ]
        if today_records:
            record = today_records[-1]
            if interval_type == "hourly":
                interval_value = record.get("Hour", "Unknown")
                interval_name = "hour"
            else:
                interval_value = record.get("Quarter hour", "Unknown")
                interval_name = "quarter hour"
            self.logger.debug(
                "No exact match found, using latest record for today: %s %s",
                interval_name,
                interval_value,
            )
            return record
        return None

    def _calculate_timestamp(
        self, delivery_day: str, interval_value: str, interval_type: str
    ) -> str:
        """Calculate timestamp from delivery day and interval value."""
        if not delivery_day or not interval_value:
            return ""
        try:
            base_date = datetime.fromisoformat(delivery_day[:10]).replace(tzinfo=CET_TZ)
            if interval_type == "hourly":
                # For hourly data, hour is the actual hour (1-24 or 0-23, assume 1-24)
                hour_offset = int(interval_value) - 1  # Convert to 0-based
                return (base_date + timedelta(hours=hour_offset)).isoformat()
            # For 15-minute data, quarter_hour is 1-96
            minutes_offset = (int(interval_value) - 1) * MINUTES_PER_QUARTER_HOUR
            return (base_date + timedelta(minutes=minutes_offset)).isoformat()
        except (ValueError, TypeError):
            return ""

    def _build_forecast_data(
        self,
        sorted_rows: list[dict[str, Any]],
        current_record: dict[str, Any],
        interval_type: str,
    ) -> dict[str, Any]:
        """Build 48-hour forecast data."""
        current_index = (
            sorted_rows.index(current_record) if current_record in sorted_rows else 0
        )

        # Calculate number of records for 48 hours
        records_count = (
            FORECAST_HOURS if interval_type == "hourly" else FORECAST_HOURS * 4
        )

        next_48h_records = sorted_rows[current_index : current_index + records_count]

        timestamp_list = []
        for r in next_48h_records:
            if interval_type == "hourly":
                interval_value = r.get("Hour", "")
            else:
                interval_value = r.get("Quarter hour", "")
            timestamp = self._calculate_timestamp(
                r.get("Delivery day", ""), interval_value, interval_type
            )
            timestamp_list.append(timestamp)

        result = {
            "timestamp": timestamp_list,
            "delivery_day": [r.get("Delivery day", "") for r in next_48h_records],
            "price": [r.get("Price", "") for r in next_48h_records],
            "traded_volume": [r.get("Traded volume", "") for r in next_48h_records],
            "baseload_price": [r.get("Baseload price", "") for r in next_48h_records],
            "status": [r.get("Status", "") for r in next_48h_records],
        }

        # Add interval-specific field
        if interval_type == "hourly":
            result["hour"] = [r.get("Hour", "") for r in next_48h_records]
        else:
            result["quarter_hour"] = [
                r.get("Quarter hour", "") for r in next_48h_records
            ]

        return result

    def _update_current_values(self, api_data: dict[str, Any]) -> dict[str, Any]:
        """Update current values based on current time without API call."""
        if not api_data:
            return api_data

        # Process both 15-minute and hourly data
        data_15min = api_data.get("data_15min", {})
        data_hourly = api_data.get("data_hourly", {})

        now = datetime.now(CET_TZ)
        today_str = now.strftime("%Y-%m-%d")

        # Process 15-minute data
        current_values_15min = {}
        forecast_48h_15min = {}
        if data_15min and data_15min.get("records"):
            records_15min = data_15min["records"]
            sorted_rows_15min = sorted(
                records_15min,
                key=lambda x: (
                    x.get("Delivery day", ""),
                    int(x.get("Quarter hour", 0)),
                ),
            )
            current_quarter = (
                (now.hour * SECONDS_PER_MINUTE + now.minute) // MINUTES_PER_QUARTER_HOUR
            ) + 1

            current_record_15min = self._find_current_record(
                sorted_rows_15min, today_str, current_quarter, "15min"
            )
            if not current_record_15min:
                current_record_15min = self._get_fallback_record(
                    sorted_rows_15min, today_str, "15min"
                )

            if current_record_15min:
                delivery_day = current_record_15min.get("Delivery day", "")
                quarter_hour = current_record_15min.get("Quarter hour", "")
                current_values_15min = {
                    "timestamp": self._calculate_timestamp(
                        delivery_day, quarter_hour, "15min"
                    ),
                    "delivery_day": delivery_day,
                    "quarter_hour": quarter_hour,
                    "price": current_record_15min.get("Price", ""),
                    "traded_volume": current_record_15min.get("Traded volume", ""),
                    "baseload_price": current_record_15min.get("Baseload price", ""),
                    "status": current_record_15min.get("Status", ""),
                }
                forecast_48h_15min = self._build_forecast_data(
                    sorted_rows_15min, current_record_15min, "15min"
                )

        # Process hourly data
        current_values_hourly = {}
        forecast_48h_hourly = {}
        if data_hourly and data_hourly.get("records"):
            records_hourly = data_hourly["records"]
            sorted_rows_hourly = sorted(
                records_hourly,
                key=lambda x: (x.get("Delivery day", ""), int(x.get("Hour", 0))),
            )
            current_hour = now.hour + 1  # Convert 0-23 to 1-24

            current_record_hourly = self._find_current_record(
                sorted_rows_hourly, today_str, current_hour, "hourly"
            )
            if not current_record_hourly:
                current_record_hourly = self._get_fallback_record(
                    sorted_rows_hourly, today_str, "hourly"
                )

            if current_record_hourly:
                delivery_day = current_record_hourly.get("Delivery day", "")
                hour = current_record_hourly.get("Hour", "")
                current_values_hourly = {
                    "timestamp": self._calculate_timestamp(
                        delivery_day, hour, "hourly"
                    ),
                    "delivery_day": delivery_day,
                    "hour": hour,
                    "price": current_record_hourly.get("Price", ""),
                    "traded_volume": current_record_hourly.get("Traded volume", ""),
                    "baseload_price": current_record_hourly.get("Baseload price", ""),
                    "status": current_record_hourly.get("Status", ""),
                }
                forecast_48h_hourly = self._build_forecast_data(
                    sorted_rows_hourly, current_record_hourly, "hourly"
                )

        return {
            "region": api_data.get("region", ""),
            "current_values_15min": current_values_15min,
            "current_values_hourly": current_values_hourly,
            "forecast_48h_15min": forecast_48h_15min,
            "forecast_48h_hourly": forecast_48h_hourly,
            "last_update": datetime.now(CET_TZ).isoformat(),
            "last_api_fetch": self._last_api_fetch.isoformat()
            if self._last_api_fetch
            else None,
        }

    def _calculate_next_quarter_hour(self) -> datetime:
        """Calculate the next quarter hour mark (00, 15, 30, or 45 minutes)."""
        now = datetime.now(CET_TZ)
        current_minute = now.minute

        # Find next quarter hour mark
        next_quarter_minute = (
            (current_minute // MINUTES_PER_QUARTER_HOUR) + 1
        ) * MINUTES_PER_QUARTER_HOUR
        max_minutes = SECONDS_PER_MINUTE

        if next_quarter_minute == max_minutes:
            # Next hour
            return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        # Same hour
        return now.replace(minute=next_quarter_minute, second=0, microsecond=0)

    def _should_fetch_api_data(self) -> bool:
        """Determine if we need to fetch fresh API data."""
        if self._cached_api_data is None or self._last_api_fetch is None:
            return True

        # Fetch new data every hour
        time_since_fetch = datetime.now(CET_TZ) - self._last_api_fetch
        should_fetch = time_since_fetch >= timedelta(hours=API_FETCH_INTERVAL_HOURS)

        self.logger.debug(
            "Time since last API fetch: %s minutes, should fetch: %s",
            round(time_since_fetch.total_seconds() / SECONDS_PER_MINUTE, 1),
            should_fetch,
        )

        return should_fetch

    async def _schedule_quarter_hour_updates(self) -> None:
        """Schedule updates at quarter hour intervals."""
        self.logger.info("Quarter hour scheduler task started")
        while True:
            try:
                # Calculate time until next quarter hour
                next_quarter = self._calculate_next_quarter_hour()
                now = datetime.now(CET_TZ)
                wait_seconds = (next_quarter - now).total_seconds()

                self.logger.debug(
                    "Next quarter hour update scheduled for %s (in %.1f seconds)",
                    next_quarter.strftime("%H:%M:%S"),
                    wait_seconds,
                )

                # If we're way past the scheduled time (e.g., after sleep/wake),
                # trigger update immediately and recalculate next time
                if wait_seconds < QUARTER_HOUR_RECOVERY_THRESHOLD:
                    self.logger.info(
                        "Delayed scheduling detected (%.1fs past), triggering recovery",
                        abs(wait_seconds),
                    )
                    current_time = datetime.now(CET_TZ)
                    self.logger.info(
                        "Quarter hour update triggered at %s (recovery)",
                        current_time.strftime("%H:%M:%S"),
                    )
                else:
                    # Wait until next quarter hour, with adjustment to avoid drift
                    sleep_time = max(0.05, wait_seconds - 0.1)
                    await asyncio.sleep(sleep_time)

                    # Final precision wait to hit exact quarter hour
                    now = datetime.now(CET_TZ)
                    remaining = (next_quarter - now).total_seconds()
                    if remaining > 0:
                        await asyncio.sleep(remaining)

                    current_time = datetime.now(CET_TZ)
                    self.logger.info(
                        "Quarter hour update triggered at %s",
                        current_time.strftime("%H:%M:%S"),
                    )
                try:
                    # Use lock to prevent race conditions with other updates
                    async with self._update_lock:
                        await self.async_request_refresh()
                    self.logger.info(
                        "Sensors refreshed successfully at %s",
                        current_time.strftime("%H:%M:%S"),
                    )
                except Exception:
                    self.logger.exception("Failed to refresh sensors")

            except asyncio.CancelledError:
                self.logger.debug("Quarter hour update task cancelled")
                break
            except Exception:
                self.logger.exception("Error in quarter hour scheduler")
                # Wait a bit before retrying
                await asyncio.sleep(SECONDS_PER_MINUTE)

    async def _schedule_hourly_api_fetch(self) -> None:
        """Schedule API fetches every hour on the hour."""
        while True:
            try:
                # Calculate time until next hour
                now = datetime.now(CET_TZ)
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(
                    hours=1
                )
                wait_seconds = (next_hour - now).total_seconds()

                self.logger.debug(
                    "Next hourly API fetch scheduled for %s (in %s seconds)",
                    next_hour.strftime("%H:%M:%S"),
                    round(wait_seconds, 1),
                )

                # If we're way past the scheduled time (e.g., after sleep/wake),
                # trigger fetch immediately and recalculate next time
                if wait_seconds < API_FETCH_RECOVERY_THRESHOLD:
                    self.logger.info(
                        "Delayed API fetch (%.1fs past), triggering recovery",
                        abs(wait_seconds),
                    )
                    # Trigger immediate fetch
                    await self._fetch_and_update_data()
                    self.logger.info(
                        "Completed hourly API data fetch at %s (recovery)",
                        datetime.now(CET_TZ).strftime("%H:%M:%S"),
                    )
                    # Continue to calculate next proper schedule
                else:
                    # Wait until next hour, with adjustment to avoid drift
                    sleep_time = max(0.05, wait_seconds - 0.1)
                    await asyncio.sleep(sleep_time)

                # Final precision wait to hit exact hour
                now = datetime.now(CET_TZ)
                remaining = (next_hour - now).total_seconds()
                if remaining > 0:
                    await asyncio.sleep(remaining)

                # Fetch fresh API data independently of sensor updates
                try:
                    # Use lock to prevent race conditions with sensor updates
                    async with self._update_lock:
                        await self._fetch_api_data()
                    self.logger.info(
                        "Completed hourly API data fetch at %s",
                        datetime.now(CET_TZ).strftime("%H:%M:%S"),
                    )
                except Exception:
                    self.logger.exception("Failed hourly API fetch")

            except asyncio.CancelledError:
                self.logger.debug("Hourly API fetch task cancelled")
                break
            except Exception:
                self.logger.exception("Error in hourly API fetch scheduler")
                # Wait a bit before retrying
                await asyncio.sleep(5 * SECONDS_PER_MINUTE)  # 5 minutes

    async def async_config_entry_first_refresh(self) -> None:
        """Perform first refresh and start scheduling tasks."""
        self.logger.info("Starting coordinator initialization")

        # Do immediate API fetch to populate cache
        self.logger.info("Performing initial API data fetch")
        try:
            await self._fetch_api_data()
            self.logger.info("Initial API data fetch completed successfully")
        except Exception:
            self.logger.exception("Initial API fetch failed")

        # Do initial sensor update with fetched data
        self.logger.info("Performing initial sensor update")
        await super().async_config_entry_first_refresh()
        self.logger.info("Initial sensor update completed")

        # Start quarter hour synchronization
        if self._quarter_hour_task is None or self._quarter_hour_task.done():
            self.logger.info("Starting quarter hour synchronization task")
            self._quarter_hour_task = asyncio.create_task(
                self._schedule_quarter_hour_updates()
            )
            self.logger.debug("Quarter hour task created: %s", self._quarter_hour_task)

        # Start hourly API fetch scheduling
        if self._api_fetch_task is None or self._api_fetch_task.done():
            self.logger.info("Starting hourly API fetch task")
            self._api_fetch_task = asyncio.create_task(
                self._schedule_hourly_api_fetch()
            )
            self.logger.debug("API fetch task created: %s", self._api_fetch_task)

        self.logger.info("Coordinator initialization completed successfully")

    def _unload(self) -> None:
        """Cancel all tasks when unloading."""
        if self._quarter_hour_task and not self._quarter_hour_task.done():
            self._quarter_hour_task.cancel()
        if self._api_fetch_task and not self._api_fetch_task.done():
            self._api_fetch_task.cancel()
        super()._unload()

    async def _async_unload(self) -> None:
        """Async cleanup when unloading."""
        tasks_to_cancel = []

        if self._quarter_hour_task and not self._quarter_hour_task.done():
            tasks_to_cancel.append(self._quarter_hour_task)

        if self._api_fetch_task and not self._api_fetch_task.done():
            tasks_to_cancel.append(self._api_fetch_task)

        for task in tasks_to_cancel:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
