"""DataUpdateCoordinator for southpool_hacs with efficient data fetching."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .api import (
    SouthpoolApiClientAuthenticationError,
    SouthpoolApiClientError,
)

if TYPE_CHECKING:
    from .data import SouthpoolConfigEntry


class SouthpoolDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API with efficient scheduling."""

    config_entry: SouthpoolConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        logger,
        name: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        # Set update interval to 15 minutes for sensor updates
        super().__init__(hass, logger, name=name, update_interval=timedelta(minutes=15))
        self._quarter_hour_task = None
        self._api_fetch_task = None
        self._cached_api_data = None
        self._last_api_fetch = None

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
                "last_update": datetime.now().isoformat(),
                "last_api_fetch": None,
            }

        # Recalculate current values from cached data
        self.logger.debug("Updating current values from cached data")
        result = self._update_current_values(self._cached_api_data)

        # Log current quarter hour for debugging
        current_values = result.get("current_values", {})
        quarter_hour = current_values.get("quarter_hour", "Unknown")
        self.logger.debug("Current quarter hour: %s", quarter_hour)

        return result

    async def _fetch_api_data(self) -> Any:
        """Fetch fresh data from the API."""
        try:
            self.logger.debug("Fetching fresh data from Southpool API")
            data = await self.config_entry.runtime_data.client.async_get_data()
            self._cached_api_data = data
            self._last_api_fetch = datetime.now()
            return data
        except SouthpoolApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except SouthpoolApiClientError as exception:
            raise UpdateFailed(exception) from exception

    def _update_current_values(self, api_data: dict[str, Any]) -> dict[str, Any]:
        """Update current values based on current time without API call."""
        if not api_data or "records" not in api_data:
            return api_data

        records = api_data["records"]
        if not records:
            return api_data

        # Sort records by delivery day and quarter hour
        sorted_rows = sorted(records, key=lambda x: (x.get("Delivery day", ""), int(x.get("Quarter hour", 0))))

        # Get current quarter hour (1-96 based on current time)
        now = datetime.now()
        current_quarter = ((now.hour * 60 + now.minute) // 15) + 1

        self.logger.debug(
            "Current time: %s, calculated quarter hour: %s",
            now.strftime("%Y-%m-%d %H:%M:%S"),
            current_quarter
        )

        # Find current record (today's current quarter hour)
        today_str = now.strftime("%Y-%m-%d")
        current_record = None

        for row in sorted_rows:
            row_date = row.get("Delivery day", "")[:10]  # Extract date part
            row_quarter = int(row.get("Quarter hour", 0))

            if row_date == today_str and row_quarter == current_quarter:
                current_record = row
                self.logger.debug("Found exact match for quarter hour %s", current_quarter)
                break

        # If no exact current record, use the latest available from today
        if not current_record:
            today_records = [r for r in sorted_rows if r.get("Delivery day", "")[:10] == today_str]
            if today_records:
                current_record = today_records[-1]
                self.logger.debug(
                    "No exact match found, using latest record for today: quarter hour %s",
                    current_record.get("Quarter hour", "Unknown")
                )
            else:
                current_record = sorted_rows[0] if sorted_rows else {}
                self.logger.debug("No today records found, using first available record")

        # Extract current values
        delivery_day = current_record.get("Delivery day", "")
        quarter_hour = current_record.get("Quarter hour", "")

        # Calculate timestamp from delivery day and quarter hour
        timestamp = ""
        if delivery_day and quarter_hour:
            try:
                base_date = datetime.fromisoformat(delivery_day.replace('Z', '+00:00'))
                minutes_offset = (int(quarter_hour) - 1) * 15
                timestamp = (base_date + timedelta(minutes=minutes_offset)).isoformat()
            except (ValueError, TypeError):
                pass

        current_values = {
            "timestamp": timestamp,
            "delivery_day": delivery_day,
            "quarter_hour": quarter_hour,
            "price": current_record.get("Price", ""),
            "traded_volume": current_record.get("Traded volume", ""),
            "baseload_price": current_record.get("Baseload price", ""),
            "status": current_record.get("Status", ""),
        }

        # Build 48-hour forecasts (next 48 hours from current quarter)
        current_index = sorted_rows.index(current_record) if current_record in sorted_rows else 0
        next_48h_records = sorted_rows[current_index:current_index + 192]  # 48 hours * 4 quarters = 192

        # Calculate timestamps for forecast
        timestamp_list = []
        for r in next_48h_records:
            delivery_day = r.get("Delivery day", "")
            quarter_hour = r.get("Quarter hour", "")
            if delivery_day and quarter_hour:
                try:
                    base_date = datetime.fromisoformat(delivery_day.replace('Z', '+00:00'))
                    minutes_offset = (int(quarter_hour) - 1) * 15
                    timestamp = (base_date + timedelta(minutes=minutes_offset)).isoformat()
                    timestamp_list.append(timestamp)
                except (ValueError, TypeError):
                    timestamp_list.append("")
            else:
                timestamp_list.append("")

        forecast_48h = {
            "timestamp": timestamp_list,
            "delivery_day": [r.get("Delivery day", "") for r in next_48h_records],
            "quarter_hour": [r.get("Quarter hour", "") for r in next_48h_records],
            "price": [r.get("Price", "") for r in next_48h_records],
            "traded_volume": [r.get("Traded volume", "") for r in next_48h_records],
            "baseload_price": [r.get("Baseload price", "") for r in next_48h_records],
            "status": [r.get("Status", "") for r in next_48h_records],
        }

        # Return updated data structure
        return {
            "region": api_data.get("region"),
            "data_count": len(records),
            "records": records,
            "current_values": current_values,
            "forecast_48h": forecast_48h,
            "last_update": datetime.now().isoformat(),
            "last_api_fetch": self._last_api_fetch.isoformat() if self._last_api_fetch else None,
        }

    def _calculate_next_quarter_hour(self) -> datetime:
        """Calculate the next quarter hour mark (00, 15, 30, or 45 minutes)."""
        now = datetime.now()
        current_minute = now.minute

        # Find next quarter hour mark
        next_quarter_minute = ((current_minute // 15) + 1) * 15

        if next_quarter_minute == 60:
            # Next hour
            next_quarter = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            # Same hour
            next_quarter = now.replace(minute=next_quarter_minute, second=0, microsecond=0)

        return next_quarter

    def _should_fetch_api_data(self) -> bool:
        """Determine if we need to fetch fresh API data."""
        if self._cached_api_data is None or self._last_api_fetch is None:
            return True

        # Fetch new data every hour
        time_since_fetch = datetime.now() - self._last_api_fetch
        should_fetch = time_since_fetch >= timedelta(hours=1)

        self.logger.debug(
            "Time since last API fetch: %s minutes, should fetch: %s",
            round(time_since_fetch.total_seconds() / 60, 1),
            should_fetch
        )

        return should_fetch

    async def _schedule_quarter_hour_updates(self) -> None:
        """Schedule updates to happen exactly on quarter hour marks."""
        self.logger.info("Quarter hour scheduler task started")
        while True:
            try:
                # Calculate time until next quarter hour
                next_quarter = self._calculate_next_quarter_hour()
                now = datetime.now()
                wait_seconds = (next_quarter - now).total_seconds()

                self.logger.debug(
                    "Next quarter hour update scheduled for %s (in %s seconds)",
                    next_quarter.strftime("%H:%M:%S"),
                    round(wait_seconds, 1)
                )

                # Wait until the next quarter hour
                await asyncio.sleep(max(0.1, wait_seconds))

                current_time = datetime.now()
                self.logger.info("Quarter hour update triggered at %s", current_time.strftime("%H:%M:%S"))

                # Trigger sensor update exactly at quarter hour mark (no API calls)
                try:
                    await self.async_refresh()
                    self.logger.info("Sensors refreshed successfully at %s", current_time.strftime("%H:%M:%S"))
                except Exception as refresh_err:
                    self.logger.error("Failed to refresh sensors: %s", refresh_err)

            except asyncio.CancelledError:
                self.logger.debug("Quarter hour update task cancelled")
                break
            except Exception as err:
                self.logger.error("Error in quarter hour scheduler: %s", err)
                # Wait a bit before retrying
                await asyncio.sleep(60)

    async def _schedule_hourly_api_fetch(self) -> None:
        """Schedule API fetches every hour on the hour."""
        while True:
            try:
                # Calculate time until next hour
                now = datetime.now()
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                wait_seconds = (next_hour - now).total_seconds()

                self.logger.debug(
                    "Next hourly API fetch scheduled for %s (in %s seconds)",
                    next_hour.strftime("%H:%M:%S"),
                    round(wait_seconds, 1)
                )

                # Wait until the next hour
                await asyncio.sleep(max(0.1, wait_seconds))

                # Fetch fresh API data independently of sensor updates
                try:
                    await self._fetch_api_data()
                    self.logger.info("Completed hourly API data fetch at %s", datetime.now().strftime("%H:%M:%S"))
                except Exception as api_err:
                    self.logger.error("Failed hourly API fetch: %s", api_err)

            except asyncio.CancelledError:
                self.logger.debug("Hourly API fetch task cancelled")
                break
            except Exception as err:
                self.logger.error("Error in hourly API fetch scheduler: %s", err)
                # Wait a bit before retrying
                await asyncio.sleep(300)  # 5 minutes

    async def async_config_entry_first_refresh(self) -> None:
        """Perform first refresh and start scheduling tasks."""
        self.logger.info("Starting coordinator initialization")

        # Do immediate API fetch to populate cache
        self.logger.info("Performing initial API data fetch")
        try:
            await self._fetch_api_data()
            self.logger.info("Initial API data fetch completed successfully")
        except Exception as err:
            self.logger.error("Initial API fetch failed: %s", err)

        # Do initial sensor update with fetched data
        self.logger.info("Performing initial sensor update")
        await super().async_config_entry_first_refresh()
        self.logger.info("Initial sensor update completed")

        # Start quarter hour synchronization
        if self._quarter_hour_task is None or self._quarter_hour_task.done():
            self.logger.info("Starting quarter hour synchronization task")
            self._quarter_hour_task = asyncio.create_task(self._schedule_quarter_hour_updates())
            self.logger.debug("Quarter hour task created: %s", self._quarter_hour_task)

        # Start hourly API fetch scheduling
        if self._api_fetch_task is None or self._api_fetch_task.done():
            self.logger.info("Starting hourly API fetch task")
            self._api_fetch_task = asyncio.create_task(self._schedule_hourly_api_fetch())
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
            try:
                await task
            except asyncio.CancelledError:
                pass
