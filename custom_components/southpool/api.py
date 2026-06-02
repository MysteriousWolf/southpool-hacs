"""Southpool API Client."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import aiohttp
import async_timeout

from .const import (
    API_ENDPOINT_15MIN,
    API_ENDPOINT_HOURLY,
    DEFAULT_DST_CORRECTION,
    DEFAULT_TIME_OFFSET,
    FIELD_DELIVERY_DAY,
    FIELD_HOUR,
    FIELD_QUARTER_HOUR,
    FIXED_CET,
    INTERVAL_15MIN,
    INTERVAL_HOURLY,
    LOGGER,
    MINUTES_PER_QUARTER_HOUR,
    SOURCE_TZ,
)

_LOGGER = logging.getLogger(__name__)

# Hard limits to protect against runaway responses
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB
_CONNECT_TIMEOUT = 10  # seconds - fail fast if server unreachable
_READ_TIMEOUT = 30  # seconds - allow time for CSV download

# Retry configuration for transient errors
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # seconds; exponential backoff: 2, 4, 8 ...


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
    delivery_day: str,
    interval_value: str,
    interval_type: str,
    *,
    dst_correction: bool = True,
    time_offset_hours: int = 0,
) -> datetime | None:
    """
    Convert a (Delivery day, Hour|Quarter hour) pair to a UTC datetime.

    HUPX expresses "Delivery day" as a calendar date and "Hour" / "Quarter
    hour" as 1-based indices into that calendar date in Europe/Budapest local
    time (CET in winter, CEST in summer). Hour 1 covers the period
    [00:00, 01:00) of the delivery day in local time, Hour 24 covers
    [23:00, 24:00), Quarter hour 1 covers [00:00, 00:15) and Quarter hour 96
    covers [23:45, 24:00).

    When *dst_correction* is True (default), the source timezone
    (Europe/Budapest) is used, which automatically handles DST transitions.
    When False, a fixed UTC+1 offset is used instead.

    *time_offset_hours* is added to the final UTC datetime, allowing manual
    adjustment of the parsed timestamp (range: -12 to +12 hours).

    The returned datetime is timezone-aware (UTC) and points at the START of
    the trading period. Returns None on parsing errors.
    """
    if not delivery_day or interval_value in (None, ""):
        return None
    try:
        # Choose timezone: SOURCE_TZ (with DST) or fixed CET (without DST).
        tz = SOURCE_TZ if dst_correction else FIXED_CET
        # delivery_day looks like "2026-06-01T00:00:00Z"; only the date part is
        # semantically meaningful, the trailing "T00:00:00Z" is API noise.
        base_date = datetime.fromisoformat(delivery_day[:10]).replace(tzinfo=tz)
        if interval_type == "hourly":
            local_start = base_date + timedelta(hours=int(interval_value) - 1)
        else:
            local_start = base_date + timedelta(
                minutes=(int(interval_value) - 1) * MINUTES_PER_QUARTER_HOUR,
            )
    except ValueError, TypeError:
        return None
    result = local_start.astimezone(UTC)
    if time_offset_hours:
        result = result + timedelta(hours=time_offset_hours)
    return result


class SouthpoolApiClient:
    """Southpool API Client."""

    def __init__(
        self,
        region: str,
        session: aiohttp.ClientSession,
        *,
        dst_correction: bool = DEFAULT_DST_CORRECTION,
        time_offset_hours: int = DEFAULT_TIME_OFFSET,
    ) -> None:
        """Initialize the API Client."""
        self._region = region
        self._session = session
        self._dst_correction = dst_correction
        self._time_offset_hours = time_offset_hours
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
        params = {"filter": filter_param}
        url_15min = f"{self._base_url_15min}?{urlencode(params)}"
        url_hourly = f"{self._base_url_hourly}?{urlencode(params)}"

        data_15min = await self._api_wrapper(url_15min, interval_type=INTERVAL_15MIN)
        data_hourly = await self._api_wrapper(url_hourly, interval_type=INTERVAL_HOURLY)

        # Combine both datasets
        return {
            "region": self._region,
            "data_15min": data_15min,
            "data_hourly": data_hourly,
            "api_fetch_time": datetime.now(UTC).isoformat(),
        }

    async def _api_wrapper(
        self,
        url: str,
        *,
        interval_type: str,
    ) -> dict[str, Any]:
        """Get information from the API with retry logic for transient errors."""
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await self._do_request(url, interval_type=interval_type)
            except SouthpoolApiClientAuthenticationError:
                # Auth errors should not be retried
                raise
            except SouthpoolApiClientCommunicationError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF_BASE**attempt
                    _LOGGER.debug(
                        "Attempt %d/%d failed (%s), retrying in %ds",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
            except SouthpoolApiClientError:
                raise

        # All retries exhausted
        raise last_exc  # type: ignore[misc]

    async def _do_request(
        self,
        url: str,
        *,
        interval_type: str,
    ) -> dict[str, Any]:
        """Execute a single HTTP request with size and timeout guards."""
        try:
            # Phase 1: connect (short timeout)
            async with async_timeout.timeout(_CONNECT_TIMEOUT):
                response = await self._session.request(
                    method="get",
                    url=url,
                )
                _verify_response_or_raise(response)

            # Phase 2: read body (longer timeout, with size guard)
            async with async_timeout.timeout(_READ_TIMEOUT):
                raw = await response.content.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    msg = (
                        f"Response exceeds {_MAX_RESPONSE_BYTES} byte limit "
                        f"({len(raw)} bytes received)"
                    )
                    raise SouthpoolApiClientError(msg)  # noqa: TRY301
                csv_content = raw.decode("utf-8", errors="replace")

            return self._parse_csv_data(csv_content, interval_type)

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise SouthpoolApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise SouthpoolApiClientCommunicationError(msg) from exception
        except SouthpoolApiClientError:
            raise
        except Exception as exception:
            msg = f"Unexpected error fetching information - {exception}"
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
            interval_key = (
                FIELD_HOUR if interval_type == INTERVAL_HOURLY else FIELD_QUARTER_HOUR
            )
            records: list[dict[str, Any]] = []
            for row_num, row in enumerate(csv_reader, start=1):
                delivery_day = row.get(FIELD_DELIVERY_DAY, "")
                interval_value = row.get(interval_key, "")
                if not delivery_day or not interval_value:
                    LOGGER.debug(
                        "Skipping %s CSV row %d: missing Delivery day or %s",
                        interval_type,
                        row_num,
                        interval_key,
                    )
                    continue
                period_start = _compute_period_start_utc(
                    delivery_day,
                    interval_value,
                    interval_type,
                    dst_correction=self._dst_correction,
                    time_offset_hours=self._time_offset_hours,
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

        except csv.Error as exception:
            msg = f"Error parsing CSV data: {exception}"
            raise SouthpoolApiClientError(msg) from exception
