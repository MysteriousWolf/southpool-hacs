"""Southpool API Client."""

from __future__ import annotations

import csv
import io
import socket
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import async_timeout


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
        self._base_url = "https://labs.hupx.hu/csv/v1/dam_aggregated_trading_data_15min/csv"

    async def async_get_data(self) -> dict[str, Any]:
        """Get 48 hours of trading data for the configured region (today + tomorrow)."""
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Build the filter parameter for 48 hours
        filter_param = f"DeliveryDay__gte__{today},DeliveryDay__lte__{tomorrow},Region__in__{self._region}"

        url = f"{self._base_url}?filter={filter_param}"

        return await self._api_wrapper(
            method="get",
            url=url,
        )

    async def async_get_data_for_date(self, date: str) -> dict[str, Any]:
        """Get trading data for a specific date."""
        filter_param = f"DeliveryDay__gte__{date},DeliveryDay__lte__{date},Region__in__{self._region}"
        url = f"{self._base_url}?filter={filter_param}"

        return await self._api_wrapper(
            method="get",
            url=url,
        )

    async def _api_wrapper(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        headers: dict | None = None,
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
                return self._parse_csv_data(csv_content)

        except TimeoutError as exception:
            msg = f"Timeout error fetching information - {exception}"
            raise SouthpoolApiClientCommunicationError(msg) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching information - {exception}"
            raise SouthpoolApiClientCommunicationError(msg) from exception
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Something really wrong happened! - {exception}"
            raise SouthpoolApiClientError(msg) from exception

    def _parse_csv_data(self, csv_content: str) -> dict[str, Any]:
        """Parse CSV content into raw structured data."""
        try:
            # Parse CSV using csv.DictReader
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(csv_reader)

            # Build response with raw data only
            result = {
                "region": self._region,
                "data_count": len(rows),
                "records": rows,
                "api_fetch_time": datetime.now().isoformat(),
            }

            return result

        except Exception as exception:
            msg = f"Error parsing CSV data: {exception}"
            raise SouthpoolApiClientError(msg) from exception
