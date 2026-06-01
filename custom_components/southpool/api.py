"""Southpool API Client."""

from __future__ import annotations

import csv
import io
import socket
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
import async_timeout

from .const import (
    API_ENDPOINT_15MIN,
    API_ENDPOINT_HOURLY,
    MINUTES_PER_QUARTER_HOUR,
    SOURCE_TZ,
)


class SouthpoolApiClientError(Exception):
    """Exception to indicate a general API error."""


class SouthpoolApiClientCommunicationError(
    SouthpoolApiClientError,
):
    """Exception to indicate a communication error."""


class SouthpoolApiClientAuthenticationError(
    SouthpoolApiClientError,
):
    """Exception to indicate an authentication error."""


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (401, 403):
        msg = "Invalid credentials"
        raise SouthpoolApiClientAuthenticationError(msg)
    response.raise_for_status()


def _compute_period_start_utc(
    delivery_day: str, interval_value: str, interval_type: str
) -> datetime | None:
    """
    Convert a (Delivery day, Hour|Quarter hour) pair to a UTC datetime.

    HUPX expresses "Delivery day" as a calendar date and "Hour" / "Quarter
    hour" as 1-based indices into that calendar date in local Central European
    time (CET in winter, CEST in summer). Hour 1 covers the period
    [00:00, 01:00) of the delivery day in local time, Hour 24 covers
    [23:00, 24:00), Quarter hour 1 covers [00:00, 00:15) and Quarter hour 96
    covers [23:45, 24:00).

    The returned datetime is timezone-aware (UTC) and points at the START of
    the trading period. Returns None on parsing errors.
    """
    if not delivery_day or interval_value in (None, ""):
        return None
    try:
        # delivery_day looks like "2026-06-01T00:00:00Z"; only the date part is
        # semantically meaningful, the trailing "T00:00:00Z" is API noise.
        base_date = datetime.fromisoformat(delivery_day[:10]).replace(tzinfo=SOURCE_TZ)
        if interval_type == "hourly":
            local_start = base_date + timedelta(hours=int(interval_value) - 1)
        else:
            local_start = base_date + timedelta(
                minutes=(int(interval_value) - 1) * MINUTES_PER_QUARTER_HOUR
            )
    except ValueError, TypeError:
        return None
    return local_start.astimezone(UTC)


class SouthpoolApiClient:
    """Southpool API Client."""

    def __init__(
        self,
        region: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the API Client."""
        self._region = region
        self._session = session
        self._base_url_15min = API_ENDPOINT_15MIN
        self._base_url_hourly = API_ENDPOINT_HOURLY

    async def async_get_data(self) -> dict[str, Any]:
        """Get 48 hours of trading data for the configured region (today + tomorrow)."""
        # Use the source timezone for date calculations since API delivery
        # days are expressed in local Central European time.
        now_local = datetime.now(SOURCE_TZ)
        today = now_local.strftime("%Y-%m-%d")
        tomorrow = (now_local + timedelta(days=1)).strftime("%Y-%m-%d")

        # Build the filter parameter for 48 hours
        filter_param = (
            f"DeliveryDay__gte__{today},"
            f"DeliveryDay__lte__{tomorrow},"
            f"Region__in__{self._region}"
        )

        # Fetch both 15-minute and hourly data
        url_15min = f"{self._base_url_15min}?filter={filter_param}"
        url_hourly = f"{self._base_url_hourly}?filter={filter_param}"

        data_15min = await self._api_wrapper("get", url_15min, interval_type="15min")
        data_hourly = await self._api_wrapper("get", url_hourly, interval_type="hourly")

        # Combine both datasets
        return {
            "region": self._region,
            "data_15min": data_15min,
            "data_hourly": data_hourly,
            "api_fetch_time": datetime.now(UTC).isoformat(),
        }

    async def async_get_data_for_date(self, date: str) -> dict[str, Any]:
        """Get trading data for a specific date."""
        filter_param = (
            f"DeliveryDay__gte__{date},"
            f"DeliveryDay__lte__{date},"
            f"Region__in__{self._region}"
        )

        # Fetch both 15-minute and hourly data
        url_15min = f"{self._base_url_15min}?filter={filter_param}"
        url_hourly = f"{self._base_url_hourly}?filter={filter_param}"

        data_15min = await self._api_wrapper("get", url_15min, interval_type="15min")
        data_hourly = await self._api_wrapper("get", url_hourly, interval_type="hourly")

        # Combine both datasets
        return {
            "region": self._region,
            "data_15min": data_15min,
            "data_hourly": data_hourly,
            "api_fetch_time": datetime.now(UTC).isoformat(),
        }

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        *,
        interval_type: str,
    ) -> dict[str, Any]:
        """Get information from the API."""
        try:
            async with async_timeout.timeout(30):  # Increased timeout for CSV download
                response = await self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                )
                _verify_response_or_raise(response)

                # Get CSV content as text
                csv_content = await response.text()

                # Parse CSV content
                return self._parse_csv_data(csv_content, interval_type)

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise SouthpoolApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise SouthpoolApiClientCommunicationError(msg) from exception
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            raise SouthpoolApiClientError(msg) from exception

    def _parse_csv_data(self, csv_content: str, interval_type: str) -> dict[str, Any]:
        """
        Parse CSV content and pre-compute UTC timestamps for each record.

        Each returned record has the original CSV fields plus:
        - ``period_start``: aware UTC ``datetime`` for the start of the
          trading period, or ``None`` if it could not be parsed.
        - ``period_start_iso``: ISO 8601 representation of ``period_start``
          (empty string if unavailable).
        """
        try:
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            interval_key = "Hour" if interval_type == "hourly" else "Quarter hour"
            records: list[dict[str, Any]] = []
            for row in csv_reader:
                period_start = _compute_period_start_utc(
                    row.get("Delivery day", ""),
                    row.get(interval_key, ""),
                    interval_type,
                )
                row["period_start"] = period_start
                row["period_start_iso"] = (
                    period_start.isoformat() if period_start else ""
                )
                records.append(row)

            return {
                "data_count": len(records),
                "records": records,
            }

        except Exception as exception:
            msg = f"Error parsing CSV data: {exception}"
            raise SouthpoolApiClientError(msg) from exception
