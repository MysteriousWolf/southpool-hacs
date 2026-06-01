"""DataUpdateCoordinator for Southpool with efficient data fetching."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
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
    FORECAST_HOURS,
    MINUTES_PER_QUARTER_HOUR,
    QUARTER_HOUR_RECOVERY_THRESHOLD,
    SECONDS_PER_MINUTE,
    SOURCE_TZ,
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
        api_client: Any = None,
    ) -> None:
        """Initialize the coordinator."""
        # Disable built-in updates - we use custom scheduling
        super().__init__(hass, logger, name=name, update_interval=None)
        self._api_client = api_client
        self._quarter_hour_task = None
        self._api_fetch_task = None
        self._cached_api_data = None
        self._last_api_fetch: datetime | None = None
        self._update_lock = asyncio.Lock()

    async def _async_update_data(self) -> Any:
        """Update current values from cached data without API call."""
        async with self._update_lock:
            # If we don't have cached data, return empty structure
            if self._cached_api_data is None:
                self.logger.warning("No cached data available for sensor update")
                return {
                    "region": self.config_entry.data.get("region", "Unknown"),
                    "data_count": 0,
                    "records": [],
                    "current_values": {},
                    "forecast_48h": {},
                    "last_update": datetime.now(UTC).isoformat(),
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
            self._last_api_fetch = datetime.now(UTC)
        except SouthpoolApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except SouthpoolApiClientError as exception:
            raise UpdateFailed(exception) from exception
        else:
            return data

    @staticmethod
    def _period_length(interval_type: str) -> timedelta:
        """Return the trading period length for the given interval type."""
        if interval_type == "hourly":
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
        """
        Return the latest record whose period has already started.

        Used when no record currently covers ``now_utc`` (e.g., the API has
        not yet published data for the current period). Falls back to the
        first record overall if nothing has started yet.
        """
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
        # Nothing has started yet - return the earliest known record so the
        # sensor still has *something* to show.
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
        self, record: dict[str, Any], interval_type: str
    ) -> dict[str, Any]:
        """Build the ``current_values`` payload from a single record."""
        interval_key = "Hour" if interval_type == "hourly" else "Quarter hour"
        interval_field = "hour" if interval_type == "hourly" else "quarter_hour"
        return {
            "timestamp": record.get("period_start_iso", ""),
            "period_start": record.get("period_start"),
            "delivery_day": record.get("Delivery day", ""),
            interval_field: record.get(interval_key, ""),
            "price": record.get("Price", ""),
            "traded_volume": record.get("Traded volume", ""),
            "baseload_price": record.get("Baseload price", ""),
            "status": record.get("Status", ""),
        }

    def _build_forecast_data(
        self,
        sorted_rows: list[dict[str, Any]],
        current_record: dict[str, Any],
        interval_type: str,
    ) -> dict[str, Any]:
        """Build 48-hour forecast data starting at the current record."""
        try:
            current_index = sorted_rows.index(current_record)
        except ValueError:
            current_index = 0

        records_count = (
            FORECAST_HOURS if interval_type == "hourly" else FORECAST_HOURS * 4
        )
        next_records = sorted_rows[current_index : current_index + records_count]

        interval_key = "Hour" if interval_type == "hourly" else "Quarter hour"
        interval_field = "hour" if interval_type == "hourly" else "quarter_hour"

        result: dict[str, Any] = {
            "timestamp": [r.get("period_start_iso", "") for r in next_records],
            "delivery_day": [r.get("Delivery day", "") for r in next_records],
            "price": [r.get("Price", "") for r in next_records],
            "traded_volume": [r.get("Traded volume", "") for r in next_records],
            "baseload_price": [r.get("Baseload price", "") for r in next_records],
            "status": [r.get("Status", "") for r in next_records],
            interval_field: [r.get(interval_key, "") for r in next_records],
        }
        return result

    def _process_interval(
        self,
        records: list[dict[str, Any]],
        now_utc: datetime,
        interval_type: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (current_values, forecast_48h) for the given interval type."""
        if not records:
            return {}, {}

        # Sort chronologically by the pre-computed UTC start. Records that
        # failed to parse a timestamp are sorted to the end and ignored.
        sentinel = datetime.max.replace(tzinfo=UTC)
        sorted_rows = sorted(
            records,
            key=lambda r: r.get("period_start") or sentinel,
        )

        current_record = self._find_current_record(sorted_rows, now_utc, interval_type)
        if current_record is None:
            current_record = self._get_fallback_record(
                sorted_rows, now_utc, interval_type
            )

        if current_record is None:
            return {}, {}

        current_values = self._build_current_values(current_record, interval_type)
        forecast = self._build_forecast_data(sorted_rows, current_record, interval_type)
        return current_values, forecast

    def _update_current_values(self, api_data: dict[str, Any]) -> dict[str, Any]:
        """Update current values based on current time without API call."""
        if not api_data:
            return api_data

        now_utc = datetime.now(UTC)

        data_15min = api_data.get("data_15min") or {}
        data_hourly = api_data.get("data_hourly") or {}

        current_values_15min, forecast_48h_15min = self._process_interval(
            data_15min.get("records", []), now_utc, "15min"
        )
        current_values_hourly, forecast_48h_hourly = self._process_interval(
            data_hourly.get("records", []), now_utc, "hourly"
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

    def _calculate_next_quarter_hour(self) -> datetime:
        """Calculate the next quarter hour mark (00, 15, 30, or 45 minutes) in UTC."""
        now = datetime.now(UTC)
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
        time_since_fetch = datetime.now(UTC) - self._last_api_fetch
        should_fetch = time_since_fetch >= timedelta(hours=API_FETCH_INTERVAL_HOURS)

        self.logger.debug(
            "Time since last API fetch: %s minutes, should fetch: %s",
            round(time_since_fetch.total_seconds() / SECONDS_PER_MINUTE, 1),
            should_fetch,
        )

        return should_fetch

    @staticmethod
    def _format_local(dt: datetime) -> str:
        """Format a UTC datetime as a local HH:MM:SS string for logs."""
        return dt.astimezone(SOURCE_TZ).strftime("%H:%M:%S")

    async def _schedule_quarter_hour_updates(self) -> None:
        """Schedule updates at quarter hour intervals."""
        self.logger.info("Quarter hour scheduler task started")
        while True:
            try:
                # Calculate time until next quarter hour
                next_quarter = self._calculate_next_quarter_hour()
                now = datetime.now(UTC)
                wait_seconds = (next_quarter - now).total_seconds()

                self.logger.debug(
                    "Next quarter hour update scheduled for %s (in %.1f seconds)",
                    self._format_local(next_quarter),
                    wait_seconds,
                )

                # If we're way past the scheduled time (e.g., after sleep/wake),
                # trigger update immediately and recalculate next time
                if wait_seconds < QUARTER_HOUR_RECOVERY_THRESHOLD:
                    self.logger.info(
                        "Delayed scheduling detected (%.1fs past), triggering recovery",
                        abs(wait_seconds),
                    )
                    current_time = datetime.now(UTC)
                    self.logger.info(
                        "Quarter hour update triggered at %s (recovery)",
                        self._format_local(current_time),
                    )
                    try:
                        async with self._update_lock:
                            await self.async_request_refresh()
                        self.logger.info(
                            "Sensors refreshed successfully at %s",
                            self._format_local(current_time),
                        )
                    except Exception:
                        self.logger.exception("Failed to refresh sensors")
                    continue

                # Wait until next quarter hour, with adjustment to avoid drift
                sleep_time = max(0.05, wait_seconds - 0.1)
                await asyncio.sleep(sleep_time)

                # Final precision wait to hit exact quarter hour
                now = datetime.now(UTC)
                remaining = (next_quarter - now).total_seconds()
                if remaining > 0:
                    await asyncio.sleep(remaining)

                current_time = datetime.now(UTC)
                self.logger.info(
                    "Quarter hour update triggered at %s",
                    self._format_local(current_time),
                )
                try:
                    async with self._update_lock:
                        await self.async_request_refresh()
                    self.logger.info(
                        "Sensors refreshed successfully at %s",
                        self._format_local(current_time),
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
                # Calculate time until next hour (in UTC)
                now = datetime.now(UTC)
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(
                    hours=1
                )
                wait_seconds = (next_hour - now).total_seconds()

                self.logger.debug(
                    "Next hourly API fetch scheduled for %s (in %s seconds)",
                    self._format_local(next_hour),
                    round(wait_seconds, 1),
                )

                # If we're way past the scheduled time (e.g., after sleep/wake),
                # trigger fetch immediately and recalculate next time
                if wait_seconds < API_FETCH_RECOVERY_THRESHOLD:
                    self.logger.info(
                        "Delayed API fetch (%.1fs past), triggering recovery",
                        abs(wait_seconds),
                    )
                    async with self._update_lock:
                        await self._fetch_api_data()
                    self.logger.info(
                        "Completed hourly API data fetch at %s (recovery)",
                        self._format_local(datetime.now(UTC)),
                    )
                    continue
                # Wait until next hour, with adjustment to avoid drift
                sleep_time = max(0.05, wait_seconds - 0.1)
                await asyncio.sleep(sleep_time)

                # Final precision wait to hit exact hour
                now = datetime.now(UTC)
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
                        self._format_local(datetime.now(UTC)),
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
